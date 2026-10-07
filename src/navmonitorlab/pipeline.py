"""One analysis run, start to finish, on normalised files. No network access happens here:
`navmon refresh` fetches, this reads. Given the same data directory and configs the outputs are
byte-identical, which is what makes a memo reproducible.
"""
from __future__ import annotations

import hashlib
import json
import platform
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from . import __version__, backtest, collateral, diff, quality, recommend, rollforward, sizing, trackrecord
from .schema import SEVERITY_ORDER, Finding, Snapshot
from .sources import PriceBook, RateBook, holdings_source, price_source, rate_source, track_source

FAR_PAST, FAR_FUTURE = date(1990, 1, 1), date(2100, 1, 1)


def load_market(cfg: dict, data_dir: Path) -> tuple[PriceBook, RateBook, list[Finding]]:
    prices, rates, findings = PriceBook(), RateBook(), []
    pcfg, rcfg = cfg["market"]["prices"]["files"], cfg["market"]["rates"]["files"]
    if (data_dir / pcfg["csv"]).exists():
        src = price_source(pcfg, data_dir=data_dir)
        for sym in src.symbols():
            prices.add(sym, src.history(sym, FAR_PAST, FAR_FUTURE), src.currency.get(sym, ""))
    else:
        findings.append(Finding("warn", "M00", "market data", "No price file in the data directory; the market layer is skipped",
                                observed=str(data_dir / pcfg["csv"])))
    if (data_dir / rcfg["csv"]).exists():
        src = rate_source(rcfg, data_dir=data_dir)
        for s in src.series():
            rates.add(s, src.history(s, FAR_PAST, FAR_FUTURE))
    else:
        findings.append(Finding("warn", "M00", "market data", "No rates file in the data directory; the base rate falls back to 0",
                                observed=str(data_dir / rcfg["csv"])))
    return prices, rates, findings


def _pick(snaps: list[Snapshot], as_of: date | None) -> int:
    if as_of is None:
        return len(snaps) - 1
    for i, s in enumerate(snaps):
        if s.as_of == as_of:
            return i
    raise ValueError(f"no snapshot dated {as_of}; available: {snaps[0].as_of} to {snaps[-1].as_of}")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyse(cfg: dict, data_dir: Path, *, as_of: date | None = None, compare_to: date | None = None) -> dict:
    data_dir = Path(data_dir)
    fac, market, veh, track_cfg = cfg["facility"], cfg["market"], cfg["vehicle"], cfg["track"]
    cov, policy = fac["covenants"], fac["policy"]
    findings: list[Finding] = []

    # 1. inputs
    snaps = holdings_source({**veh["files"], "vehicle": veh["vehicle"]}, data_dir=data_dir).load()
    if not snaps:
        raise ValueError("no holdings snapshots in the data directory")
    i = _pick(snaps, as_of)
    cur = snaps[i]
    history = snaps[: i + 1]
    prev = snaps[_pick(snaps, compare_to)] if compare_to else (snaps[i - 1] if i > 0 else None)
    tr = track_source(track_cfg["files"], data_dir=data_dir).load()
    prices, rates, mf = load_market(cfg, data_dir)
    findings += mf

    # 2. data quality
    per_snapshot = {s.as_of: quality.check_snapshot(s, stale_days=policy["stale_days"]) for s in history}
    for fs in per_snapshot.values():
        findings += fs
    findings += quality.check_history(history, veh.get("company_aliases") or {}, veh.get("sector_aliases") or {})
    findings += quality.check_track_record(tr, **track_cfg["quality"])
    recent = history[-12:]
    unreconciled_recent = sum(1 for s in recent if any(f.code in ("Q01", "Q02") for f in per_snapshot[s.as_of]))
    unreconciled_all = [s.as_of.isoformat() for s in history if any(f.code == "Q01" for f in per_snapshot[s.as_of])]

    # 3. track record
    gp = trackrecord.GpMap(cfg["gp_map"])
    metrics = trackrecord.fund_metrics(tr, gp, track_cfg["scoring"]["cohort_min_funds"])
    families = trackrecord.family_records(metrics, track_cfg["scoring"])
    tr_cov = trackrecord.coverage(metrics)

    # 4. collateral pool and sponsor overlay
    pool = collateral.build_pool(cur, veh, fac["collateral"])
    pool_sum = collateral.pool_summary(cur, pool)
    overlay_rows, overlay_sum = trackrecord.sponsor_overlay(pool, gp, families)

    # 5. market layer: backtest first (it sets the pass-through), then the roll-forward
    proxies = sorted({rollforward.proxy_for(a.sector, market["sector_proxy"], market["default_proxy"]) for a in pool})
    have_prices = all(prices.has(s) for s in proxies)
    bt = backtest.run(history, prices, cfg) if have_prices and len(history) > int(market["backtest"]["horizon_months"]) else None
    acc = bt["accuracy"] if bt else None
    pass_through, pt_source = float(market["roll_forward"]["pass_through"]), "configs/market.yaml (assumption)"
    if acc and acc["beta_in_sample"] is not None and market["roll_forward"].get("use_backtest_beta", True):
        pass_through = max(0.0, min(1.0, acc["beta_in_sample"]))
        pt_source = f"fitted on {acc['n_periods']} past valuation cycles of this vehicle"
    rf = rollforward.roll_forward(cur, pool, prices, market, pass_through=pass_through) if have_prices else \
        {"ran": False, "rows": [], "values": {}, "findings": [], "to": None, "pass_through": pass_through}
    findings += rf["findings"]
    rf_full = rollforward.roll_forward(cur, pool, prices, market, pass_through=1.0) if rf["ran"] else None
    disc = rollforward.discount_to_nav(cur, prices, veh.get("listed_share"), rf["to"]) if rf["ran"] else None
    replay = backtest.covenant_replay(history, prices, cfg, pass_through) if have_prices and len(history) > 1 else None
    series = market["rates"]["base_rate_series"]
    rate_date, base_rate = None, 0.0
    try:
        rate_date, base_rate = rates.latest(series, rf["to"] if rf["ran"] else None)
    except KeyError:
        findings.append(Finding("warn", "M05", "market data", f"No {series} rate available; interest is computed on the margin alone"))
    ro_cfg = fac["runoff"]
    all_in = base_rate + float(ro_cfg["margin_pct"])

    # 6. sizing, stresses, repayment
    grid = sizing.size_grid(pool, cov, fac["sizing"])
    sectors = sorted({a.sector for a in pool if a.eligible})
    resolved, skipped_sc = sizing.resolve_scenarios(fac["scenarios"], sectors, prices if have_prices else None,
                                                    market["sector_proxy"], market["default_proxy"])
    for msg in skipped_sc:
        findings.append(Finding("warn", "S01", "scenarios", "Market-history scenario skipped", observed=msg))
    scen_rows: dict[float, list[dict]] = {}
    runoffs: dict[float, dict] = {}
    rolled_ltv: dict[float, float | None] = {}
    ro_kw = dict(all_in_rate_pct=all_in, tenor_years=int(ro_cfg["tenor_years"]), cov=cov, sweep_below=float(ro_cfg["sweep_share_below_trigger"]),
                 sweep_above=float(ro_cfg["sweep_share_above_trigger"]), growth_per_year=float(ro_cfg.get("nav_growth_per_year", 0.0)))
    dr = ro_cfg["drought"]
    est_elig = sizing.eligible_nav(sizing.to_assets(pool, rf["values"]), cov)[0] if rf["ran"] else None
    full_elig = sizing.eligible_nav(sizing.to_assets(pool, rf_full["values"]), cov)[0] if rf_full else None
    full_ltv: dict[float, float | None] = {}

    def pool_change(run: dict | None) -> float | None:
        """Change in the eligible holdings' summed value, before concentration limits."""
        if not run or not run.get("ran"):
            return None
        rows_ = [x for x in run["rows"] if x["eligible"]]
        rep_ = sum(x["reported_fv"] for x in rows_)
        return (sum(x["estimated_fv"] for x in rows_) / rep_ - 1.0) if rep_ else None
    for c in grid["candidates"]:
        l0, loan = c["opening_ltv"], c["loan"]
        scen_rows[l0] = sizing.run_scenarios(pool, cov, loan, resolved)
        pace = float(ro_cfg["exit_pace_per_year"])
        runoffs[l0] = {
            "base": sizing.runoff(grid["eligible_nav"], loan, pace_per_year=pace, **ro_kw),
            "drought": sizing.runoff(grid["eligible_nav"], loan, pace_per_year=pace, drought_multiplier=float(dr["pace_multiplier"]),
                                     drought_quarters=int(dr["quarters"]), **ro_kw),
            "drought_markdown": sizing.runoff(grid["eligible_nav"], loan, pace_per_year=pace, drought_multiplier=float(dr["pace_multiplier"]),
                                              drought_quarters=int(dr["quarters"]), markdown=float(dr["markdown"]), **ro_kw),
            "breakeven_pace": sizing.breakeven_pace(grid["eligible_nav"], loan, **ro_kw),
            "pace_grid": [{"pace": p, **{k: v for k, v in sizing.runoff(grid["eligible_nav"], loan, pace_per_year=p, **ro_kw).items() if k != "rows"}}
                          for p in ro_cfg["pace_grid"]],
        }
        rolled_ltv[l0] = (loan / est_elig) if est_elig else None
        full_ltv[l0] = (loan / full_elig) if full_elig else None

    # 7. recommendation
    cand_tests = recommend.assess_candidates(grid["candidates"], scen_rows, grid["single_name"], runoffs, rolled_ltv, cov, fac["sizing"])
    passing = [c for c in cand_tests if c["passed"]]
    proposed = max(passing, key=lambda c: c["opening_ltv"]) if passing else None
    counts = Counter(f.severity for f in findings)
    stale = {"stale_share": quality.stale_share(cur, policy["stale_days"]), "age_at_report": quality.weighted_mark_age(cur),
             "age_today": rf.get("weighted_private_mark_age_days") if rf["ran"] else None}
    meta = {"investment_level_pct": cur.investment_level_pct, "cash_m": cur.cash_m, "undrawn_credit_m": cur.undrawn_credit_m}
    flags = recommend.build_flags(
        pool=pool_sum, overlay=overlay_sum, quality_counts={"error": counts.get("error", 0), "unreconciled_recent": unreconciled_recent},
        stale=stale, snapshot_meta=meta, proposed=proposed,
        runoff_info=({"breakeven_pace": runoffs[proposed["opening_ltv"]]["breakeven_pace"], "assumed_pace": float(ro_cfg["exit_pace_per_year"])}
                     if proposed else None),
        policy=policy, cov=cov, limits_bite=grid["excluded_by_limits"], market_ran=rf["ran"])
    verdict, proposed = recommend.decide(cand_tests, flags)

    # 8. change log
    changes = diff.diff_snapshots(prev, cur, veh, policy, fac.get("watchlist")) if prev else None

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.code, f.scope))
    return {
        "cfg": cfg, "vehicle": veh["vehicle"], "vehicle_name": veh.get("name", veh["vehicle"]), "currency": cur.currency, "unit": cur.unit,
        "snapshot": cur, "previous": prev, "history_n": len(history), "history_start": history[0].as_of, "track_record": tr,
        "findings": findings, "finding_counts": dict(counts), "unreconciled_recent": unreconciled_recent, "unreconciled_all": unreconciled_all,
        "metrics": metrics, "families": families, "vintages": trackrecord.vintage_table(metrics), "track_coverage": tr_cov,
        "pool": pool, "pool_summary": pool_sum, "sector_mix": collateral.sector_mix(pool), "overlay_rows": overlay_rows, "overlay": overlay_sum,
        "backtest": bt, "accuracy": acc, "pass_through": pass_through, "pass_through_source": pt_source, "roll_forward": rf,
        "estimated_eligible_nav": est_elig, "discount": disc, "replay": replay, "base_rate": base_rate, "base_rate_date": rate_date,
        "base_rate_series": series, "all_in_rate": all_in, "grid": grid, "scenarios": resolved, "scenario_rows": scen_rows,
        "runoffs": runoffs, "rolled_ltv": rolled_ltv, "full_pass_through_ltv": full_ltv, "full_pass_through_eligible_nav": full_elig,
        "eligible_pool_change_estimated": pool_change(rf), "eligible_pool_change_full_pass_through": pool_change(rf_full), "candidate_tests": cand_tests, "flags": flags, "verdict": verdict,
        "proposed": proposed, "stale": stale, "changes": changes, "have_prices": have_prices,
    }


def run_manifest(cfg: dict, data_dir: Path, result: dict, outputs: list[Path]) -> dict:
    """What went in and what came out, with hashes. `generated_at` is the only field that changes between
    identical runs, which is why it lives here and not in the memo."""
    data_dir = Path(data_dir)
    inputs = {p.name: _sha(p) for p in sorted(data_dir.glob("*.csv"))}
    cdir = Path(cfg["_dir"])
    configs = {p.name: _sha(p) for p in sorted(cdir.glob("*.yaml"))}
    try:
        from importlib.metadata import version
        ffl = version("fund-finance-lab")
    except Exception:
        ffl = "unknown"
    return {"tool": "nav-monitor-lab", "version": __version__, "fund_finance_lab_version": ffl, "python": platform.python_version(),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_dir": data_dir.as_posix(),
            "snapshot_as_of": result["snapshot"].as_of.isoformat(), "track_record_as_of": result["track_record"].as_of.isoformat(),
            "prices_to": result["roll_forward"]["to"].isoformat() if result["roll_forward"].get("to") else None,
            "inputs_sha256": inputs, "configs_sha256": configs,
            "outputs_sha256": {p.name: _sha(p) for p in sorted(outputs) if p.exists() and p.suffix != ".xlsx"}}
