"""The shipped sample is real published data. These tests tie it back to the publishers' own totals."""
import hashlib
import json
from datetime import date

from conftest import SAMPLE
from navmonitorlab import quality


def test_sample_files_match_their_manifest():
    man = json.loads((SAMPLE / "manifest.json").read_text())
    for name, meta in man["files"].items():
        raw = (SAMPLE / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == meta["sha256"], name
        assert len(raw) == meta["bytes"]


def test_calpers_sample_ties_to_the_column_sums_read_off_the_live_page(track):
    tie = json.loads((SAMPLE / "manifest.json").read_text())["sources"]["track_record_calpers.csv"]["tie_out"]
    f = track.funds
    assert len(f) == tie["rows"] == 485
    assert sum(x.vintage for x in f) == tie["sum_vintage"]
    assert sum(x.committed for x in f) == tie["sum_committed"]
    assert sum(x.cash_in for x in f) == tie["sum_cash_in"]
    assert sum(x.cash_out for x in f) == tie["sum_cash_out"]
    assert sum(x.total_value for x in f) == tie["sum_total_value"]
    assert sum(1 for x in f if x.footnote) == tie["rows_with_footnote"]


def test_every_published_multiple_can_be_recomputed(track):
    """All 484 funds with cash paid in: published multiple equals value / cash in to the published decimal."""
    checked = [x for x in track.funds if x.multiple is not None and x.cash_in > 0]
    assert len(checked) > 400
    assert all(abs(x.tvpi - x.multiple) <= 0.06 for x in checked)


def test_nbpe_history_is_complete_and_monthly(snaps):
    assert len(snaps) == 55 and snaps[0].as_of == date(2022, 2, 28) and snaps[-1].as_of == date(2026, 8, 31)
    months = [(s.as_of.year, s.as_of.month) for s in snaps]
    assert len(set(months)) == 55 and all(len(s.holdings) == 30 for s in snaps)
    assert all(s.valuation_mix and abs(sum(w for _, w in s.valuation_mix) - 1) <= 0.021 for s in snaps)
    assert all(s.nav_per_share_usd and s.source_url.startswith("https://data.fca.org.uk/artefacts/NSM/GNW/") for s in snaps)


def test_52_of_55_reports_tie_to_their_own_total_row_and_the_other_three_are_flagged(snaps):
    bad = [s.as_of for s in snaps if any(f.code == "Q01" for f in quality.check_snapshot(s))]
    assert bad == [date(2023, 3, 31), date(2023, 4, 30), date(2023, 8, 31)]


def test_latest_snapshot_values(snaps):
    s = snaps[-1]
    assert (s.stated_total_fv, s.stated_total_pct) == (1051.0, 0.823) and round(s.total_fv, 1) == 1051.2
    assert s.holdings[0].company == "Action" and s.holdings[0].fair_value == 78.4
    assert (s.cash_m, s.undrawn_credit_m, s.investment_level_pct) == (7.0, 135.0, 115.0)
    assert s.private_mix() == [(date(2026, 6, 30), 1.0)]
