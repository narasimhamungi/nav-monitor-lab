"""Holdings plug: a listed vehicle's monthly NAV announcements from the FCA National Storage Mechanism.

Two steps, both against the official UK regulatory archive:
1. discover the announcements for a company (by LEI) through the NSM search API;
2. fetch each announcement and read its holdings table, valuation-date breakdown and NAV per share.

The request and response shapes were captured from the live service on 2026-10-07 (tests/fixtures/).
The announcement parser is driven by column headings in the vehicle config, so another vehicle that
publishes a holdings table needs a config file, not new code. Anything it cannot read becomes a
finding; it never guesses.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime

from ..htmltable import find_table, parse
from ..net import Fetcher
from ..realisations import compile_patterns, read_statements
from ..schema import Finding, Holding, Snapshot

API_URL = "https://api.data.fca.org.uk/search?index=nsm-search"
ARTEFACT_BASE = "https://data.fca.org.uk/artefacts/"
PAGE = 400

DEFAULT_COLUMNS = {
    "company": ["Company Name", "Company", "Investment"],
    "vintage": ["Vintage", "Vintage Year"],
    "sponsor": ["Lead Sponsor", "Sponsor"],
    "sector": ["Sector", "Industry"],
    "fair_value": ["Fair Value ($m)", "Fair Value($m)", "Fair Value"],
    "pct": ["% of FV", "% of Fair Value", "% of Portfolio"],
}
_MIX = re.compile(r"(\d+(?:\.\d+)?)% of the portfolio was valued as of (\d{1,2} [A-Za-z]+ \d{4})")
_NAV = re.compile(r"NAV per share (?:was |of |increased to |decreased to )?\$([\d.]+) ?\(£([\d.]+)\)", re.I)
_ASOF = re.compile(r"Supplementary Information \(as of (\d{1,2} [A-Za-z]+ \d{4})\)", re.I)
_CASH = re.compile(r"\$([\d,.]+) million of cash(?: and liquid investments| / liquid investments)?(?!\s+and undrawn)")
_UNDRAWN = re.compile(r"\$([\d,.]+) million of undrawn credit")
_INV = re.compile(r"investment level of (\d+(?:\.\d+)?)%", re.I)


def _d(text: str) -> date:
    return datetime.strptime(text.strip(), "%d %B %Y").date()


def _num(text: str) -> float | None:
    t = text.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def parse_announcement(html: str, *, vehicle: str, source_url: str, published: date | None, headline: str = "",
                       columns: dict | None = None, currency: str = "USD", unit: str = "millions",
                       realisation_patterns: dict | None = None) -> tuple[Snapshot | None, list[Finding]]:
    """Read one announcement. Returns (snapshot or None, findings).

    `realisation_patterns` (from `compile_patterns`) switches on reading cash received from realisations.
    """
    findings: list[Finding] = []
    tables, text = parse(html)
    flat = text.replace("\n", " ")
    found = find_table(tables, columns or DEFAULT_COLUMNS)
    if found is None:
        return None, [Finding("warn", "H00", source_url, "No holdings table with the expected column headings; announcement skipped",
                              observed=f"{len(tables)} tables on page")]
    table, hdr, col = found
    holdings: list[Holding] = []
    total_fv = total_pct = None
    for row in table.rows[hdr + 1:]:
        cells = [c.text for c in row]
        if not any(cells):
            continue
        if cells[0].lower().startswith("total"):
            nums = [n for n in (_num(c) for c in cells[1:]) if n is not None]
            if len(nums) >= 2:
                total_fv, total_pct = nums[-2], nums[-1] / 100.0
            continue
        if len(cells) <= max(col.values()):
            findings.append(Finding("warn", "H01", source_url, "Row has fewer cells than the header; row skipped", observed=" | ".join(cells)))
            continue
        fv, pct = _num(cells[col["fair_value"]]), _num(cells[col["pct"]])
        if fv is None:
            findings.append(Finding("warn", "H01", source_url, "Fair value is not a number; row skipped", observed=" | ".join(cells)))
            continue
        vint = _num(cells[col["vintage"]])
        holdings.append(Holding(company=cells[col["company"]], vintage=int(vint) if vint else None, sponsor=cells[col["sponsor"]],
                                sector=cells[col["sector"]], fair_value=fv, pct_of_fv=None if pct is None else round(pct / 100.0, 4)))
    mix = [(_d(m.group(2)), float(m.group(1)) / 100.0) for m in _MIX.finditer(flat)]
    asof_m = _ASOF.search(flat)
    if mix:
        as_of = max(d for d, _ in mix)
    elif asof_m:
        as_of = _d(asof_m.group(1))
        findings.append(Finding("warn", "H02", source_url, "No valuation-date breakdown found; holdings treated as valued at the report date"))
    else:
        return None, findings + [Finding("warn", "H00", source_url, "Could not establish the report date; announcement skipped")]
    nav = _NAV.search(flat)
    cash, undrawn, inv = _CASH.search(flat), _UNDRAWN.search(flat), _INV.search(flat)
    snap = Snapshot(vehicle=vehicle, as_of=as_of, published=published, source_url=source_url, currency=currency, unit=unit,
                    holdings=holdings, stated_total_fv=total_fv, stated_total_pct=total_pct,
                    nav_per_share_usd=float(nav.group(1)) if nav else None, nav_per_share_gbp=float(nav.group(2)) if nav else None,
                    valuation_mix=mix, investment_level_pct=float(inv.group(1)) if inv else None,
                    cash_m=_num(cash.group(1)) if cash else None, undrawn_credit_m=_num(undrawn.group(1)) if undrawn else None,
                    headline=headline)
    if realisation_patterns:
        got, rf = read_statements(text, as_of, realisation_patterns, scope=f"{vehicle} {as_of}")
        snap.realised_ytd_m, snap.realised_month_m = got["realised_ytd_m"], got["realised_month_m"]
        snap.realised_prior_year_m, snap.realised_text = got["realised_prior_year_m"], got["realised_text"]
        findings += rf
    return snap, findings


def search_body(lei: str, start: int) -> dict:
    """The NSM web application's own query shape: company by LEI, latest versions only, newest first."""
    return {"from": start, "size": PAGE, "sort": "publication_date", "sortorder": "desc",
            "criteriaObj": {"criteria": [{"name": "company_lei", "value": ["", lei.upper(), "disclose_org", "related_org"]},
                                         {"name": "latest_flag", "value": "Y"}], "dateCriteria": None}}


class FcaNsmHoldings:
    def __init__(self, fetcher: Fetcher, *, vehicle: str, lei: str, headline_include: str, headline_exclude: str = "",
                 since: date | None = None, columns: dict | None = None, currency: str = "USD", unit: str = "millions",
                 api_url: str = API_URL, artefact_base: str = ARTEFACT_BASE, max_announcements: int | None = None,
                 realisations: dict | None = None):
        self.f, self.vehicle, self.lei = fetcher, vehicle, lei
        self.inc = re.compile(headline_include, re.I)
        self.exc = re.compile(headline_exclude, re.I) if headline_exclude else None
        self.since, self.columns, self.currency, self.unit = since, columns, currency, unit
        self.api_url, self.artefact_base, self.max = api_url, artefact_base, max_announcements
        self.realisation_patterns = compile_patterns(realisations) if realisations else None
        self.findings: list[Finding] = []

    def discover(self) -> list[dict]:
        """Announcements that look like monthly NAV updates, newest first."""
        hits, start, total = [], 0, None
        while total is None or start < total:
            raw = self.f.get(self.api_url, data=search_body(self.lei, start), label="fca_nsm_search",
                             headers={"Origin": "https://data.fca.org.uk", "Referer": "https://data.fca.org.uk/"})
            payload = json.loads(raw)
            page = payload["hits"]["hits"]
            total = payload["hits"]["total"]["value"]
            hits += [h["_source"] for h in page]
            start += PAGE
            if len(page) < PAGE:                    # a short page is the last one
                break
        out = []
        for s in hits:
            head, link = (s.get("headline") or "").strip(), s.get("download_link") or ""
            pub = date.fromisoformat((s.get("publication_date") or "")[:10])
            if not link.lower().endswith((".html", ".htm")) or not self.inc.search(head):
                continue
            if self.exc and self.exc.search(head):
                continue
            if self.since and pub < self.since:
                continue
            out.append({"published": pub, "headline": re.sub(r"\s+", " ", head), "url": self.artefact_base + link})
        return out[: self.max] if self.max else out

    def load(self) -> list[Snapshot]:
        by_date: dict[date, Snapshot] = {}
        for a in self.discover():
            html = self.f.text(a["url"], label="fca_nsm_artefact")
            snap, fs = parse_announcement(html, vehicle=self.vehicle, source_url=a["url"], published=a["published"],
                                          headline=a["headline"], columns=self.columns, currency=self.currency, unit=self.unit,
                                          realisation_patterns=self.realisation_patterns)
            self.findings += fs
            if snap is None or not snap.holdings:
                continue
            prev = by_date.get(snap.as_of)
            if prev is None:
                by_date[snap.as_of] = snap
                continue
            self.findings.append(Finding("info", "H03", a["url"], "Two announcements carry the same report date; the later one is kept",
                                         observed=snap.as_of.isoformat()))
            if snap.published and prev.published and snap.published > prev.published:
                by_date[snap.as_of] = snap
        return [by_date[k] for k in sorted(by_date)]
