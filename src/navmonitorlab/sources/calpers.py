"""Track-record plug: CalPERS Private Equity Program fund performance review (public web page).

CalPERS publishes one table of every active partnership it holds: vintage, commitment, cash in, cash
out, cash out plus remaining value, net IRR and multiple. It is one investor's book, active funds only,
with interim values. Those limits are stated in docs/limitations.md and repeated in every memo.

The markup this parser is tested against is a real excerpt of the page captured on 2026-10-07.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from ..htmltable import find_table, parse
from ..net import Fetcher
from ..schema import Finding, FundRecord, TrackRecord
from .files import multiple_text, pct_text_to_fraction

URL = "https://www.calpers.ca.gov/investments/about-investment-office/investment-organization/pep-fund-performance-print"
COLUMNS = {
    "fund": ["Fund"], "vintage": ["Vintage Year"], "committed": ["Capital Committed"], "cash_in": ["Cash In"],
    "cash_out": ["Cash Out"], "total_value": ["Cash Out & Remaining Value"], "net_irr": ["Net IRR"],
    "multiple": ["Investment Multiple"],
}
_ASOF = re.compile(r"[Aa]s of ([A-Z][a-z]+ \d{1,2}, \d{4})")


def _money(text: str) -> float:
    return float(text.replace("$", "").replace(",", "").strip() or 0)


def parse_page(html: str, source_url: str = URL, lp: str = "CalPERS", program: str = "Private Equity"
               ) -> tuple[TrackRecord, list[Finding]]:
    tables, text = parse(html)
    found = find_table(tables, COLUMNS)
    if found is None:
        raise ValueError("CalPERS page: no table with the expected column headings (page layout may have changed)")
    table, hdr, col = found
    m = _ASOF.search(text)
    if not m:
        raise ValueError("CalPERS page: could not find the 'As of <date>' statement")
    as_of = datetime.strptime(m.group(1), "%B %d, %Y").date()
    funds, findings = [], []
    for row in table.rows[hdr + 1:]:
        if all(c.is_header for c in row) or len(row) <= max(col.values()):
            continue                                        # the page repeats the header row as a footer
        name = row[col["fund"]].text
        try:
            funds.append(FundRecord(
                fund=name, vintage=int(row[col["vintage"]].text), committed=_money(row[col["committed"]].text),
                cash_in=_money(row[col["cash_in"]].text), cash_out=_money(row[col["cash_out"]].text),
                total_value=_money(row[col["total_value"]].text), net_irr=pct_text_to_fraction(row[col["net_irr"]].text),
                multiple=multiple_text(row[col["multiple"]].text), footnote=row[col["net_irr"]].sup))
        except ValueError:
            findings.append(Finding("warn", "T00", name, "Row could not be read as numbers; row skipped",
                                    observed=" | ".join(c.text for c in row)))
    return TrackRecord(lp=lp, program=program, as_of=as_of, source_url=source_url, funds=funds), findings


class CalpersTrackRecord:
    def __init__(self, fetcher: Fetcher, url: str = URL, lp: str = "CalPERS", program: str = "Private Equity"):
        self.f, self.url, self.lp, self.program = fetcher, url, lp, program
        self.findings: list[Finding] = []

    def load(self) -> TrackRecord:
        tr, self.findings = parse_page(self.f.text(self.url, label="calpers_pep"), self.url, self.lp, self.program)
        return tr


def as_of_guard(tr: TrackRecord, today: date) -> Finding | None:
    """CalPERS states a lag of about two quarters; flag anything older than that."""
    age = (today - tr.as_of).days
    if age > 270:
        return Finding("warn", "T10", tr.lp, "Track-record data is older than three quarters", observed=f"{age} days", threshold="270 days")
    return None
