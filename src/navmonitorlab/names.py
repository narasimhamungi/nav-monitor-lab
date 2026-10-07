"""Stable names. Publishers rename companies, add tickers and footnote marks, and relabel sectors;
comparing one month with another needs a key that survives that. The maps live in the vehicle config."""
from __future__ import annotations

import re

from .schema import Holding, Snapshot

_TICKER = re.compile(r"\s*\(\s*(?:NYSE|NASDAQ|LSE|OB|AMS|XETRA)\s*[:.]\s*[A-Z0-9.]+\s*\)", re.I)
_MARK = re.compile(r"(\*+|(?<=Company)\d)\s*$")


def canonical_company(name: str, aliases: dict[str, str]) -> str:
    """Published name -> comparison key: alias map first, then ticker and footnote marks removed."""
    name = name.strip()
    if name in aliases:
        return aliases[name]
    bare = _MARK.sub("", _TICKER.sub("", name)).strip()
    return aliases.get(bare, bare)


def canonical_sector(sector: str, aliases: dict[str, str]) -> str:
    return aliases.get(sector.strip(), sector.strip())


def keyed(snap: Snapshot, company_aliases: dict[str, str]) -> dict[str, Holding]:
    """Holdings by comparison key. Undisclosed names that collide within one snapshot (the publisher has
    listed two "Undisclosed Technology Company" lines in the same month) are numbered by size so
    neither is lost; they are never matched across months."""
    out: dict[str, Holding] = {}
    seen: dict[str, int] = {}
    for h in sorted(snap.holdings, key=lambda x: -x.fair_value):
        k = canonical_company(h.company, company_aliases)
        if k in out:
            seen[k] = seen.get(k, 1) + 1
            k = f"{k} [{seen[k]}]"
        out[k] = h
    return out
