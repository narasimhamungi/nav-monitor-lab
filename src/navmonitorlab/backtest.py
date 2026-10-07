"""How wrong has the roll-forward been, and would the covenant have tripped?

Two tests on the vehicle's own published history:
1. Accuracy. Take pairs of reports one valuation cycle apart. For each private company in both, compare
   the change in its published fair value with the change in its listed sector proxy over the matching
   valuation dates. That gives a measured pass-through factor and a measured error, for the estimate and
   for the alternative of doing nothing (carrying stale marks).
2. Covenant replay. Fix a loan at the first report and walk forward: what did LTV look like on reported
   values, and on rolled-forward values, at each later report?

What this cannot separate: a fair-value change also contains follow-on investments, part-realisations and
currency moves, none of which the published table breaks out. Moves beyond a size limit are left out for
that reason and counted. See docs/limitations.md.
"""
from __future__ import annotations

from datetime import date

from . import sizing
from .collateral import build_pool
from .names import canonical_sector, keyed
from .rollforward import mix_index, proxy_for, roll_forward
from .schema import Snapshot
from .sources.base import PriceBook


def _chain(snaps: list[Snapshot], horizon_months: int) -> list[tuple[Snapshot, Snapshot]]:
    """Non-overlapping pairs `horizon_months` apart, anchored on the latest report and walking back."""
    by = {(s.as_of.year, s.as_of.month): s for s in snaps}
    pairs = []
    y, m = snaps[-1].as_of.year, snaps[-1].as_of.month
    while True:
        py, pm = y, m - horizon_months
        while pm <= 0:
            py, pm = py - 1, pm + 12
        if (py, pm) not in by or (y, m) not in by:
            break
        pairs.append((by[(py, pm)], by[(y, m)]))
        y, m = py, pm
    return list(reversed(pairs))


def observations(snaps: list[Snapshot], prices: PriceBook, vehicle_cfg: dict, market_cfg: dict) -> tuple[list[dict], list[dict]]:
    """Name-level observations and the ones left out (with the reason)."""
    bt = market_cfg["backtest"]
    aliases, sector_aliases = vehicle_cfg.get("company_aliases") or {}, vehicle_cfg.get("sector_aliases") or {}
    sector_proxy, default_proxy = market_cfg["sector_proxy"], market_cfg["default_proxy"]
    gap = int(market_cfg["roll_forward"].get("max_price_gap_days", 10))
    obs, skipped = [], []
    for s0, s1 in _chain(snaps, int(bt["horizon_months"])):
        k0, k1 = keyed(s0, aliases), keyed(s1, aliases)
        m0, m1 = s0.private_mix(), s1.private_mix()
        for key in sorted(set(k0) & set(k1)):
            h0, h1 = k0[key], k1[key]
            base = {"from": s0.as_of.isoformat(), "to": s1.as_of.isoformat(), "company": key}
            if h0.is_undisclosed or h1.is_undisclosed:
                skipped.append({**base, "reason": "undisclosed name cannot be matched across reports"}); continue
            if h0.is_listed or h1.is_listed:
                skipped.append({**base, "reason": "quoted holding (marked to market already)"}); continue
            sector = canonical_sector(h1.sector, sector_aliases)
            sym = proxy_for(sector, sector_proxy, default_proxy)
            actual = h1.fair_value / h0.fair_value - 1.0
            if abs(actual) > float(bt["max_abs_move"]):
                skipped.append({**base, "reason": f"move of {actual:+.0%} exceeds the size limit (follow-on or part-exit likely)"}); continue
            try:
                idx = mix_index(prices, sym, m1, gap) / mix_index(prices, sym, m0, gap) - 1.0
            except KeyError as e:
                skipped.append({**base, "reason": f"no proxy price: {e}"}); continue
            obs.append({**base, "sector": sector, "proxy": sym, "fv_from": h0.fair_value, "fv_to": h1.fair_value,
                        "actual": actual, "proxy_return": idx})
    return obs, skipped


def fit_beta(obs: list[dict]) -> float | None:
    """Least squares through the origin, weighted by starting fair value: actual = beta x proxy return."""
    sxx = sum(o["fv_from"] * o["proxy_return"] ** 2 for o in obs)
    return (sum(o["fv_from"] * o["proxy_return"] * o["actual"] for o in obs) / sxx) if sxx > 0 else None


def _corr(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx, syy = sum((x - mx) ** 2 for x in xs), sum((y - my) ** 2 for y in ys)
    return (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sxx * syy) ** 0.5) if sxx > 0 and syy > 0 else None


def accuracy(obs: list[dict], min_periods_to_fit: int = 4) -> dict:
    """Portfolio-level error per period for: no adjustment, full pass-through, the fitted factor
    (in-sample), and the factor fitted only on earlier periods (walk-forward, the honest one)."""
    periods = sorted({(o["from"], o["to"]) for o in obs})
    beta_all = fit_beta(obs)
    rows = []
    for i, (f, t) in enumerate(periods):
        cur = [o for o in obs if (o["from"], o["to"]) == (f, t)]
        w = sum(o["fv_from"] for o in cur)
        actual = sum(o["fv_to"] for o in cur) / w - 1.0
        proxy = sum(o["fv_from"] * o["proxy_return"] for o in cur) / w
        earlier = [o for o in obs if o["to"] <= f]
        beta_wf = fit_beta(earlier) if i >= min_periods_to_fit else None
        rows.append({"from": f, "to": t, "names": len(cur), "fair_value_from": w, "actual": actual, "proxy_return": proxy,
                     "err_no_adjustment": actual, "err_full_pass_through": actual - proxy,
                     "err_fitted_in_sample": None if beta_all is None else actual - beta_all * proxy,
                     "beta_walk_forward": beta_wf, "err_walk_forward": None if beta_wf is None else actual - beta_wf * proxy})

    def mae(key: str, only: list[dict] | None = None) -> float | None:
        v = [abs(r[key]) for r in (only if only is not None else rows) if r[key] is not None]
        return sum(v) / len(v) if v else None

    wf = [r for r in rows if r["err_walk_forward"] is not None]
    return {"periods": rows, "n_periods": len(rows), "n_observations": len(obs), "beta_in_sample": beta_all,
            "correlation_name_level": _corr([o["proxy_return"] for o in obs], [o["actual"] for o in obs]),
            "correlation_period_level": _corr([r["proxy_return"] for r in rows], [r["actual"] for r in rows]),
            "mae_no_adjustment": mae("err_no_adjustment"), "mae_full_pass_through": mae("err_full_pass_through"),
            "mae_fitted_in_sample": mae("err_fitted_in_sample"),
            "n_walk_forward": len(wf), "mae_walk_forward": mae("err_walk_forward"),
            "mae_no_adjustment_same_periods": mae("err_no_adjustment", wf),
            "mae_full_pass_through_same_periods": mae("err_full_pass_through", wf),
            "beta_latest_walk_forward": wf[-1]["beta_walk_forward"] if wf else None}


def covenant_replay(snaps: list[Snapshot], prices: PriceBook, cfg: dict, pass_through: float) -> dict:
    """Fix a loan at the first report (opening LTV x eligible NAV then) and track LTV at every later report:
    on reported values, on rolled-forward values with the fitted factor, and with full pass-through.
    The loan is held constant (no repayments), which overstates LTV as holdings are sold; that is deliberate."""
    cov, market = cfg["facility"]["covenants"], cfg["market"]
    rows, summary = [], []
    first_pool = build_pool(snaps[0], cfg["vehicle"], cfg["facility"]["collateral"])
    base_elig, _ = sizing.eligible_nav(sizing.to_assets(first_pool), cov)
    path = []
    for s in snaps:
        pool = build_pool(s, cfg["vehicle"], cfg["facility"]["collateral"])
        rep, _ = sizing.eligible_nav(sizing.to_assets(pool), cov)
        est = full = None
        try:
            r1 = roll_forward(s, pool, prices, market, pass_through=pass_through, to=s.as_of)
            r2 = roll_forward(s, pool, prices, market, pass_through=1.0, to=s.as_of)
            if r1["ran"]:
                est, _ = sizing.eligible_nav(sizing.to_assets(pool, r1["values"]), cov)
                full, _ = sizing.eligible_nav(sizing.to_assets(pool, r2["values"]), cov)
        except KeyError:
            pass
        path.append((s.as_of, rep, est, full))
    for l0 in market["backtest"]["replay_opening_ltvs"]:
        loan = l0 * base_elig
        worst = {"reported": (0.0, None), "estimated": (0.0, None), "full": (0.0, None)}
        firsts = {"reported_sweep": None, "estimated_sweep": None, "full_sweep": None, "reported_breach": None,
                  "estimated_breach": None, "full_breach": None}
        for d, rep, est, full in path:
            vals = {"reported": rep, "estimated": est, "full": full}
            ltvs = {k: (loan / v if v else None) for k, v in vals.items()}
            for k, v in ltvs.items():
                if v is None:
                    continue
                if v > worst[k][0]:
                    worst[k] = (v, d)
                if v >= cov["ltv_sweep"] and firsts[f"{k}_sweep"] is None:
                    firsts[f"{k}_sweep"] = d
                if v >= cov["ltv_breach"] and firsts[f"{k}_breach"] is None:
                    firsts[f"{k}_breach"] = d
            rows.append({"opening_ltv": l0, "loan": loan, "as_of": d.isoformat(), "eligible_reported": rep, "ltv_reported": ltvs["reported"],
                         "eligible_estimated": est, "ltv_estimated": ltvs["estimated"], "eligible_full_pass_through": full,
                         "ltv_full_pass_through": ltvs["full"]})
        summary.append({"opening_ltv": l0, "loan": loan, "start": snaps[0].as_of.isoformat(), "end": snaps[-1].as_of.isoformat(),
                        **{f"peak_ltv_{k}": v[0] for k, v in worst.items()},
                        **{f"peak_date_{k}": (v[1].isoformat() if v[1] else "") for k, v in worst.items()},
                        **{f"first_{k}": (v.isoformat() if v else "") for k, v in firsts.items()}})
    return {"rows": rows, "summary": summary, "pass_through": pass_through}


def robustness(snaps: list[Snapshot], prices: PriceBook, cfg: dict) -> list[dict]:
    """Repeat the accuracy test on every possible set of reporting months (anchor the chain one, two, ...
    months earlier). If the answer changes with the anchor, it is not a result."""
    bt = cfg["market"]["backtest"]
    out = []
    for off in range(int(bt["horizon_months"])):
        hist = snaps[: len(snaps) - off]
        if len(hist) <= int(bt["horizon_months"]):
            break
        obs, _ = observations(hist, prices, cfg["vehicle"], cfg["market"])
        if not obs:
            continue
        a = accuracy(obs, int(bt["min_periods_to_fit"]))
        beats = (a["mae_walk_forward"] is not None and a["mae_walk_forward"] < a["mae_no_adjustment_same_periods"])
        out.append({"chain_ends": hist[-1].as_of.isoformat(), "periods": a["n_periods"], "observations": a["n_observations"],
                    "beta_in_sample": a["beta_in_sample"], "mae_no_adjustment": a["mae_no_adjustment"],
                    "mae_full_pass_through": a["mae_full_pass_through"], "walk_forward_periods": a["n_walk_forward"],
                    "mae_walk_forward": a["mae_walk_forward"], "mae_no_adjustment_same_periods": a["mae_no_adjustment_same_periods"],
                    "mae_full_pass_through_same_periods": a["mae_full_pass_through_same_periods"],
                    "estimate_beats_stale_marks": beats, "correlation_period_level": a["correlation_period_level"]})
    return out


def verdict(rob: list[dict]) -> str:
    """One of three fixed statements, chosen by counting, about whether the roll-forward earns its place."""
    scored = [r for r in rob if r["mae_walk_forward"] is not None]
    if not scored:
        return "too little history to judge the estimate out of sample"
    wins = sum(1 for r in scored if r["estimate_beats_stale_marks"])
    if wins == len(scored):
        return "the estimate beat carrying stale marks on every set of reporting months tested"
    if wins == 0:
        return "the estimate did not beat carrying stale marks on any set of reporting months tested"
    return (f"the estimate beat carrying stale marks on {wins} of {len(scored)} sets of reporting months, so it is not a reliable "
            "improvement at this horizon")


def run(snaps: list[Snapshot], prices: PriceBook, cfg: dict) -> dict:
    obs, skipped = observations(snaps, prices, cfg["vehicle"], cfg["market"])
    acc = accuracy(obs, int(cfg["market"]["backtest"]["min_periods_to_fit"])) if obs else None
    rob = robustness(snaps, prices, cfg) if obs else []
    return {"observations": obs, "skipped": skipped, "accuracy": acc, "robustness": rob, "verdict": verdict(rob)}
