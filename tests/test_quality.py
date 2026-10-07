from dataclasses import replace
from datetime import date

from navmonitorlab import quality
from navmonitorlab.schema import FundRecord, Holding, Snapshot, TrackRecord


def snap(holdings, total=None, pct=None, mix=None):
    return Snapshot("V", date(2026, 6, 30), date(2026, 7, 20), "u", "USD", "millions", holdings, total, pct,
                    nav_per_share_usd=10.0, valuation_mix=mix or [(date(2026, 6, 30), 0.1), (date(2026, 3, 31), 0.9)])


H = [Holding("A", 2020, "S1", "Tech", 60.0, 0.30), Holding("B", 2021, "S2", "Tech", 40.0, 0.20)]


def test_clean_snapshot_has_no_findings():
    assert quality.check_snapshot(snap(H, 100.0, 0.50)) == []


def test_rows_that_do_not_sum_to_the_total_are_flagged_not_fixed():
    s = snap([replace(H[0], fair_value=75.0), H[1]], 100.0, 0.50)
    codes = [f.code for f in quality.check_snapshot(s)]
    assert "Q01" in codes and "Q03" in codes          # the total is off, and the changed row no longer fits its own percentage
    assert s.holdings[0].fair_value == 75.0           # nothing was altered


def test_duplicate_names_and_missing_breakdown():
    s = snap(H + [Holding("A", 2020, "S1", "Tech", 1.0, 0.005)], 101.0, 0.505, mix=[(date(2026, 6, 30), 1.0)])
    assert "Q04" in [f.code for f in quality.check_snapshot(s)]
    bare = Snapshot("V", date(2026, 6, 30), None, "u", "USD", "m", H, 100.0, 0.5)
    assert {"Q05", "Q07"} <= {f.code for f in quality.check_snapshot(bare)}


def test_mark_age_and_stale_share():
    s = snap(H, 100.0, 0.5, mix=[(date(2026, 6, 30), 0.2), (date(2026, 3, 31), 0.5), (date(2025, 12, 31), 0.3)])
    assert quality.stale_share(s, 100) == 0.3
    assert quality.weighted_mark_age(s) == 0.5 * 91 + 0.3 * 181


def test_history_check_reports_relabelled_companies():
    s1 = snap([Holding("Acme", 2017, "GP", "Tech", 10.0, 0.1)])
    s2 = replace(s1, as_of=date(2026, 7, 31), holdings=[Holding("Acme", 2022, "GP", "Industrials", 10.0, 0.1)])
    found = {f.code: f for f in quality.check_history([s1, s2], {})}
    assert set(found) == {"Q10", "Q11"} and "2017" in found["Q10"].observed and "2022" in found["Q10"].observed


def test_track_record_checks():
    funds = [FundRecord("Good Fund I", 2015, 100, 100, 150, 180, 0.15, 1.8),
             FundRecord("Wrong Multiple II", 2015, 100, 100, 50, 150, 0.1, 2.0),          # 150/100 is 1.5x, not 2.0x
             FundRecord("Impossible III", 2015, 100, 100, 120, 100, 0.0, 1.0),           # total below cash out
             FundRecord("Young IV", 2024, 100, 10, 0, 30, 7.009, 3.0, "1"),
             FundRecord("Unfunded V", 2026, 100, 0, 0, 5, None, None, "1"),
             FundRecord("Recycler VI L.P. 1", 2010, 10, 100, 150, 150, 0.1, 1.5)]
    codes = {}
    for f in quality.check_track_record(TrackRecord("LP", "PE", date(2026, 3, 31), "u", funds)):
        codes.setdefault(f.code, []).append(f.scope)
    assert codes["T01"] == ["Wrong Multiple II"] and codes["T05"] == ["Impossible III"]
    assert codes["T04"] == ["Young IV"] and codes["T06"] == ["Unfunded V"]
    assert codes["T07"] == ["Recycler VI L.P. 1"] and codes["T11"] == ["Recycler VI L.P. 1"]
    assert "T09" in codes and "T02" in codes and "T03" in codes


def test_real_table_findings(track, cfg):
    fs = quality.check_track_record(track, **cfg["track"]["quality"])
    by = {}
    for f in fs:
        by.setdefault(f.code, []).append(f)
    assert "T01" not in by and "T05" not in by                       # the publisher's arithmetic holds
    assert any("Forbion Growth Opportunities Fund II" in f.scope and "700.9%" in f.observed for f in by["T04"])
    assert any("Blackstone Capital Partners V" in f.scope for f in by["T07"])
    assert len(by["T11"]) == 4 and all("Permira" in f.scope for f in by["T11"])
