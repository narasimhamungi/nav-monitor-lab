"""Write the outputs: CSV files for every table and the memo that quotes them.

The memo is built from the same result object as the CSVs, so every figure in it can be found in a
named file. tests/test_memo_traceability.py checks that.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from .schema import SEVERITY_ORDER

DISCLAIMER = ("*Illustrative analysis on public data. The loan terms are this tool's assumptions, not observed market terms. "
              "Not a rating, not a valuation, not advice.*")


def money(x, dec: int = 1) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:,.{dec}f}"


def pct(x, dec: int = 1) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return "n/a" if math.isinf(x) else f"{x:.{dec}%}"


def mult(x) -> str:
    return "n/a" if x is None else f"{x:.2f}x"


def _cell(v):
    if isinstance(v, float):
        return "" if math.isnan(v) else ("inf" if math.isinf(v) else round(v, 6))
    return "" if v is None else v


def write_rows(path: Path, rows: list[dict], cols: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = cols or (list(rows[0]) if rows else ["empty"])
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _cell(r.get(k)) for k in cols})
    return path


def write_outputs(r: dict, out: Path) -> list[Path]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    rf_by_key = {x["key"]: x for x in r["roll_forward"]["rows"]}
    ov_by_key = {x["key"]: x for x in r["overlay_rows"]}
    elig_fv = r["pool_summary"]["eligible_fv"]
    pool_rows = []
    for a in r["pool"]:
        rf, ov = rf_by_key.get(a.key, {}), ov_by_key.get(a.key, {})
        pool_rows.append({**a.row(), "share_of_eligible": (a.fair_value / elig_fv) if a.eligible and elig_fv else None,
                          "sponsor_rating": ov.get("rating"), "sponsor_families": ov.get("families"),
                          "proxy": rf.get("proxy"), "proxy_return_since_marks": rf.get("proxy_return"), "estimated_fv": rf.get("estimated_fv")})
    files.append(write_rows(out / "collateral.csv", pool_rows))
    files.append(write_rows(out / "pool_summary.csv", [{"item": k, "value": v} for k, v in r["pool_summary"].items()]
                            + [{"item": "eligible_nav_after_limits", "value": r["grid"]["eligible_nav"]},
                               {"item": "excluded_by_concentration_limits", "value": r["grid"]["excluded_by_limits"]},
                               {"item": "estimated_eligible_nav_after_limits", "value": r["estimated_eligible_nav"]},
                               {"item": "full_pass_through_eligible_nav_after_limits", "value": r["full_pass_through_eligible_nav"]},
                               {"item": "eligible_pool_change_estimated", "value": r["eligible_pool_change_estimated"]},
                               {"item": "eligible_pool_change_full_pass_through", "value": r["eligible_pool_change_full_pass_through"]}]
                            + [{"item": f"sector_share:{k}", "value": v} for k, v in r["sector_mix"].items()]))
    files.append(write_rows(out / "sponsor_overlay.csv", r["overlay_rows"]))
    files.append(write_rows(out / "track_record_funds.csv", [m.row() for m in r["metrics"]]))
    files.append(write_rows(out / "track_record_families.csv", [f.row() for f in r["families"]]))
    files.append(write_rows(out / "track_record_vintages.csv", r["vintages"]))
    files.append(write_rows(out / "sizing_candidates.csv", [
        {**c, "rolled_forward_ltv": r["rolled_ltv"].get(c["opening_ltv"]),
         "full_pass_through_ltv": r["full_pass_through_ltv"].get(c["opening_ltv"]),
         "passed_all_tests": next(t["passed"] for t in r["candidate_tests"] if t["opening_ltv"] == c["opening_ltv"]),
         "failed_tests": "; ".join(x["test"] for t in r["candidate_tests"] if t["opening_ltv"] == c["opening_ltv"] for x in t["tests"] if not x["passed"]),
         "breakeven_exit_pace": r["runoffs"][c["opening_ltv"]]["breakeven_pace"]} for c in r["grid"]["candidates"]]))
    files.append(write_rows(out / "stress_uniform.csv", r["grid"]["uniform"]))
    files.append(write_rows(out / "stress_single_name.csv", r["grid"]["single_name"]))
    files.append(write_rows(out / "stress_scenarios.csv", [{"opening_ltv": l0, **row} for l0, rows in r["scenario_rows"].items() for row in rows]))
    ro_rows, pg_rows = [], []
    for l0, ro in r["runoffs"].items():
        for case in ("base", "drought", "drought_markdown"):
            ro_rows += [{"opening_ltv": l0, "case": case, **row} for row in ro[case]["rows"]]
        pg_rows += [{"opening_ltv": l0, **row} for row in ro["pace_grid"]]
    files.append(write_rows(out / "runoff.csv", ro_rows))
    files.append(write_rows(out / "runoff_pace_grid.csv", pg_rows))
    cal = r["calibration"]
    files.append(write_rows(out / "realisations.csv", [
        {"as_of": x["as_of"].isoformat(), "cash_received_year_to_date": x["ytd"], "basis": x["basis"], "cash_stated_for_month": x["month_stated"],
         "previous_year_stated": x["prior_year_stated"], "running_total": x.get("cumulative"), "cash_in_month": x.get("cash_in_month"),
         "portfolio_fair_value": x["portfolio_fv"], "read_from": x["text"]} for x in r["cash_rows"]]))
    files.append(write_rows(out / "exit_pace_calibration.csv", [
        {"window": w["window"], "start": w["start"].isoformat(), "end": w["end"].isoformat(), "months": w["months"], "cash_received": w["cash"],
         "average_portfolio_fair_value": w["avg_portfolio_fv"], "portfolio_values_averaged": w.get("fv_observations"), "pace_per_year": w["pace"],
         "base_case": cal["source"] == "calibrated" and w["window"] == cal["base_window"], "note": w["note"]} for w in cal["windows"]]
        + [{"window": "base case", "pace_per_year": r["base_pace"], "note": (f"calibrated: {cal['rule']} of the windows" if cal["source"] == "calibrated"
                                                                             else f"assumed: {cal['reason']}")},
           {"window": "former assumption", "pace_per_year": r["former_pace"], "note": "configs/facility.yaml runoff.exit_pace_per_year; sensitivity only"}],
        ["window", "start", "end", "months", "cash_received", "average_portfolio_fair_value", "portfolio_values_averaged", "pace_per_year", "base_case", "note"]))
    sens = []
    for label, pace, ros, tests in (("base case", r["base_pace"], r["runoffs"], r["candidate_tests"]),
                                    ("former assumption", r["former_pace"], r["runoffs_former"], r["former_tests"])):
        for l0, ro in ros.items():
            sens.append({"case": label, "exit_pace_per_year": pace, "opening_ltv": l0, "loan": next(c["loan"] for c in r["grid"]["candidates"] if c["opening_ltv"] == l0),
                         "repaid_quarter": ro["base"]["repaid_quarter"], "balance_at_maturity": ro["base"]["balance_at_maturity"],
                         "drought_balance_at_maturity": ro["drought"]["balance_at_maturity"], "breakeven_exit_pace": ro["breakeven_pace"],
                         "passed_all_tests": next(t["passed"] for t in tests if t["opening_ltv"] == l0)})
    files.append(write_rows(out / "runoff_sensitivity.csv", sens))
    files.append(write_rows(out / "roll_forward.csv", r["roll_forward"]["rows"]))
    if r["backtest"]:
        files.append(write_rows(out / "backtest_periods.csv", r["accuracy"]["periods"]))
        files.append(write_rows(out / "backtest_observations.csv", r["backtest"]["observations"]))
        files.append(write_rows(out / "backtest_skipped.csv", r["backtest"]["skipped"], ["from", "to", "company", "reason"]))
        files.append(write_rows(out / "backtest_summary.csv", [{"item": k, "value": v} for k, v in r["accuracy"].items() if k != "periods"]
                                + [{"item": "verdict", "value": r["backtest"]["verdict"]}]))
        files.append(write_rows(out / "backtest_robustness.csv", r["backtest"]["robustness"]))
    if r["replay"]:
        files.append(write_rows(out / "covenant_replay.csv", r["replay"]["rows"]))
        files.append(write_rows(out / "covenant_replay_summary.csv", r["replay"]["summary"]))
    if r["changes"]:
        files.append(write_rows(out / "changes.csv", r["changes"]["rows"]))
        files.append(write_rows(out / "changes_sectors.csv", r["changes"]["sectors"]))
    files.append(write_rows(out / "findings.csv", [f.row() for f in r["findings"]],
                            ["severity", "code", "scope", "message", "observed", "threshold"]))
    rec = {"verdict": r["verdict"], "proposed": r["proposed"], "flags": [f.row() for f in r["flags"]], "candidate_tests": r["candidate_tests"],
           "pass_through": r["pass_through"], "pass_through_source": r["pass_through_source"], "base_rate_pct": r["base_rate"],
           "all_in_rate_pct": r["all_in_rate"], "discount_to_nav": r["discount"],
           "exit_pace": {"base_pace": r["base_pace"], "source": cal["source"], "rule": cal["rule"], "base_window": cal["base_window"],
                         "windows_end": cal["end"], "former_assumption": r["former_pace"], "reason": cal.get("reason", "")},
           "former_assumption_result": {"proposed": r["former_proposed"]}}
    (out / "recommendation.json").write_text(json.dumps(rec, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    files.append(out / "recommendation.json")
    (out / "memo.md").write_text(build_memo(r), encoding="utf-8", newline="\n")
    files.append(out / "memo.md")
    return files


# ---------------------------------------------------------------- memo

def _status_mark(status: str) -> str:
    return {"ok": "", "cash sweep": " (sweep)", "breach": " (BREACH)"}.get(status, f" ({status})")


def build_memo(r: dict) -> str:
    s, ps, cov, fac = r["snapshot"], r["pool_summary"], r["cfg"]["facility"]["covenants"], r["cfg"]["facility"]
    ro_cfg, policy = fac["runoff"], fac["policy"]
    grid, rf, tr = r["grid"], r["roll_forward"], r["track_record"]
    unit = f"{s.currency} {s.unit}"
    prop = r["proposed"]
    L: list[str] = []
    add = L.append
    add(f"# NAV facility memo: {r['vehicle_name']} ({r['vehicle']})")
    add("")
    add(DISCLAIMER)
    add("")
    add(f"**Figures in {unit} unless stated.** Holdings as of {s.as_of.isoformat()}"
        + (f" (published {s.published.isoformat()})" if s.published else "")
        + f"; {r['history_n']} monthly reports from {r['history_start'].isoformat()}. Sponsor records: {tr.lp} {tr.program}, as of {tr.as_of.isoformat()}. "
        + (f"Prices to {rf['to'].isoformat()}. " if rf["ran"] else "No market data in this run. ")
        + (f"Base rate {r['base_rate_series']} {r['base_rate']:.2f}% on {r['base_rate_date'].isoformat()}." if r["base_rate_date"] else ""))
    add("")

    # 1 ------------------------------------------------------------
    add("## 1. Recommendation")
    add("")
    if prop:
        l0 = prop["opening_ltv"]
        add(f"**{r['verdict']}.** Opening LTV {pct(l0, 0)}: a loan of {money(prop['loan'])} against eligible NAV of {money(grid['eligible_nav'])} "
            f"({pct(grid['eligible_nav'] / ps['implied_portfolio_fv']) if ps['implied_portfolio_fv'] else 'n/a'} of the vehicle's "
            f"{money(ps['implied_portfolio_fv'], 0)} portfolio).")
    else:
        add(f"**{r['verdict']}.** No opening LTV on the grid passes every sizing test.")
    add("")
    add("| Term | Proposed | Basis |")
    add("|---|---|---|")
    if prop:
        add(f"| Opening LTV / loan | {pct(prop['opening_ltv'], 0)} / {money(prop['loan'])} | highest grid point that passes every test in sections 4 to 6 |")
    add(f"| Cash sweep / breach / cure-to | {pct(cov['ltv_sweep'], 0)} / {pct(cov['ltv_breach'], 0)} / {pct(cov['ltv_target'], 0)} | breach level from published agency commentary (initial 10-30%, maximum about 40%); sweep and cure are assumptions |")
    add(f"| Single-name cap / top-{cov.get('top_n')} limit / minimum names | {pct(cov['single_asset_cap'])} / {pct(cov.get('top_n_share'), 0)} / {cov.get('min_assets')} | assumptions |")
    add(f"| Indicative all-in rate | {r['all_in_rate']:.2f}% | {r['base_rate_series']} {r['base_rate']:.2f}% + {ro_cfg['margin_pct']}% margin (margin is an assumption) |")
    add(f"| Tenor | {ro_cfg['tenor_years']} years | assumption |")
    add(f"| Excluded from the pool | {ps['excluded_names']} names, {money(ps['excluded_fv'])} | names or sponsors the publisher does not disclose |")
    add("")
    conds = [f for f in r["flags"] if f.severity in ("blocker", "condition")]
    notes = [f for f in r["flags"] if f.severity == "note"]
    if conds:
        add("**Conditions**")
        add("")
        for f in conds:
            add(f"- **{f.title}** ({f.code}). Observed: {f.observed}. Policy: {f.threshold}. Action: {f.action}.")
        add("")
    if notes:
        add("**Notes**")
        add("")
        for f in notes:
            add(f"- {f.title} ({f.code}): {f.observed}.")
        add("")
    higher = [c for c in r["candidate_tests"] if prop and c["opening_ltv"] > prop["opening_ltv"] and not c["passed"]]
    if higher:
        c = min(higher, key=lambda x: x["opening_ltv"])
        add(f"**Why not {pct(c['opening_ltv'], 0)}:** " + "; ".join(f"{t['test'].lower()} fails ({t['detail']})" for t in c["tests"] if not t["passed"]) + ".")
        add("")

    # 2 ------------------------------------------------------------
    add("## 2. Collateral pool (`collateral.csv`, `pool_summary.csv`)")
    add("")
    add(f"- Published: {ps['published_names']} holdings worth {money(ps['published_fv'])}; the publisher states {money(ps['stated_total_fv'])}, "
        f"{pct(ps['stated_share_of_portfolio'])} of the portfolio. Holdings outside the published table get no credit.")
    add(f"- Eligible: {ps['eligible_names']} names, {money(ps['eligible_fv'])}. Concentration limits remove a further {money(grid['excluded_by_limits'])}, "
        f"leaving eligible NAV of {money(grid['eligible_nav'])}.")
    add(f"- Concentration: largest name {pct(ps['eligible_top1'])}, top five {pct(ps['eligible_top5'])}, top ten {pct(ps['eligible_top10'])} of eligible value; "
        f"equivalent to {ps['eligible_effective_names']:.1f} equal-sized names. Quoted holdings are {pct(ps['listed_share_of_eligible'])}.")
    add("- Sectors: " + ", ".join(f"{k} {pct(v, 0)}" for k, v in r["sector_mix"].items()) + ".")
    mix = ", ".join(f"{pct(w, 0)} at {d.isoformat()}" for d, w in sorted(s.valuation_mix, reverse=True))
    add(f"- Age of marks: {mix}. Average age {r['stale']['age_at_report']:.0f} days at the report date"
        + (f", {r['stale']['age_today']:.0f} days for the private marks as of {rf['to'].isoformat()}" if r["stale"]["age_today"] is not None else "") + ".")
    liq = []
    if s.cash_m is not None:
        liq.append(f"cash {money(s.cash_m, 0)}")
    if s.undrawn_credit_m is not None:
        liq.append(f"undrawn credit line {money(s.undrawn_credit_m, 0)}")
    if s.investment_level_pct is not None:
        liq.append(f"investment level {s.investment_level_pct:.0f}%")
    if liq:
        add("- Vehicle liquidity as published: " + ", ".join(liq) + ".")
    add("")
    add("| Largest eligible holdings | Lead sponsor | Sector | Fair value | Share | Sponsor record | Est. today |")
    add("|---|---|---|---|---|---|---|")
    rf_by, ov_by = {x["key"]: x for x in rf["rows"]}, {x["key"]: x for x in r["overlay_rows"]}
    for a in [a for a in r["pool"] if a.eligible][:10]:
        est = rf_by.get(a.key, {}).get("estimated_fv")
        add(f"| {a.company} | {a.sponsor} | {a.sector} | {money(a.fair_value)} | {pct(a.fair_value / ps['eligible_fv'])} | "
            f"{ov_by[a.key]['rating']} | {money(est)} |")
    add("")

    # 3 ------------------------------------------------------------
    o, tc = r["overlay"], r["track_coverage"]
    add("## 3. Sponsor track record (`sponsor_overlay.csv`, `track_record_families.csv`)")
    add("")
    add(f"Source: {tr.lp}'s table of {tc['funds']} active partnerships. The fund-name-to-manager map covers {tc['mapped_funds']} funds "
        f"({pct(tc['mapped_share_of_remaining_value'], 0)} of remaining value); {tc['inferred_funds']} of those are mapped by inference. "
        "Ratings compare how fast a manager has returned capital with other funds of the same vintage year in this one investor's book.")
    add("")
    add(f"Of eligible value: {pct(o['rated_share'], 0)} has a rated sponsor ({pct(o['strong_share'], 0)} strong, {pct(o['adequate_share'], 0)} adequate, "
        f"{pct(o['weak_share'], 0)} weak); {pct(o['insufficient_share'], 0)} has a sponsor with too short a record; "
        f"{pct(o['no_record_share'], 0)} has a sponsor with no funds in the table.")
    add("")
    matched = [x for x in r["overlay_rows"] if x["eligible"] and x["rating"] != "no record"]
    if matched:
        add("| Holding | Sponsor | Fair value | Rating | Older funds' DPI | Capital-returned rank | Map basis |")
        add("|---|---|---|---|---|---|---|")
        for x in matched:
            add(f"| {x['company']} | {x['sponsor']} | {money(x['fair_value'])} | {x['rating']} | {mult(x['pooled_mature_dpi'])} | "
                f"{'n/a' if x['median_dpi_rank'] is None else format(x['median_dpi_rank'], '.2f')} | {x['mapping_basis']} |")
        add("")

    # 4 ------------------------------------------------------------
    add("## 4. Stress (`stress_uniform.csv`, `stress_scenarios.csv`, `stress_single_name.csv`)")
    add("")
    dds = fac["sizing"]["drawdown_grid"]
    add("LTV after a uniform fall in the pool, by opening LTV:")
    add("")
    add("| Opening LTV | Loan | " + " | ".join(f"-{pct(d, 0)}" if d else "Today" for d in dds) + " | Fall to breach |")
    add("|---|---|" + "---|" * (len(dds) + 1))
    for c in grid["candidates"]:
        cells = []
        for d in dds:
            u = next(x for x in grid["uniform"] if x["opening_ltv"] == c["opening_ltv"] and x["drawdown"] == d)
            cells.append(f"{pct(u['ltv'])}{_status_mark(u['status'])}")
        star = " *" if prop and c["opening_ltv"] == prop["opening_ltv"] else ""
        add(f"| {pct(c['opening_ltv'], 0)}{star} | {money(c['loan'])} | " + " | ".join(cells) + f" | {pct(c['drawdown_to_breach'])} |")
    add("")
    if prop:
        l0 = prop["opening_ltv"]
        add(f"Sector scenarios on the proposed loan ({pct(l0, 0)} opening LTV, marked * above):")
        add("")
        add("| Scenario | Pool falls | LTV | Status | Write-downs |")
        add("|---|---|---|---|---|")
        for x in r["scenario_rows"][l0]:
            add(f"| {x['scenario']} | {pct(x['pool_fall'])} | {pct(x['ltv'])} | {x['status']} | {x['shocks']} |")
        add("")
        sn = [x for x in grid["single_name"] if x["opening_ltv"] == l0]
        add("Largest names written off in full: " + "; ".join(
            f"{x['assets_written_down']} ({x['names'].split(', ')[-1]} added) LTV {pct(x['ltv'])}, {x['status']}" for x in sn) + ".")
        add("")

    # 5 ------------------------------------------------------------
    add("## 5. Repayment from exits (`realisations.csv`, `exit_pace_calibration.csv`, `runoff.csv`, `runoff_pace_grid.csv`, `runoff_sensitivity.csv`)")
    add("")
    cal, base_pace, former = r["calibration"], r["base_pace"], r["former_pace"]
    known = [x for x in r["cash_rows"] if x["ytd"] is not None]
    if cal["source"] == "calibrated":
        add(f"**Exit pace: {pct(base_pace)} a year, calibrated from the vehicle's own reports.** Pace = cash received from realisations over a "
            "window, divided by the average portfolio fair value over the same months, annualised. The denominator is the fair value of the "
            "whole portfolio, not NAV and not the eligible pool; the model applies that pace to the eligible pool (assumption). Only cash the "
            "publisher says it received is counted; announced, pending and pro forma amounts are not.")
        add("")
        add("| Window | Months | Cash received | Average portfolio value | Pace a year |")
        add("|---|---|---|---|---|")
        for w in cal["windows"]:
            star = " *" if w["window"] == cal["base_window"] else ""
            if w["pace"] is None:
                add(f"| {w['window']} to {w['end'].isoformat()} | {w['months']} | n/a | n/a | not computed: {w['note']} |")
            else:
                label = f"all, from {w['start'].year + 1}-01-01" if w["window"] == "all" else w["window"]
                add(f"| {label} to {w['end'].isoformat()}{star} | {w['months']} | {money(w['cash'], 0)} | {money(w['avg_portfolio_fv'], 0)} | {pct(w['pace'])} |")
        add("")
        add(f"- Base case (*): the {cal['rule']} of the windows, a rule set in `configs/facility.yaml`. The former assumption was {pct(former, 0)}.")
    else:
        add(f"**Exit pace: {pct(base_pace)} a year, an assumption.** It could not be calibrated from the vehicle's reports: {cal.get('reason') or 'no reason recorded'}.")
        add("")
    if known:
        years: dict[int, dict] = {}
        for x in known:
            years[x["as_of"].year] = x
        add("- Cash received by calendar year: " + "; ".join(
            f"{y} {money(x['ytd'], 0)}" + ("" if x["as_of"].month == 12 else f" to {x['as_of'].isoformat()}") for y, x in sorted(years.items())) + ".")
    missing = [x["as_of"].isoformat() for x in r["cash_rows"] if x["ytd"] is None]
    if missing:
        add(f"- Not stated: {len(missing)} of {len(r['cash_rows'])} reports give no figure for cash received ({', '.join(missing)}). "
            "The running total picks up at the next report that does.")
    if cal.get("end") and cal.get("reports_after_end"):
        add(f"- The latest report ({s.as_of.isoformat()}) is one of them, so the windows end at {cal['end'].isoformat()}"
            + (", where the running total is the last stated year-to-date figure plus the monthly figures since." if cal.get("end_basis") == "derived" else "."))
    ties = [f for f in r["findings"] if f.code in ("R02", "R03", "R04")]
    if ties:
        add(f"- The publisher's own figures do not tie in {len(ties)} place{'s' if len(ties) != 1 else ''}: "
            + "; ".join(f"{f.scope}: {f.observed}" for f in ties[:3]) + ". Reported as found; the stated year-to-date figure is used.")
    add("")
    if prop:
        ro = r["runoffs"][prop["opening_ltv"]]
        add(f"The loan is repaid from sale proceeds: {pct(base_pace)} of the pool realised a year ({'calibrated base case' if cal['source'] == 'calibrated' else 'assumption'}), "
            f"{pct(ro_cfg['sweep_share_below_trigger'], 0)} of proceeds after interest applied to principal (assumption), all of it once LTV reaches the sweep level.")
        add("")
        add("| Case | Repaid | Outstanding at maturity | Peak LTV | Interest added to the loan |")
        add("|---|---|---|---|---|")
        dr = ro_cfg["drought"]
        labels = {"base": "Base pace", "drought": f"Exits at {pct(dr['pace_multiplier'], 0)} of pace for {dr['quarters']} quarters",
                  "drought_markdown": f"Same drought plus a {pct(dr['markdown'], 0)} markdown on day one"}
        for case, label in labels.items():
            x = ro[case]
            add(f"| {label} | {'quarter ' + str(x['repaid_quarter']) if x['repaid_quarter'] else 'not by maturity'} | {money(x['balance_at_maturity'])} | "
                f"{pct(x['peak_ltv'])}{' (BREACH)' if x['breached'] else ''} | {money(x['interest_capitalised'])} |")
        add("")
        add(f"Breakeven: the pool must realise {pct(ro['breakeven_pace'])} a year for the loan to be repaid by maturity. By pace: "
            + "; ".join(f"{pct(x['pace'], 0)} leaves {money(x['balance_at_maturity'])}" for x in ro["pace_grid"]) + ".")
        add("")
    if cal["source"] == "calibrated":
        fp = r["former_proposed"]
        add(f"Sensitivity: the same rules on the former assumption of {pct(former, 0)} a year, beside the base case. Outstanding at maturity, base repayment case:")
        add("")
        add(f"| Opening LTV | Loan | Base case {pct(base_pace)} | Former assumption {pct(former, 0)} | Breakeven pace |")
        add("|---|---|---|---|---|")

        def _cellro(x: dict, passed: bool) -> str:
            body = f"repaid in quarter {x['repaid_quarter']}" if x["repaid_quarter"] else f"{money(x['balance_at_maturity'])} outstanding"
            return body + ("" if passed else " (fails a test)")
        for c in grid["candidates"]:
            l0 = c["opening_ltv"]
            p_base = next(t["passed"] for t in r["candidate_tests"] if t["opening_ltv"] == l0)
            p_former = next(t["passed"] for t in r["former_tests"] if t["opening_ltv"] == l0)
            add(f"| {pct(l0, 0)} | {money(c['loan'])} | {_cellro(r['runoffs'][l0]['base'], p_base)} | {_cellro(r['runoffs_former'][l0]['base'], p_former)} | "
                f"{pct(r['runoffs'][l0]['breakeven_pace'])} |")
        add("")
        add("Proposed loan: " + (f"{pct(prop['opening_ltv'], 0)} ({money(prop['loan'])}) on the base case" if prop else "none on the base case")
            + "; " + (f"{pct(fp['opening_ltv'], 0)} ({money(fp['loan'])}) on the former assumption." if fp else "none on the former assumption."))
        add("")

    # 6 ------------------------------------------------------------
    add("## 6. Market layer (`roll_forward.csv`, `backtest_periods.csv`, `covenant_replay_summary.csv`)")
    add("")
    if rf["ran"]:
        est = r["estimated_eligible_nav"]
        add(f"- **Rolled-forward estimate, not a valuation.** Private marks are moved by {r['pass_through']:.2f} of their listed sector proxy's return "
            f"since the valuation dates ({r['pass_through_source']}); quoted holdings move one-for-one from the report date.")
        add(f"- Eligible holdings move {pct(r['eligible_pool_change_estimated'], 1)} on the estimate. Eligible NAV after concentration limits: "
            f"{money(grid['eligible_nav'])} as reported, {money(est)} estimated at {rf['to'].isoformat()} ({pct(est / grid['eligible_nav'] - 1, 1)})."
            + (f" LTV on the proposed loan: {pct(prop['opening_ltv'])} reported, {pct(r['rolled_ltv'][prop['opening_ltv']])} estimated." if prop else ""))
        fe = r["full_pass_through_eligible_nav"]
        add(f"- Outer bound: if private marks had moved one-for-one with their listed proxies, eligible holdings would have moved "
            f"{pct(r['eligible_pool_change_full_pass_through'], 1)} and eligible NAV {money(fe)} ({pct(fe / grid['eligible_nav'] - 1, 1)}; "
            "the concentration limits absorb part of a fall in the largest names)"
            + (f" and LTV {pct(r['full_pass_through_ltv'][prop['opening_ltv']])}." if prop else "."))
        d = r["discount"]
        if d:
            add(f"- The market's own haircut: {d['symbol']} closed at {d['share_price']:.2f} on {d['price_date']} against NAV per share of "
                f"{d['nav_per_share']:.2f} at {d['nav_date']}, a discount of {pct(d['discount'])}. The proposed loan breaches only if the pool "
                + (f"falls {pct(next(c['drawdown_to_breach'] for c in grid['candidates'] if c['opening_ltv'] == prop['opening_ltv']))}. " if prop else "falls far further. ")
                + "A discount also reflects fees, borrowing and liquidity, so it is context only.")
        a = r["accuracy"]
        if a:
            add(f"- Backtest on this vehicle's own history: {a['n_periods']} valuation cycles, {a['n_observations']} company observations. "
                f"Average error in the quarterly move of the matched holdings: {pct(a['mae_no_adjustment'], 2)} carrying stale marks, "
                f"{pct(a['mae_full_pass_through'], 2)} passing the listed move through in full, {pct(a['mae_fitted_in_sample'], 2)} with the fitted factor "
                f"of {a['beta_in_sample']:.2f} (in-sample).")
            if a["n_walk_forward"]:
                add(f"- Out of sample ({a['n_walk_forward']} cycles, factor fitted on earlier cycles only): {pct(a['mae_walk_forward'], 2)}, against "
                    f"{pct(a['mae_no_adjustment_same_periods'], 2)} for stale marks and {pct(a['mae_full_pass_through_same_periods'], 2)} for full pass-through "
                    f"on the same cycles. Correlation with the proxy is {a['correlation_period_level']:.2f} at portfolio level and "
                    f"{a['correlation_name_level']:.2f} company by company.")
            rob = r["backtest"]["robustness"]
            if rob:
                betas = [x["beta_in_sample"] for x in rob if x["beta_in_sample"] is not None]
                add(f"- Robustness (`backtest_robustness.csv`): repeated on {len(rob)} different sets of reporting months, the fitted factor ranges "
                    f"from {min(betas):.2f} to {max(betas):.2f} and {r['backtest']['verdict']}. Full pass-through was the worst option every time "
                    f"(error {pct(min(x['mae_full_pass_through'] for x in rob), 1)} to {pct(max(x['mae_full_pass_through'] for x in rob), 1)}). "
                    "Read the estimate as a direction check on the pool, not as a number to lend against.")
        if r["replay"]:
            add("")
            add(f"Covenant replay: a loan fixed at the {r['replay']['summary'][0]['start']} report and never repaid, tracked to {r['replay']['summary'][0]['end']}:")
            add("")
            add("| Opening LTV | Peak LTV, reported | Peak LTV, estimated | Peak LTV, full pass-through | First sweep (full pass-through) | Any breach |")
            add("|---|---|---|---|---|---|")
            for x in r["replay"]["summary"]:
                breach = [k for k in ("reported", "estimated", "full") if x[f"first_{k}_breach"]]
                add(f"| {pct(x['opening_ltv'], 0)} | {pct(x['peak_ltv_reported'])} ({x['peak_date_reported']}) | {pct(x['peak_ltv_estimated'])} | "
                    f"{pct(x['peak_ltv_full'])} ({x['peak_date_full']}) | {x['first_full_sweep'] or 'none'} | {', '.join(breach) or 'none'} |")
    else:
        add("Not run: no usable price history in the data directory. Run `navmon refresh` and then `navmon run`.")
    add("")

    # 7 ------------------------------------------------------------
    ch = r["changes"]
    add("## 7. Changes since the previous report (`changes.csv`, `changes_sectors.csv`)")
    add("")
    if ch:
        p, c = ch["prev"], ch["cur"]
        add(f"From {p['as_of']} to {c['as_of']}:")
        add("")
        add(f"- Published holdings {money(p['published_fv'])} to {money(c['published_fv'])}; names held in both months moved {pct(ch['held_value_change'])}. "
            f"NAV per share {money(p['nav_per_share_usd'], 2)} to {money(c['nav_per_share_usd'], 2)}.")
        add(f"- Entered: {', '.join(ch['entered']) or 'none'}. Left: {', '.join(ch['left']) or 'none'}.")
        if ch["movers"]:
            add(f"- Moves of {pct(ch['mover_threshold'], 0)} or more: " + "; ".join(
                f"{x['company']}{' (undisclosed, matched by label)' if x['undisclosed'] else ''} {money(x['fv_prev'])} to {money(x['fv_cur'])} "
                f"({x['change']:+.1%})" for x in ch["movers"]) + ".")
        else:
            add(f"- No held name moved by {pct(ch['mover_threshold'], 0)} or more.")
        watch = [x for x in ch["watch"] if x["status"] == "held"]
        if watch:
            add("- Watchlist: " + "; ".join(f"{x['company']} {x['change']:+.1%}" for x in watch) + ".")
        add(f"- Top five share of published value {pct(ch['concentration_prev']['top5'])} to {pct(ch['concentration_cur']['top5'])}.")
        big = [x for x in ch["sectors"] if abs(x["change_pp"]) >= 1.0][:3]
        if big:
            add("- Sector shifts of a point or more: " + "; ".join(f"{x['sector']} {x['change_pp']:+.1f} points" for x in big) + ".")
        l0, l1 = [], []
        for k, lab in (("cash_m", "cash"), ("undrawn_credit_m", "undrawn line"), ("investment_level_pct", "investment level")):
            if p[k] is not None and c[k] is not None:
                l0.append(f"{lab} {p[k]:g}"); l1.append(f"{c[k]:g}")
        if l0:
            add("- Vehicle liquidity: " + "; ".join(f"{a} to {b}" for a, b in zip(l0, l1)) + ".")
    else:
        add("First report in the data set; nothing to compare.")
    add("")

    # 8 ------------------------------------------------------------
    add("## 8. Data-quality findings (`findings.csv`)")
    add("")
    fc = r["finding_counts"]
    add(f"{fc.get('error', 0)} errors, {fc.get('warn', 0)} warnings, {fc.get('info', 0)} notes. Nothing was corrected; these are reported as found.")
    add("")
    by_code: dict[tuple, list] = {}
    for f in r["findings"]:
        if f.severity in ("error", "warn"):
            by_code.setdefault((f.severity, f.code, f.message), []).append(f)
    for (sev, code, msg), fs in sorted(by_code.items(), key=lambda kv: (SEVERITY_ORDER[kv[0][0]], kv[0][1])):
        ex = "; ".join(f"{f.scope}: {f.observed}" if f.observed else f.scope for f in fs[:3])
        add(f"- **{code}** ({sev}, {len(fs)}): {msg}. {ex}{' ...' if len(fs) > 3 else ''}")
    add("")

    # 9 ------------------------------------------------------------
    add("## 9. Limits")
    add("")
    add(f"- The collateral is a listed vehicle's published top holdings, not a private fund asking for a loan. No fund documents, covenants in "
        "place, company financials or valuation reports were seen.")
    add("- The vehicle has its own credit facility; ranking against it is not modelled.")
    add(f"- Sponsor records come from one investor ({tr.lp}), active funds only, with interim values. That is a biased sample, not a market benchmark.")
    add("- The roll-forward is an estimate from listed sector funds. Published fair-value changes also contain follow-on investments, "
        "part-realisations and currency moves, which the backtest cannot separate.")
    add("- Thresholds, margins, sweep shares and concentration limits are assumptions set in `configs/facility.yaml`."
        + (" The exit pace is the whole portfolio's, from the publisher's statements of cash received; applying it to the eligible pool, and to the "
           "next four years, is an assumption." if r["calibration"]["source"] == "calibrated" else " So is the exit pace."))
    add("- Full list: `docs/limitations.md`.")
    add("")
    return "\n".join(L)
