"""Cash received from realisations: the reader, the reconciliation and the exit-pace calibration.

The reader is tested against every NBPE report in the sample (55 reports, real text), and the expected values
below were written by reading those reports, not by running the code.
"""
import json
import shutil
from datetime import date

import pytest

from conftest import FIXTURES, SAMPLE, fixture_text
from navmonitorlab import pipeline, realisations as R, recommend, refresh, report
from navmonitorlab.htmltable import parse
from navmonitorlab.schema import Snapshot
from navmonitorlab.sources.fca_nsm import parse_announcement
from navmonitorlab.sources.files import FileHoldings, save_snapshots

# as_of: (cash received year to date, cash received in the month, previous year's total). None = the report does not say.
BY_EYE = {
    "2022-02-28": (None, None, None), "2022-03-31": (None, None, None), "2022-04-30": (None, None, None),
    "2022-05-31": (56, None, None), "2022-06-30": (67, 11, None), "2022-07-31": (67, None, None), "2022-08-31": (77, None, None),
    "2022-09-30": (84, None, None), "2022-10-31": (108, None, None), "2022-11-30": (113, None, None), "2022-12-31": (120, None, None),
    "2023-01-31": (None, None, None), "2023-02-28": (None, None, None), "2023-03-31": (37, None, None), "2023-04-30": (40, None, None),
    "2023-05-31": (41, None, None), "2023-06-30": (45, None, None), "2023-07-31": (57, None, None), "2023-08-31": (60, None, None),
    "2023-09-30": (70, None, None), "2023-10-31": (110, None, None), "2023-11-30": (118, None, None), "2023-12-31": (171, None, None),
    "2024-01-31": (None, 38, None), "2024-02-29": (38, None, None), "2024-03-31": (64, None, 171), "2024-04-30": (70, None, None),
    "2024-05-31": (122, 52, None), "2024-06-30": (126, None, None), "2024-07-31": (153, 27, None), "2024-08-31": (158, 5, None),
    "2024-09-30": (160, None, None), "2024-10-31": (161, None, None), "2024-11-30": (168, None, None), "2024-12-31": (179, None, None),
    "2025-01-31": (3, 3, None), "2025-02-28": (29, 26, None), "2025-03-31": (47, None, 179), "2025-04-30": (53, 6, None),
    "2025-05-31": (66, 8, None), "2025-06-30": (68, None, None), "2025-07-31": (71, None, None), "2025-08-31": (86, None, None),
    "2025-09-30": (101, 15, None), "2025-10-31": (None, None, None), "2025-11-30": (157, None, None), "2025-12-31": (180, 22, None),
    "2026-01-31": (4, 4, None), "2026-02-28": (None, 6, None), "2026-03-31": (None, None, 180), "2026-04-30": (28, 18, None),
    "2026-05-31": (None, 25, None), "2026-06-30": (None, 35, None), "2026-07-31": (None, 1, None), "2026-08-31": (None, None, None),
}
CAL = {"windows_months": [12, 24, "all"], "base_rule": "lowest", "min_months": 12}


@pytest.fixture(scope="module")
def patterns(cfg):
    return R.compile_patterns(cfg["vehicle"]["live"]["realisations"])


@pytest.fixture(scope="module")
def reports():
    return json.loads(fixture_text("nbpe_realisation_lines.json"))["reports"]


def read(text, as_of, patterns):
    got, findings = R.read_statements(text, as_of, patterns)
    return (got["realised_ytd_m"], got["realised_month_m"], got["realised_prior_year_m"]), findings


def test_reader_agrees_with_a_reading_by_eye_of_all_55_reports(reports, patterns):
    assert len(reports) == len(BY_EYE) == 55
    for rep in reports:
        got, findings = read("\n".join(rep["lines"]), date.fromisoformat(rep["as_of"]), patterns)
        assert got == BY_EYE[rep["as_of"]], rep["as_of"]
        assert not [f for f in findings if f.code == "R06"], rep["as_of"]


def test_the_shipped_sample_carries_exactly_those_figures(snaps):
    assert {s.as_of.isoformat(): (s.realised_ytd_m, s.realised_month_m, s.realised_prior_year_m) for s in snaps} == BY_EYE
    assert all(bool(s.realised_text) == (s.realised_ytd_m is not None or s.realised_month_m is not None or s.realised_prior_year_m is not None)
               for s in snaps)


@pytest.mark.parametrize("line", [
    "$54 million of realisations announced during 2022",                                               # announced, not received
    "2022 year to date announced realisations of $110 milllion1",
    "Total announced portfolio realisations year to date of $80 million",
    "2023 year to date announced cash proceeds of $148 milllion3",
    "$143 million of announced realisations during 2022",
    "Pro forma for expected cash receipts from realisations in June 2023, NBPE expects total cash realisations to be $55 million",
    "On a pro forma basis for 2026, NBPE's total realisations would be $150m",
    "A further $16 million of proceeds from previously announced realisations expected in the coming months",
    "At 31 July 2026, there was approximately $61 million of pending realisations",
    "$64 million of realisations in October",                                                          # mixes cash with deals closed but unpaid
    "~$13 million received during the month from the partial realisation of Tendam",                   # one item, not the month
    "$3 million of proceeds received from Bending Spoons in connection with the company's IPO received in August",
    "$41 million of additional realisations from the closing of Cotiviti was received in May 2024",
    "$104 million committed to new investments year-to-date",
    "Year-to-date, NBPE has returned $74 million to shareholders through dividends and buybacks",
    "2.6% NAV increase ($32 million) from Q2 private valuation information received during the month",
])
def test_announced_pending_pro_forma_and_single_items_are_never_read(line, patterns):
    for as_of in (date(2022, 6, 30), date(2023, 6, 30), date(2024, 5, 31), date(2025, 8, 31), date(2025, 10, 31), date(2026, 8, 31)):
        assert read(line, as_of, patterns)[0] == (None, None, None)


def test_real_html_goes_through_the_page_reader_to_the_same_figures(patterns):
    """The live path: HTML -> text -> figures. Footnote marks sit in <sup> and must not disturb the amounts."""
    frag = json.loads(fixture_text("nbpe_realisation_html.json"))["reports"]
    want = {"2022-06-30": (67, 11, None), "2024-01-31": (None, 38, None), "2024-03-31": (None, None, 171),
            "2025-05-31": (66, 8, None), "2025-08-31": (86, None, None), "2026-07-31": (None, 1, None)}
    assert set(frag) == set(want)
    for as_of, item in frag.items():
        _, text = parse("<html><body>" + "".join(item["html"]) + "</body></html>")
        assert read(text, date.fromisoformat(as_of), patterns)[0] == want[as_of], as_of
    assert "<sup>1</sup>" in "".join(frag["2024-01-31"]["html"])


def test_the_announcement_parser_reads_cash_received_from_a_real_page(cfg, patterns):
    html = fixture_text("nbpe_2026-04_excerpt.html")
    snap, _ = parse_announcement(html, vehicle="NBPE", source_url="x", published=date(2026, 5, 27), realisation_patterns=patterns)
    assert (snap.realised_ytd_m, snap.realised_month_m, snap.realised_prior_year_m) == (28, 18, None)
    assert snap.realised_text == "Year-to-date realisations total $28 million | $18 million of realisation proceeds received in April 2026"
    plain, _ = parse_announcement(html, vehicle="NBPE", source_url="x", published=date(2026, 5, 27))
    assert plain.realised_ytd_m is None and plain.realised_text == ""            # off unless the vehicle config asks for it


def test_a_figure_must_be_dated_to_the_report(patterns):
    line = "$56 million of cash from realisations received through 31 May 2022"
    assert read(line, date(2022, 5, 31), patterns)[0] == (56, None, None)
    got, findings = read(line, date(2022, 6, 30), patterns)
    assert got == (None, None, None) and [f.code for f in findings] == ["R05"]
    assert read("$11 million of proceeds received during June", date(2022, 7, 31), patterns)[0] == (None, None, None)     # wrong month
    assert read("$60 million received during 2023", date(2024, 8, 31), patterns)[0] == (None, None, 60)                   # last year's total
    assert read("$60 million received during 2023", date(2025, 8, 31), patterns)[0] == (None, None, None)                 # neither year
    got, findings = read("$47 million of proceeds received in the first three months of 2025", date(2025, 4, 30), patterns)
    assert got == (None, None, None) and findings[0].code == "R05"                                                         # not a March report


def test_two_different_figures_for_the_same_thing_are_a_conflict_and_neither_is_used(patterns):
    got, findings = read("$70 million of realisations received year to date\n$75 million of proceeds received year to date", date(2024, 4, 30), patterns)
    assert got == (None, None, None) and findings[0].code == "R06" and findings[0].severity == "warn"
    same, findings = read("$70 million of realisations received year to date\n$70 million of proceeds received year-to-date", date(2024, 4, 30), patterns)
    assert same == (70, None, None) and not findings


def test_an_unknown_statement_kind_in_the_config_is_an_error():
    with pytest.raises(ValueError, match="unknown statement kind"):
        R.compile_patterns({"quarter": ["{amt} received"]})


def test_cash_series_on_the_sample(snaps):
    rows, findings = R.cash_series(snaps)
    by = {r["as_of"].isoformat(): r for r in rows}
    assert R.year_totals(rows) == {2022: 120, 2023: 171, 2024: 179, 2025: 180}
    assert (by["2024-01-31"]["ytd"], by["2024-01-31"]["basis"]) == (38, "derived")                 # January: the month is the year to date
    assert [(by[d]["ytd"], by[d]["basis"]) for d in ("2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31")] == \
        [(28, "stated"), (53, "derived"), (88, "derived"), (89, "derived")]
    assert by["2026-03-31"]["ytd"] is None and by["2026-08-31"]["ytd"] is None
    assert by["2022-12-31"]["cumulative"] == 120 and by["2025-12-31"]["cumulative"] == 650 and by["2026-07-31"]["cumulative"] == 739
    assert by["2022-06-30"]["cash_in_month"] == 11 and by["2025-11-30"]["cash_in_month"] is None    # October 2025 is not stated
    codes = {f.code: f for f in findings}
    assert set(codes) == {"R01", "R02"}
    assert codes["R02"].scope == "NBPE 2025-05-31" and "53 + 8 = 61 vs stated 66" in codes["R02"].observed
    assert codes["R01"].observed.startswith("8 of 55: 2022-02-28")


def snap(as_of, ytd=None, month=None, prior=None, fv=1000.0):
    return Snapshot(vehicle="X", as_of=as_of, published=None, source_url="", currency="USD", unit="millions", holdings=[],
                    stated_total_fv=fv, stated_total_pct=1.0, realised_ytd_m=ytd, realised_month_m=month, realised_prior_year_m=prior)


def test_reconciliation_findings():
    s = [snap(date(2024, 11, 30), ytd=90), snap(date(2024, 12, 31), ytd=100), snap(date(2025, 1, 31), ytd=10), snap(date(2025, 2, 28), ytd=8),
         snap(date(2025, 3, 31), ytd=20, prior=120)]
    rows, findings = R.cash_series(s)
    got = {f.code: f.observed for f in findings}
    assert got["R03"] == "8 after 10" and got["R04"].startswith("December report 100 vs 120")
    # no December figure and nothing restating the year: the running total cannot cross that year-end
    rows, findings = R.cash_series([snap(date(2024, 11, 30), ytd=90), snap(date(2025, 1, 31), ytd=10), snap(date(2025, 2, 28), ytd=12)])
    assert [f.code for f in findings if f.code == "R07"] and rows[-1]["cumulative"] is None
    # the same gap, closed by a later report restating the year
    rows, _ = R.cash_series([snap(date(2024, 11, 30), ytd=90), snap(date(2025, 1, 31), ytd=10), snap(date(2025, 2, 28), ytd=12, prior=100)])
    assert rows[-1]["cumulative"] == 112


def test_calibration_on_the_sample(snaps):
    rows, _ = R.cash_series(snaps)
    c = R.calibrate(rows, CAL, 0.15)
    w = {x["window"]: x for x in c["windows"]}
    assert (w["12 months"]["cash"], w["24 months"]["cash"], w["all"]["cash"]) == (198, 295, 739)
    assert (w["12 months"]["start"], w["24 months"]["start"], w["all"]["start"]) == (date(2025, 7, 31), date(2024, 7, 31), date(2021, 12, 31))
    assert [round(w[k]["pace"], 4) for k in ("12 months", "24 months", "all")] == [0.1587, 0.1170, 0.1213]
    assert c["source"] == "calibrated" and c["base_window"] == "24 months" and round(c["base_pace"], 4) == 0.1170
    assert c["end"] == date(2026, 7, 31) and c["end_basis"] == "derived" and c["reports_after_end"] == [date(2026, 8, 31)]
    # the pace is cash / average portfolio fair value / years, on the published numbers
    fv = [s.implied_portfolio_fv for s in snaps if date(2025, 7, 31) <= s.as_of < date(2026, 7, 31)]
    assert len(fv) == 12 and w["12 months"]["pace"] == pytest.approx(198 / (sum(fv) / 12))
    # the publisher's own cross-check: "$122 million to 31 May 2024, approximately 9% of opening portfolio value"
    opening_2024 = next(s.implied_portfolio_fv for s in snaps if s.as_of == date(2023, 12, 31))
    assert round(122 / opening_2024, 2) == 0.09


def test_the_base_case_follows_the_rule_in_the_config(snaps):
    rows, _ = R.cash_series(snaps)
    pick = lambda rule: R.calibrate(rows, {**CAL, "base_rule": rule}, 0.15)
    assert pick("highest")["base_window"] == "12 months" and pick("median")["base_window"] == "all"
    assert pick("12")["base_window"] == "12 months" and pick("all")["base_window"] == "all"
    assert pick("36")["source"] == "assumed" and pick("36")["base_pace"] == 0.15 and "could not be computed" in pick("36")["reason"]


def test_calibration_never_looks_past_the_report_being_analysed(snaps):
    rows, _ = R.cash_series([s for s in snaps if s.as_of <= date(2026, 4, 30)])
    c = R.calibrate(rows, CAL, 0.15)
    assert c["end"] == date(2026, 4, 30) and {w["window"]: w["cash"] for w in c["windows"]} == {"12 months": 155, "24 months": 317, "all": 678}


def test_windows_that_cannot_be_computed_say_why_and_the_pace_falls_back_to_the_labelled_assumption():
    # year to date known only at the end: a 12-month window has no known start, and "all" is under 12 months
    rows, _ = R.cash_series([snap(date(2025, 3, 31)), snap(date(2025, 4, 30)), snap(date(2025, 5, 31), ytd=40)])
    c = R.calibrate(rows, CAL, 0.15)
    notes = {w["window"]: w["note"] for w in c["windows"]}
    assert notes["12 months"] == "running total not known at the start of the window" and notes["all"] == "shorter than 12 months"
    assert c["source"] == "assumed" and c["base_pace"] == 0.15 and c["reason"].startswith("no window could be computed")
    none = R.calibrate(R.cash_series([snap(date(2025, 3, 31))])[0], CAL, 0.15)
    assert none["source"] == "assumed" and none["reason"] == "no report states cash received from realisations"


def test_real_run_uses_the_calibrated_pace_and_the_rules_move_the_loan(cfg):
    r = pipeline.analyse(cfg, SAMPLE)
    assert round(r["base_pace"], 4) == 0.1170 and r["calibration"]["source"] == "calibrated" and r["former_pace"] == 0.15
    assert r["verdict"] == "Proceed with conditions" and r["proposed"]["opening_ltv"] == 0.15 and round(r["proposed"]["loan"], 1) == 138.4
    assert r["former_proposed"]["opening_ltv"] == 0.20 and round(r["former_proposed"]["loan"], 1) == 184.6        # the v0.1.0 result, kept as a sensitivity
    tests = {c["opening_ltv"]: {t["test"]: t["passed"] for t in c["tests"]} for c in r["candidate_tests"]}
    assert tests[0.20]["Repayment from exits (base pace)"] is False and all(tests[0.15].values())
    ro = r["runoffs"]
    assert round(ro[0.20]["base"]["balance_at_maturity"], 1) == 32.7 and ro[0.15]["base"]["repaid_quarter"] == 14
    assert (ro[0.15]["breakeven_pace"], ro[0.20]["breakeven_pace"]) == (0.1, 0.143)
    assert round(r["runoffs_former"][0.20]["base"]["balance_at_maturity"], 1) == 0.0 and r["runoffs_former"][0.20]["base"]["repaid_quarter"] == 16
    flags = {f.code: f for f in r["flags"]}
    assert flags["P20"].severity == "note" and "24 months 11.7%" in flags["P20"].observed and "P21" not in flags
    assert flags["P18"].severity == "condition" and "needs 10.0%" in flags["P18"].observed and "(9.4%)" in flags["P18"].threshold


def test_with_calibration_switched_off_the_old_result_returns_and_is_labelled_an_assumption(cfg):
    import copy
    c2 = copy.deepcopy(cfg)
    c2["facility"]["runoff"]["exit_pace_calibration"]["enabled"] = False
    r = pipeline.analyse(c2, SAMPLE)
    assert r["base_pace"] == 0.15 and r["proposed"]["opening_ltv"] == 0.20 and round(r["proposed"]["loan"], 1) == 184.6
    flags = {f.code: f for f in r["flags"]}
    assert flags["P20"].severity == "condition" and "switched off" in flags["P20"].observed
    memo = report.build_memo(r)
    assert "**Exit pace: 15.0% a year, an assumption.**" in memo and "Former assumption" not in memo


def test_the_memo_figures_on_exit_pace_are_in_named_files(cfg, tmp_path):
    import csv
    r = pipeline.analyse(cfg, SAMPLE)
    report.write_outputs(r, tmp_path)
    memo = (tmp_path / "memo.md").read_text(encoding="utf-8")
    rd = lambda n: list(csv.DictReader(open(tmp_path / n, newline="", encoding="utf-8")))
    cal = {x["window"]: x for x in rd("exit_pace_calibration.csv")}
    for k, label in (("12 months", "12 months to 2026-07-31"), ("24 months", "24 months to 2026-07-31 *"), ("all", "all, from 2022-01-01 to 2026-07-31")):
        assert f"| {label} | {cal[k]['months']} | {float(cal[k]['cash_received']):,.0f} | {float(cal[k]['average_portfolio_fair_value']):,.0f} | {float(cal[k]['pace_per_year']):.1%} |" in memo
    assert cal["24 months"]["base_case"] == "True" and float(cal["base case"]["pace_per_year"]) == pytest.approx(r["base_pace"], abs=1e-6)
    assert float(cal["former assumption"]["pace_per_year"]) == 0.15
    assert f"**Exit pace: {float(cal['base case']['pace_per_year']):.1%} a year, calibrated from the vehicle's own reports.**" in memo
    sens = {(x["case"], float(x["opening_ltv"])): x for x in rd("runoff_sensitivity.csv")}
    assert sens[("base case", 0.2)]["passed_all_tests"] == "False" and sens[("former assumption", 0.2)]["passed_all_tests"] == "True"
    assert f"| 20% | 184.6 | {float(sens[('base case', 0.2)]['balance_at_maturity']):,.1f} outstanding (fails a test) | repaid in quarter {sens[('former assumption', 0.2)]['repaid_quarter']} | 14.3% |" in memo
    assert "Proposed loan: 15% (138.4) on the base case; 20% (184.6) on the former assumption." in memo
    cash = rd("realisations.csv")
    assert len(cash) == 55 and cash[-2]["running_total"] == "739.0" and cash[-1]["cash_received_year_to_date"] == ""
    assert "Cash received by calendar year: 2022 120; 2023 171; 2024 179; 2025 180; 2026 89 to 2026-07-31." in memo
    assert "8 of 55 reports give no figure for cash received" in memo and "53 + 8 = 61 vs stated 66" in memo
    rec = json.loads((tmp_path / "recommendation.json").read_text())
    assert rec["exit_pace"]["source"] == "calibrated" and rec["former_assumption_result"]["proposed"]["opening_ltv"] == 0.2


def test_stale_realisation_data_becomes_a_condition():
    base = dict(pool={"eligible_names": 20, "undisclosed_share_of_published": 0.05, "excluded_names": 1}, overlay={"rated_share": 0.5, "weak_share": 0.0},
                quality_counts={"error": 0, "unreconciled_recent": 0}, stale={"stale_share": 0.1, "age_today": 90.0},
                snapshot_meta={"investment_level_pct": 100.0}, proposed={"opening_ltv": 0.2}, runoff_info={"breakeven_pace": 0.05, "base_pace": 0.12},
                policy={"max_undisclosed_share": 0.1, "max_stale_share": 0.25, "stale_days": 100, "max_weighted_mark_age_days": 120, "min_sponsor_coverage": 0.25,
                        "max_weak_sponsor_share": 0.15, "max_vehicle_investment_level": 110, "max_unreconciled_snapshots": 0,
                        "max_breakeven_share_of_base_pace": 0.8, "max_calibration_lag_months": 3},
                cov={"min_assets": 15, "top_n": 5}, limits_bite=0.0, market_ran=True)
    cal = {"source": "calibrated", "rule": "lowest", "base_pace": 0.12, "end": date(2026, 3, 31), "fallback_pace": 0.15,
           "windows": [{"window": "12 months", "pace": 0.12}], "lag_months": 5}
    sev = {f.code: f.severity for f in recommend.build_flags(**base, calibration=cal)}
    assert sev["P20"] == "note" and sev["P21"] == "condition"
    assert "P21" not in {f.code for f in recommend.build_flags(**base, calibration={**cal, "lag_months": 3})}


def test_the_file_layout_round_trips_the_new_columns(snaps, tmp_path):
    save_snapshots(snaps, tmp_path / "h.csv", tmp_path / "s.csv")
    assert (tmp_path / "s.csv").read_bytes() == (SAMPLE / "snapshots_nbpe.csv").read_bytes()
    back = FileHoldings(tmp_path / "h.csv", tmp_path / "s.csv").load()
    assert [(s.realised_ytd_m, s.realised_month_m, s.realised_prior_year_m, s.realised_text) for s in back] == \
        [(s.realised_ytd_m, s.realised_month_m, s.realised_prior_year_m, s.realised_text) for s in snaps]


def test_a_file_without_the_new_columns_still_loads_and_the_pace_is_then_an_assumption(cfg, tmp_path):
    import csv
    for n in ("holdings_nbpe.csv", "track_record_calpers.csv", "prices.csv", "rates.csv"):
        shutil.copyfile(SAMPLE / n, tmp_path / n)
    with open(SAMPLE / "snapshots_nbpe.csv", newline="", encoding="utf-8") as fh:
        old = [{k: v for k, v in row.items() if not k.startswith("realised_")} for row in csv.DictReader(fh)]
    with open(tmp_path / "snapshots_nbpe.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(old[0]), lineterminator="\n")
        w.writeheader(); w.writerows(old)
    r = pipeline.analyse(cfg, tmp_path)
    assert r["calibration"]["source"] == "assumed" and r["base_pace"] == 0.15 and r["proposed"]["opening_ltv"] == 0.20
    assert {f.code: f.severity for f in r["flags"]}["P20"] == "condition"


def test_verify_live_compares_the_cash_figures(cfg, tmp_path):
    live = tmp_path / "live"
    shutil.copytree(SAMPLE, live)
    snaps = FileHoldings(live / "holdings_nbpe.csv", live / "snapshots_nbpe.csv").load()
    snaps[-2].realised_month_m = 2.0
    save_snapshots(snaps, live / "holdings_nbpe.csv", live / "snapshots_nbpe.csv")
    v = refresh.verify_live(cfg, live, SAMPLE)
    assert not v["agree"] and v["holdings"]["mismatches"] == [{"as_of": "2026-07-31", "field": "realised_month_m", "live": "2.0", "sample": "1.0"}]


def test_sample_ties_to_the_manifest_totals(snaps):
    tie = json.loads((SAMPLE / "manifest.json").read_text(encoding="utf-8"))["sources"]["holdings_nbpe.csv / snapshots_nbpe.csv"]["cash_received"]["tie_out"]
    rows, _ = R.cash_series(snaps)
    assert {str(k): v for k, v in R.year_totals(rows).items()} == tie["cash_received_by_year"]
    assert next(r["ytd"] for r in rows if r["as_of"] == date(2026, 7, 31)) == tie["year_to_date_2026-07-31"]
    restated = {str(s.as_of.year - 1): s.realised_prior_year_m for s in snaps if s.realised_prior_year_m is not None}
    assert restated == tie["previous_year_totals_restated_in_later_reports"]
    assert all(restated[y] == tie["cash_received_by_year"][y] for y in restated)
