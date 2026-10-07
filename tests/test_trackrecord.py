from datetime import date

import pytest

from navmonitorlab import trackrecord as T
from navmonitorlab.collateral import PoolAsset
from navmonitorlab.schema import FundRecord, TrackRecord

SCORING = {"seasoned_age_years": 4, "mature_age_years": 8, "min_seasoned_funds": 3, "cohort_min_funds": 5,
           "strong": {"median_dpi_rank_min": 0.60, "pooled_mature_dpi_min": 1.3},
           "weak": {"median_dpi_rank_max": 0.35, "pooled_mature_dpi_max": 1.0}}
GP = T.GpMap({"families": [{"family": "Alpha", "basis": "name", "patterns": ["Alpha "]},
                           {"family": "Beta", "basis": "inferred", "patterns": ["BX "]}],
              "sponsors": {"Alpha Partners": "Alpha", "Beta": "Beta"}})


def fund(name, vintage, cash_in, cash_out, total):
    return FundRecord(name, vintage, cash_in, cash_in, cash_out, total, 0.1, round(total / cash_in, 1))


def test_fund_metrics_by_hand():
    f = fund("Alpha I", 2016, 100, 80, 150)
    m = T.fund_metrics(TrackRecord("LP", "PE", date(2026, 3, 31), "", [f]), GP)[0]
    assert (m.dpi, m.rvpi, m.tvpi, m.remaining, m.age) == (0.8, 0.7, 1.5, 70, 10)
    assert (m.family, m.basis) == ("Alpha", "name") and m.cohort_rank_dpi is None      # one fund is not a peer group


def test_rank_is_within_vintage_and_handles_ties():
    assert T._rank(3, [1, 2, 3]) == 1.0 and T._rank(1, [1, 2, 3]) == 0.0 and T._rank(2, [1, 2, 3]) == 0.5
    assert T._rank(2, [2, 2, 2]) == 0.5
    funds = [fund(f"Other {i}", 2016, 100, 20 * i, 150) for i in range(1, 5)] + [fund("Alpha I", 2016, 100, 100, 150)]
    ms = {m.fund: m for m in T.fund_metrics(TrackRecord("LP", "PE", date(2026, 3, 31), "", funds), GP)}
    assert ms["Alpha I"].cohort_rank_dpi == 1.0 and ms["Other 1"].cohort_rank_dpi == 0.0 and ms["Alpha I"].cohort_n == 5


@pytest.mark.parametrize("n, mature, rank, dpi, expected", [
    (2, 2, 0.9, 2.0, "insufficient"),
    (3, 2, 0.9, 0.9, "weak"),            # old funds have not returned capital, whatever the rank
    (3, 0, 0.2, None, "weak"),           # slow against peers
    (3, 2, 0.7, 1.5, "strong"),
    (3, 0, 0.7, None, "strong"),         # no old funds yet: rank alone decides
    (3, 2, 0.7, 1.1, "adequate"),        # fast, but old funds only just returned capital
    (3, 2, 0.5, 1.5, "adequate")])
def test_rating_rule(n, mature, rank, dpi, expected):
    assert T.rate_family(n, mature, rank, dpi, SCORING)[0] == expected


def test_gp_map_and_joint_sponsors():
    assert GP.family_of("Alpha Capital Partners IX") == ("Alpha", "name") and GP.family_of("BX Co-Invest") == ("Beta", "inferred")
    assert GP.family_of("Golden Bay 2024") == ("", "")
    assert GP.families_of_sponsor("Someone / Beta") == ["Beta"] and GP.families_of_sponsor("Unknown GP") == []


def test_overlay_carries_weakest_rated_sponsor_and_measures_coverage():
    fams = [T.FamilyRecord("Alpha", "name", 5, 5, 3, 1, 1, 1.5, 1.8, 1.6, 1.0, 0.8, 0.8, "strong", "r"),
            T.FamilyRecord("Beta", "inferred", 1, 0, 0, 1, 1, None, None, None, None, None, None, "insufficient", "r")]
    pool = [PoolAsset("A", "A", "Alpha Partners / Beta", "Tech", 2020, 60.0, False, True, ""),
            PoolAsset("B", "B", "Beta", "Tech", 2020, 30.0, False, True, ""),
            PoolAsset("C", "C", "Unknown GP", "Tech", 2020, 10.0, False, True, ""),
            PoolAsset("D", "D*", "Alpha Partners", "Tech", 2020, 50.0, False, False, "name or sponsor not disclosed")]
    rows, s = T.sponsor_overlay(pool, GP, fams)
    assert [r["rating"] for r in rows] == ["strong", "insufficient", "no record", "strong"]
    assert s["eligible_fv"] == 100 and s["rated_share"] == 0.6 and s["insufficient_share"] == 0.3 and s["no_record_share"] == 0.1


def test_real_table_coverage_and_known_families(track, cfg):
    gp = T.GpMap(cfg["gp_map"])
    ms = T.fund_metrics(track, gp, cfg["track"]["scoring"]["cohort_min_funds"])
    cov = T.coverage(ms)
    assert cov["funds"] == 485 and cov["mapped_funds"] == 229 and 0.3 < cov["mapped_share_of_remaining_value"] < 0.4
    fam = {f.family: f for f in T.family_records(ms, cfg["track"]["scoring"])}
    assert fam["Francisco Partners"].rating == "strong" and fam["Thoma Bravo"].rating == "insufficient"
    by = {m.fund: m for m in ms}
    assert by["Advent International GPE VIII-B Limited Partnership"].dpi == pytest.approx(774417264 / 500000000)
    v = {r["vintage"]: r for r in T.vintage_table(ms)}
    assert v[2021]["funds"] == 43 and v[2026]["funds"] == 18        # one 2026 fund has no cash in and is left out
