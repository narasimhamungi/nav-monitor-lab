"""The live plugs' parsers, run against real excerpts of the pages captured on 2026-10-07."""
import json
from datetime import date

from conftest import SAMPLE, fixture_text
from navmonitorlab.htmltable import find_table, parse
from navmonitorlab.net import FetchError, Fetcher
from navmonitorlab.sources.calpers import CalpersTrackRecord, parse_page
from navmonitorlab.sources.fca_nsm import ARTEFACT_BASE, FcaNsmHoldings, parse_announcement, search_body
from navmonitorlab.sources.files import FileTrackRecord
from navmonitorlab.sources.market import FredRates, YahooChartPrices, parse_fred_csv, parse_tiingo, parse_yahoo_chart

import pytest


def test_calpers_excerpt_matches_sample_rows():
    tr, findings = parse_page(fixture_text("calpers_pep_excerpt.html"))
    assert tr.as_of == date(2026, 3, 31) and not findings
    assert len(tr.funds) == 15                      # 12 first rows + 3 last rows; the repeated header row is skipped
    sample = {f.fund: f for f in FileTrackRecord(SAMPLE / "track_record_calpers.csv").load().funds}
    for f in tr.funds:
        assert sample[f.fund] == f                  # identical to what the browser capture recorded


def test_calpers_footnotes_and_links_do_not_leak_into_values():
    tr, _ = parse_page(fixture_text("calpers_pep_excerpt.html"))
    by = {f.fund: f for f in tr.funds}
    young = by["2024 Golden Bay, L.P."]
    assert young.net_irr is None and young.multiple is None and young.footnote == "1"
    assert by["2SP I, L.P."].net_irr == pytest.approx(0.413) and by["2SP I, L.P."].multiple == 1.4
    linked = by["57 Stars Global Opportunities Fund 2 (CalPERS), LLC"]          # name sits inside an <a> on the page
    assert linked.cash_in == 531394363 and linked.footnote == ""
    assert by["AACP India Investors C"].net_irr == pytest.approx(-0.016)


def test_calpers_layout_change_is_an_error_not_a_guess():
    with pytest.raises(ValueError, match="expected column headings"):
        parse_page("<html><body><p>As of March 31, 2026</p><table><tr><td>Fund</td><td>Other</td></tr></table></body></html>")


def test_nbpe_announcement_matches_sample_snapshot(snaps):
    snap, findings = parse_announcement(fixture_text("nbpe_2026-04_excerpt.html"), vehicle="NBPE", source_url="u", published=date(2026, 5, 27))
    assert not findings
    ref = next(s for s in snaps if s.as_of == date(2026, 4, 30))
    assert snap.as_of == ref.as_of and snap.holdings == ref.holdings and len(snap.holdings) == 30
    assert (snap.stated_total_fv, snap.stated_total_pct) == (1014.8, 0.805)
    assert snap.valuation_mix == ref.valuation_mix == [(date(2026, 4, 30), 0.06), (date(2026, 3, 31), 0.73), (date(2025, 12, 31), 0.21)]
    assert (snap.nav_per_share_usd, snap.nav_per_share_gbp) == (27.42, 20.18)


def test_nbpe_header_cells_are_td_not_th():
    """The real page writes its header row with <td><b>, so the table must be found by text, not by tag."""
    tables, _ = parse(fixture_text("nbpe_2026-04_excerpt.html"))
    t, hdr, col = find_table(tables, {"company": ["Company Name"], "fv": ["Fair Value ($m)"], "pct": ["% of FV"]})
    assert hdr == 0 and not t.rows[0][0].is_header and col == {"company": 0, "fv": 4, "pct": 5}


def test_announcement_without_a_holdings_table_is_skipped_with_a_finding():
    snap, findings = parse_announcement("<html><body><p>Transaction in own shares</p></body></html>", vehicle="X", source_url="u", published=None)
    assert snap is None and findings[0].code == "H00"


class FakeWeb:
    """Stands in for the network: serves the captured payloads and records what was asked for."""

    def __init__(self, fail: tuple[str, ...] = ()):
        self.calls, self.fail = [], fail

    def __call__(self, url, data, headers):
        self.calls.append((url, data, headers))
        if any(x in url for x in self.fail):
            raise FetchError(f"blocked in test: {url}")
        if "api.data.fca.org.uk" in url:
            return fixture_text("nsm_search_response.json").encode()
        if "data.fca.org.uk/artefacts" in url:
            return fixture_text("nbpe_2026-04_excerpt.html").encode()
        if "calpers.ca.gov" in url:
            return fixture_text("calpers_pep_excerpt.html").encode()
        if "finance.yahoo.com" in url:
            return fixture_text("yahoo_chart_xlk_5d.json").encode()
        if "fred.stlouisfed.org" in url:
            return fixture_text("fred_sofr_excerpt.csv").encode()
        raise AssertionError(f"unexpected URL in test: {url}")


def test_nsm_discovery_keeps_only_nav_announcements():
    web = FakeWeb()
    src = FcaNsmHoldings(Fetcher(transport=web), vehicle="NBPE", lei="213800ujh93nh8iofq77",
                         headline_include="NAV|Net Asset Value", headline_exclude="Kepler|Transaction in Own")
    found = src.discover()
    heads = [a["headline"] for a in found]
    assert len(found) == 5 and all("NAV" in h for h in heads)
    assert not any("Kepler" in h or "Own Shares" in h or "Interim Results" in h for h in heads)
    assert found[0]["url"].startswith(ARTEFACT_BASE + "NSM/GNW/") and found[0]["published"] == date(2026, 9, 23)
    url, body, headers = web.calls[0]
    sent = json.loads(body)
    assert sent == search_body("213800UJH93NH8IOFQ77", 0) and headers["Content-Type"] == "application/json"
    assert sent["criteriaObj"]["criteria"][0]["value"] == ["", "213800UJH93NH8IOFQ77", "disclose_org", "related_org"]


def test_nsm_load_deduplicates_reports_with_the_same_date():
    src = FcaNsmHoldings(Fetcher(transport=FakeWeb()), vehicle="NBPE", lei="x", headline_include="NAV")
    snaps = src.load()                               # the fake serves the April page for every announcement
    assert len(snaps) == 1 and snaps[0].as_of == date(2026, 4, 30) and snaps[0].published == date(2026, 9, 23)
    assert any(f.code == "H03" for f in src.findings)


def test_calpers_plug_through_fetcher():
    tr = CalpersTrackRecord(Fetcher(transport=FakeWeb())).load()
    assert len(tr.funds) == 15 and tr.lp == "CalPERS"


def test_yahoo_chart_real_response():
    rows, cur = parse_yahoo_chart(fixture_text("yahoo_chart_xlk_5d.json"))
    assert cur == "USD" and [r[0] for r in rows] == [date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5), date(2026, 10, 6)]
    assert rows[-1][1:] == (202.0, 202.0) and rows[0][2] == 195.75
    got = YahooChartPrices(Fetcher(transport=FakeWeb())).history("XLK", date(2026, 10, 1), date(2026, 10, 5))
    assert [r[0] for r in got] == [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5)]


def test_fred_csv_real_rows_and_missing_values():
    rows = parse_fred_csv(fixture_text("fred_sofr_excerpt.csv"))
    assert rows[0] == (date(2021, 8, 2), 0.05) and rows[-1] == (date(2026, 10, 5), 3.89)
    assert date(2021, 8, 5) not in [r[0] for r in rows]          # FRED writes "." when there is no value
    got = FredRates(Fetcher(transport=FakeWeb())).history("SOFR", date(2026, 10, 1), date(2026, 10, 31))
    assert got == [(date(2026, 10, 1), 3.87), (date(2026, 10, 2), 3.88), (date(2026, 10, 5), 3.89)]


def test_tiingo_parser_on_a_synthetic_payload():
    """SYNTHETIC: written from Tiingo's documented response shape. The Tiingo plug was not run live."""
    payload = json.dumps([{"date": "2026-10-05T00:00:00.000Z", "close": 200.93, "adjClose": 200.93},
                          {"date": "2026-10-06T00:00:00.000Z", "close": 202.0, "adjClose": 202.0}])
    assert parse_tiingo(payload) == [(date(2026, 10, 5), 200.93, 200.93), (date(2026, 10, 6), 202.0, 202.0)]
