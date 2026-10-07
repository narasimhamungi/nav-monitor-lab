"""Size and stress the loan. The loan arithmetic itself is fund-finance-lab's NAV facility model, used
as an installed package and not modified: eligible NAV after concentration limits, LTV, covenant
status, breakeven drawdowns, cure amounts. This module feeds it real holdings and adds the two things
it does not have: sector-shaped stresses and repayment from exits over time.
"""
from __future__ import annotations

import math
from datetime import date

from fundfinancelab import nav_facility as nf

from .collateral import PoolAsset
from .sources.base import PriceBook


def to_assets(pool: list[PoolAsset], values: dict[str, float] | None = None) -> list[nf.Asset]:
    """Eligible holdings as fund-finance-lab assets; `values` overrides fair value by key (for stresses)."""
    return [nf.Asset(a.key, (values or {}).get(a.key, a.fair_value)) for a in pool if a.eligible]


def eligible_nav(assets: list[nf.Asset], cov: dict) -> tuple[float, float]:
    return nf.eligible_nav(assets, cov["single_asset_cap"], cov.get("top_n"), cov.get("top_n_share"))


def facility(loan: float, cov: dict) -> nf.NavFacility:
    return nf.NavFacility(loan=loan, ltv_sweep=cov["ltv_sweep"], ltv_breach=cov["ltv_breach"], ltv_target=cov["ltv_target"],
                          single_asset_cap=cov["single_asset_cap"], top_n=cov.get("top_n"), top_n_share=cov.get("top_n_share"),
                          min_assets=cov.get("min_assets"))


def status_of(loan: float, assets: list[nf.Asset], cov: dict) -> dict:
    f = facility(loan, cov)
    elig, excl = eligible_nav(assets, cov)
    v, div = nf.ltv(loan, elig), nf.diversity_ok(assets, f)
    return {"nav": sum(a.nav for a in assets), "eligible_nav": elig, "excluded_by_limits": excl, "ltv": v,
            "status": nf.status(v, f, div), "diversified": div,
            "cure_to_target": nf.cure_amount(loan, elig, f.ltv_target) if v >= f.ltv_breach else 0.0}


def size_grid(pool: list[PoolAsset], cov: dict, sizing: dict) -> dict:
    """For each candidate opening LTV: the loan it implies and how it behaves under uniform drawdowns
    and the loss of the largest names. Loan = opening LTV x eligible NAV after concentration limits."""
    assets = to_assets(pool)
    elig, excl = eligible_nav(assets, cov)
    out = {"eligible_nav": elig, "excluded_by_limits": excl, "candidates": [], "uniform": [], "single_name": []}
    for l0 in sizing["opening_ltv_grid"]:
        loan = l0 * elig
        f = facility(loan, cov)
        s = nf.summary(assets, f)
        out["candidates"].append({"opening_ltv": l0, "loan": loan, "status": s["status"], "drawdown_to_sweep": s["drawdown_to_sweep"],
                                  "drawdown_to_breach": s["drawdown_to_breach"], "excluded_single_cap": s["excluded_single_cap"],
                                  "excluded_top_n": s["excluded_top_n"], "largest_asset": s["largest_asset"],
                                  "largest_asset_share": s["largest_asset_share"]})
        for r in nf.uniform_stress(assets, f, sizing["drawdown_grid"]):
            out["uniform"].append({"opening_ltv": l0, "loan": loan, "drawdown": r["drawdown"], "eligible_nav": r["eligible_nav"],
                                   "ltv": r["ltv"], "status": r["status"], "cure_to_target": r["cure_to_target"]})
        for r in nf.single_name_stress(assets, f, sizing.get("single_name_loss", 1.0), sizing.get("single_names", 3)):
            out["single_name"].append({"opening_ltv": l0, "loan": loan, "assets_written_down": r["assets_written_down"], "names": r["names"],
                                       "eligible_nav": r["eligible_nav"], "ltv": r["ltv"], "status": r["status"],
                                       "remaining_drawdown_to_breach": r["remaining_drawdown_to_breach"]})
    return out


def max_drawdown(rows: list[tuple[date, float, float]], start: date, end: date) -> float:
    """Largest peak-to-trough fall of the adjusted close inside [start, end], on the observations available."""
    peak, worst = None, 0.0
    for d, adj, _ in rows:
        if d < start or d > end:
            continue
        peak = adj if peak is None else max(peak, adj)
        worst = max(worst, 1.0 - adj / peak)
    return worst


def resolve_scenarios(scenarios: list[dict], sectors: list[str], prices: PriceBook | None, sector_proxy: dict,
                      default_proxy: str) -> tuple[list[dict], list[str]]:
    """Scenario definitions -> one write-down per sector. Market-driven scenarios are computed from the
    price history; if that history is missing they are skipped and the reason is returned."""
    out, skipped = [], []
    for sc in scenarios:
        if "shocks" in sc:
            default = float(sc["shocks"].get("default", 0.0))
            named = [(k, float(v)) for k, v in sc["shocks"].items() if k != "default"]
            label = "; ".join(f"{k} -{v:.0%}" for k, v in sorted(named, key=lambda kv: -kv[1]))
            label = (label + f"; all other sectors -{default:.0%}") if named else f"every sector -{default:.0%}"
            out.append({"name": sc["name"], "kind": "configured", "label": label,
                        "shocks": {s: float(sc["shocks"].get(s, default)) for s in sectors}})
            continue
        h = sc["historical"]
        start, end = date.fromisoformat(str(h["window_start"])), date.fromisoformat(str(h["window_end"]))
        pt = float(h.get("pass_through", 1.0))
        shocks, missing = {}, []
        for s in sectors:
            sym = sector_proxy.get(s, default_proxy)
            if prices is None or not prices.has(sym) or prices.first_date(sym) > start:
                missing.append(sym); continue
            shocks[s] = pt * max_drawdown(prices.rows(sym), start, end)
        if missing:
            skipped.append(f"{sc['name']}: no price history covering {start} to {end} for {', '.join(sorted(set(missing)))}")
        else:
            label = "; ".join(f"{k} -{v:.0%}" for k, v in sorted(shocks.items(), key=lambda kv: -kv[1]))
            out.append({"name": f"{sc['name']} ({start.isoformat()} to {end.isoformat()})", "kind": "market history", "label": label,
                        "shocks": shocks})
    return out, skipped


def run_scenarios(pool: list[PoolAsset], cov: dict, loan: float, resolved: list[dict]) -> list[dict]:
    rows = []
    base = sum(a.fair_value for a in pool if a.eligible)
    for sc in resolved:
        values = {a.key: a.fair_value * (1.0 - sc["shocks"].get(a.sector, 0.0)) for a in pool if a.eligible}
        st = status_of(loan, to_assets(pool, values), cov)
        rows.append({"scenario": sc["name"], "kind": sc["kind"], "pool_fall": 1.0 - st["nav"] / base if base else 0.0,
                     "eligible_nav": st["eligible_nav"], "ltv": st["ltv"], "status": st["status"],
                     "cure_to_target": st["cure_to_target"],
                     "shocks": sc["label"]})
    return rows


def runoff(nav0: float, loan0: float, *, all_in_rate_pct: float, tenor_years: int, pace_per_year: float, cov: dict,
           sweep_below: float, sweep_above: float, growth_per_year: float = 0.0, markdown: float = 0.0,
           drought_multiplier: float = 1.0, drought_quarters: int = 0) -> dict:
    """Quarter-by-quarter repayment from exits (docs/model_spec.md, S-4).

    Each quarter the pool realises pace/4 of its value. Proceeds pay interest first; unpaid interest is
    added to the loan. A share of what is left repays principal: `sweep_below` while LTV is under the sweep
    level, `sweep_above` once it is at or over it.
    """
    nav, loan = nav0 * (1.0 - markdown), loan0
    q_growth = (1.0 + growth_per_year) ** 0.25
    rows, peak, breached, swept, capitalised, repaid_q = [], 0.0, False, False, 0.0, None
    for q in range(1, tenor_years * 4 + 1):
        nav *= q_growth
        ltv_start = loan / nav if nav > 0 else math.inf
        mult = drought_multiplier if q <= drought_quarters else 1.0
        proceeds = nav * pace_per_year * mult / 4.0
        nav -= proceeds
        interest = loan * all_in_rate_pct / 100.0 / 4.0
        paid_interest = min(interest, proceeds)
        capitalised += interest - paid_interest
        loan += interest - paid_interest
        share = sweep_above if ltv_start >= cov["ltv_sweep"] else sweep_below
        repay = min(loan, (proceeds - paid_interest) * share)
        loan -= repay
        ltv_end = 0.0 if loan <= 1e-9 else (loan / nav if nav > 0 else math.inf)
        peak = max(peak, ltv_start, ltv_end)
        breached = breached or ltv_end >= cov["ltv_breach"] or ltv_start >= cov["ltv_breach"]
        swept = swept or ltv_start >= cov["ltv_sweep"]
        if repaid_q is None and loan <= 1e-9:
            repaid_q = q
        rows.append({"quarter": q, "exit_proceeds": proceeds, "interest": interest, "interest_capitalised": interest - paid_interest,
                     "principal_repaid": repay, "loan_end": max(loan, 0.0), "nav_end": nav, "ltv_end": ltv_end,
                     "status": "repaid" if loan <= 1e-9 else ("breach" if ltv_end >= cov["ltv_breach"] else
                                                                ("cash sweep" if ltv_end >= cov["ltv_sweep"] else "ok"))})
    return {"rows": rows, "repaid_quarter": repaid_q, "balance_at_maturity": max(loan, 0.0), "peak_ltv": peak, "breached": breached,
            "swept": swept, "interest_capitalised": capitalised,
            "balance_share_of_nav_at_maturity": (loan / nav if nav > 0 else math.inf) if loan > 1e-9 else 0.0}


def breakeven_pace(nav0: float, loan0: float, **kw) -> float | None:
    """Lowest yearly exit pace at which the loan is fully repaid by maturity (to the nearest 0.1 point)."""
    kw = {k: v for k, v in kw.items() if k != "pace_per_year"}
    lo, hi = 0.0, 1.0
    if runoff(nav0, loan0, pace_per_year=hi, **kw)["balance_at_maturity"] > 1e-6:
        return None
    for _ in range(40):
        mid = (lo + hi) / 2
        if runoff(nav0, loan0, pace_per_year=mid, **kw)["balance_at_maturity"] > 1e-6:
            lo = mid
        else:
            hi = mid
    return math.ceil(hi * 1000 - 1e-9) / 1000        # rounded up, so the returned pace always repays
