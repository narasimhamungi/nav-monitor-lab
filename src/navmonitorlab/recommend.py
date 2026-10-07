"""The recommendation: proposed terms, conditions and a verdict.

Everything here is a rule with a threshold from configs/facility.yaml. Each flag shows the rule, the
number observed and the action it leads to, so a reader can disagree with a threshold and see exactly
what would change. No free-text judgement is generated. It is illustrative and is not advice.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Flag:
    code: str
    severity: str       # "blocker" | "condition" | "note"
    title: str
    observed: str
    threshold: str
    action: str

    def row(self) -> dict:
        return dict(self.__dict__)


def assess_candidates(candidates: list[dict], scenario_rows: dict[float, list[dict]], single_rows: list[dict],
                    runoffs: dict[float, dict], rolled_ltv: dict[float, float | None], cov: dict, sizing: dict) -> list[dict]:
    """Apply the sizing tests to each candidate opening LTV. A candidate passes only if every test passes."""
    out = []
    for c in candidates:
        l0 = c["opening_ltv"]
        tests = []
        ok = c["drawdown_to_breach"] >= sizing["min_cushion_to_breach"]
        tests.append({"test": "Cushion to breach", "passed": ok,
                      "detail": f"pool can fall {c['drawdown_to_breach']:.1%} before breach; policy needs {sizing['min_cushion_to_breach']:.0%}"})
        bad = [r["scenario"] for r in scenario_rows.get(l0, []) if r["status"] == "breach"]
        tests.append({"test": "Sector scenarios", "passed": not bad,
                      "detail": "no breach in any scenario" if not bad else "breach under: " + "; ".join(bad)})
        sn = [r for r in single_rows if r["opening_ltv"] == l0]
        bad = [str(r["assets_written_down"]) for r in sn if r["status"] == "breach"]
        tests.append({"test": "Loss of the largest names", "passed": not bad,
                      "detail": f"no breach with the largest {len(sn)} written off" if not bad else f"breach with the largest {bad[0]} written off"})
        ro = runoffs.get(l0)
        if ro:
            base, drought = ro["base"], ro["drought"]
            ok = base["balance_at_maturity"] <= 1e-6 and not base["breached"]
            tests.append({"test": "Repayment from exits (base pace)", "passed": ok,
                          "detail": (f"repaid in quarter {base['repaid_quarter']}" if base["repaid_quarter"] else
                                     f"{base['balance_at_maturity']:,.1f} outstanding at maturity") + f"; peak LTV {base['peak_ltv']:.1%}"})
            tests.append({"test": "Exit drought", "passed": not drought["breached"],
                          "detail": f"peak LTV {drought['peak_ltv']:.1%}; {drought['balance_at_maturity']:,.1f} outstanding at maturity"})
        rl = rolled_ltv.get(l0)
        if rl is not None:
            tests.append({"test": "Rolled-forward LTV under the sweep level", "passed": rl < cov["ltv_sweep"],
                          "detail": f"estimated LTV today {rl:.1%} against sweep at {cov['ltv_sweep']:.0%}"})
        out.append({"opening_ltv": l0, "loan": c["loan"], "passed": all(t["passed"] for t in tests), "tests": tests})
    return out


def build_flags(*, pool: dict, overlay: dict, quality_counts: dict, stale: dict, snapshot_meta: dict, proposed: dict | None,
                runoff_info: dict | None, policy: dict, cov: dict, limits_bite: float, market_ran: bool) -> list[Flag]:
    f: list[Flag] = []
    if quality_counts.get("error", 0):
        f.append(Flag("P01", "blocker", "Data errors in the inputs", f"{quality_counts['error']} error-level findings", "0",
                      "Resolve the errors listed in findings.csv before relying on any figure"))
    if pool["eligible_names"] < cov.get("min_assets", 0):
        f.append(Flag("P02", "blocker", "Too few eligible holdings", f"{pool['eligible_names']} names", f"at least {cov['min_assets']}",
                      "Pool fails the diversity covenant at inception"))
    if proposed is None:
        f.append(Flag("P03", "blocker", "No opening LTV on the grid passes every sizing test", "see sizing_candidates.csv", "all tests pass",
                      "Reduce the opening LTV grid or revisit the covenant levels"))
    if pool["undisclosed_share_of_published"] > policy["max_undisclosed_share"]:
        f.append(Flag("P10", "condition", "Undisclosed holdings above policy", f"{pool['undisclosed_share_of_published']:.1%} of published fair value",
                      f"at most {policy['max_undisclosed_share']:.0%}", "Obtain the names under NDA, or keep them excluded from the borrowing base"))
    elif pool["excluded_names"]:
        f.append(Flag("P10", "note", "Undisclosed holdings excluded from the pool", f"{pool['undisclosed_share_of_published']:.1%} of published fair value",
                      f"at most {policy['max_undisclosed_share']:.0%}", "Excluded names carry no collateral credit"))
    if stale["stale_share"] > policy["max_stale_share"]:
        f.append(Flag("P11", "condition", "Stale marks at the report date", f"{stale['stale_share']:.0%} of the portfolio valued more than {policy['stale_days']} days before the report",
                      f"at most {policy['max_stale_share']:.0%}", "Require refreshed valuations before first drawdown"))
    if stale.get("age_today") is not None and stale["age_today"] > policy["max_weighted_mark_age_days"]:
        f.append(Flag("P12", "condition", "Private marks are old today", f"{stale['age_today']:.0f} days on average",
                      f"at most {policy['max_weighted_mark_age_days']} days", "Size against the rolled-forward estimate and include a valuation challenge right"))
    if overlay["rated_share"] < policy["min_sponsor_coverage"]:
        f.append(Flag("P13", "condition", "Sponsor track record available for too little of the pool", f"{overlay['rated_share']:.0%} of eligible value has a rated sponsor",
                      f"at least {policy['min_sponsor_coverage']:.0%}", "Request sponsor track records directly; public investor data does not cover these managers"))
    else:
        f.append(Flag("P13", "note", "Sponsor track record coverage", f"{overlay['rated_share']:.0%} of eligible value has a rated sponsor",
                      f"at least {policy['min_sponsor_coverage']:.0%}", "Remaining sponsors have no record, or too short a one, in the investor's table"))
    if overlay["weak_share"] > policy["max_weak_sponsor_share"]:
        f.append(Flag("P14", "condition", "Exposure to sponsors rated weak on capital returned", f"{overlay['weak_share']:.0%} of eligible value",
                      f"at most {policy['max_weak_sponsor_share']:.0%}", "Apply a lower advance rate to those holdings or cap them"))
    inv = snapshot_meta.get("investment_level_pct")
    if inv is not None and inv > policy["max_vehicle_investment_level"]:
        f.append(Flag("P15", "condition", "The vehicle is itself drawing on borrowings", f"investment level {inv:.0f}%; undrawn credit line "
                      + (f"${snapshot_meta['undrawn_credit_m']:.0f}m" if snapshot_meta.get("undrawn_credit_m") is not None else "not stated")
                      + (f"; cash ${snapshot_meta['cash_m']:.0f}m" if snapshot_meta.get("cash_m") is not None else ""),
                      f"at most {policy['max_vehicle_investment_level']}%",
                      "Confirm ranking against the vehicle's existing credit facility; this model assumes a first-ranking claim"))
    if quality_counts.get("unreconciled_recent", 0) > policy["max_unreconciled_snapshots"]:
        f.append(Flag("P16", "condition", "Recent reports do not tie to their own totals", f"{quality_counts['unreconciled_recent']} of the latest 12",
                      f"at most {policy['max_unreconciled_snapshots']}", "Query the publisher before relying on the affected months"))
    if limits_bite > 0:
        f.append(Flag("P17", "note", "Concentration limits reduce the borrowing base", f"{limits_bite:,.1f} excluded by the single-name cap and top-{cov.get('top_n')} limit",
                      "n/a", "Loan is sized on eligible NAV after these limits"))
    if runoff_info and runoff_info.get("breakeven_pace") is not None:
        be, assumed = runoff_info["breakeven_pace"], runoff_info["assumed_pace"]
        sev = "condition" if be > 0.8 * assumed else "note"
        f.append(Flag("P18", sev, "Repayment depends on the pace of exits", f"needs {be:.1%} of the pool realised a year to repay by maturity; base case assumes {assumed:.0%}",
                      "breakeven at most 80% of the assumed pace", "Add scheduled amortisation or a maturity extension test; do not rely on exits alone"))
    if not market_ran:
        f.append(Flag("P19", "condition", "Market layer did not run", "no usable price history", "roll-forward available",
                      "Run `navmon refresh` to fetch prices; LTV shown is on reported values only"))
    return f


def decide(candidate_tests: list[dict], flags: list[Flag]) -> tuple[str, dict | None]:
    passing = [c for c in candidate_tests if c["passed"]]
    proposed = max(passing, key=lambda c: c["opening_ltv"]) if passing else None
    if any(fl.severity == "blocker" for fl in flags) or proposed is None:
        return "Decline", proposed
    if any(fl.severity == "condition" for fl in flags):
        return "Proceed with conditions", proposed
    return "Proceed", proposed
