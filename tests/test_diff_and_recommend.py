from datetime import date

from navmonitorlab import diff, recommend
from navmonitorlab.schema import Holding, Snapshot

POLICY = {"mover_threshold": 0.15, "stale_days": 100, "max_undisclosed_share": 0.10, "max_stale_share": 0.25, "max_weighted_mark_age_days": 120,
          "min_sponsor_coverage": 0.25, "max_weak_sponsor_share": 0.15, "max_vehicle_investment_level": 110, "max_unreconciled_snapshots": 0}
COV = {"ltv_sweep": 0.30, "ltv_breach": 0.40, "min_assets": 3, "top_n": 5}
SIZ = {"min_cushion_to_breach": 0.40}


def snap(d, holdings, **kw):
    return Snapshot("V", d, d, "", "USD", "m", holdings, valuation_mix=[(d, 1.0)], **kw)


def test_diff_finds_entries_exits_movers_and_renames():
    prev = snap(date(2026, 7, 31), [Holding("Advisor Group", 2019, "RC", "Fin", 50.0, None), Holding("Steady", 2020, "GP", "Tech", 40.0, None),
                                    Holding("Faller", 2020, "GP", "Tech", 30.0, None), Holding("Gone", 2018, "GP", "Tech", 20.0, None)],
                nav_per_share_usd=27.0, cash_m=12.0, investment_level_pct=112.0)
    cur = snap(date(2026, 8, 31), [Holding("Osaic", 2019, "Reverence", "Fin", 51.0, None), Holding("Steady", 2020, "GP", "Tech", 40.0, None),
                                   Holding("Faller", 2020, "GP", "Tech", 21.0, None), Holding("Newco", 2026, "GP", "Tech", 25.0, None)],
               nav_per_share_usd=28.0, cash_m=7.0, investment_level_pct=115.0)
    d = diff.diff_snapshots(prev, cur, {"company_aliases": {"Advisor Group": "Osaic"}}, POLICY, {"companies": ["Steady"]})
    assert d["entered"] == ["Newco"] and d["left"] == ["Gone"]
    assert [m["company"] for m in d["movers"]] == ["Faller"] and round(d["movers"][0]["change"], 2) == -0.30
    rows = {r["company"]: r for r in d["rows"]}
    assert rows["Osaic"]["status"] == "held" and "sponsor label RC -> Reverence" in rows["Osaic"]["notes"] and "published as" in rows["Osaic"]["notes"]
    assert rows["Steady"]["flag"] and rows["Steady"]["watchlist"] and not rows["Osaic"]["flag"]
    assert round(d["held_value_change"], 4) == round(112 / 120 - 1, 4)
    assert d["prev"]["cash_m"] == 12.0 and d["cur"]["investment_level_pct"] == 115.0
    assert d["sectors"][0]["sector"] in ("Tech", "Fin") and abs(sum(s["change_pp"] for s in d["sectors"])) < 1e-9


def test_track_record_diff():
    prev = [{"fund": "A", "dpi": 0.5, "tvpi": 1.2}, {"fund": "B", "dpi": 1.0, "tvpi": 1.5}]
    cur = [{"fund": "A", "dpi": 0.9, "tvpi": 1.3}, {"fund": "C", "dpi": 0.0, "tvpi": 1.0}]
    d = diff.diff_track_records(prev, cur)
    assert d["new"] == ["C"] and d["dropped"] == ["B"] and d["dpi_moves"][0]["fund"] == "A"


def cand(l0, cushion):
    return {"opening_ltv": l0, "loan": 1000 * l0, "drawdown_to_breach": cushion}


def ro(balance=0.0, breached=False, peak=0.2, q=10):
    return {"balance_at_maturity": balance, "breached": breached, "peak_ltv": peak, "repaid_quarter": None if balance else q}


def test_candidates_must_pass_every_test_and_the_highest_passing_one_is_proposed():
    cands = [cand(0.15, 0.625), cand(0.20, 0.50), cand(0.25, 0.375)]
    scen = {0.15: [{"scenario": "s", "status": "ok"}], 0.20: [{"scenario": "s", "status": "cash sweep"}], 0.25: [{"scenario": "bad one", "status": "breach"}]}
    single = [{"opening_ltv": l, "assets_written_down": 1, "status": "ok"} for l in (0.15, 0.20, 0.25)]
    runoffs = {l: {"base": ro(), "drought": ro(balance=50.0)} for l in (0.15, 0.20, 0.25)}
    tests = recommend.assess_candidates(cands, scen, single, runoffs, {0.15: 0.16, 0.20: 0.21, 0.25: 0.31}, COV, SIZ)
    assert [t["passed"] for t in tests] == [True, True, False]
    failed = [x["test"] for x in tests[2]["tests"] if not x["passed"]]
    assert failed == ["Cushion to breach", "Sector scenarios", "Rolled-forward LTV under the sweep level"]
    verdict, prop = recommend.decide(tests, [])
    assert verdict == "Proceed" and prop["opening_ltv"] == 0.20


def flags(**over):
    base = dict(pool={"eligible_names": 20, "undisclosed_share_of_published": 0.05, "excluded_names": 1},
                overlay={"rated_share": 0.5, "weak_share": 0.0}, quality_counts={"error": 0, "unreconciled_recent": 0},
                stale={"stale_share": 0.1, "age_today": 90.0}, snapshot_meta={"investment_level_pct": 100.0, "cash_m": 50.0, "undrawn_credit_m": 200.0},
                proposed={"opening_ltv": 0.2}, runoff_info={"breakeven_pace": 0.10, "base_pace": 0.15}, policy=POLICY, cov=COV,
                limits_bite=0.0, market_ran=True)
    base.update(over)
    return recommend.build_flags(**base)


def test_flags_fire_only_when_a_threshold_is_crossed():
    assert {f.severity for f in flags()} == {"note"}
    sev = lambda fs: {f.code: f.severity for f in fs}
    assert sev(flags(overlay={"rated_share": 0.1, "weak_share": 0.2}))["P13"] == "condition"
    assert sev(flags(overlay={"rated_share": 0.5, "weak_share": 0.2}))["P14"] == "condition"
    assert sev(flags(snapshot_meta={"investment_level_pct": 115.0, "cash_m": 7.0, "undrawn_credit_m": 135.0}))["P15"] == "condition"
    assert sev(flags(stale={"stale_share": 0.4, "age_today": 150.0})).keys() >= {"P11", "P12"}
    assert sev(flags(runoff_info={"breakeven_pace": 0.143, "base_pace": 0.15}))["P18"] == "condition"
    assert sev(flags(pool={"eligible_names": 20, "undisclosed_share_of_published": 0.2, "excluded_names": 3}))["P10"] == "condition"
    assert sev(flags(market_ran=False))["P19"] == "condition"
    assert sev(flags(quality_counts={"error": 0, "unreconciled_recent": 2}))["P16"] == "condition"


def test_verdict_rules():
    ok = [{"opening_ltv": 0.2, "loan": 200.0, "passed": True, "tests": []}]
    assert recommend.decide(ok, flags())[0] == "Proceed"
    assert recommend.decide(ok, flags(market_ran=False))[0] == "Proceed with conditions"
    assert recommend.decide(ok, flags(quality_counts={"error": 1, "unreconciled_recent": 0}))[0] == "Decline"
    assert recommend.decide(ok, flags(pool={"eligible_names": 2, "undisclosed_share_of_published": 0.0, "excluded_names": 0}))[0] == "Decline"
    none = [{"opening_ltv": 0.2, "loan": 200.0, "passed": False, "tests": []}]
    assert recommend.decide(none, flags(proposed=None)) == ("Decline", None)
