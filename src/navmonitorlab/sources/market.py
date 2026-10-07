"""Market-data plugs: prices and reference rates.

- `yahoo_chart`: Yahoo Finance chart endpoint, no key. Unofficial and unlicensed: fine for a personal
  tool, not something a firm would rely on. Response shape captured live on 2026-10-07.
- `tiingo`: Tiingo end-of-day API, needs TIINGO_API_KEY. Written from Tiingo's documented response
  shape; it was NOT exercised against the live service when this was built (docs/PLAN.md).
- `fred_csv`: FRED's CSV download for a series (SOFR, SONIA), no key. Shape captured live 2026-10-07.

Stooq was tried and dropped: its CSV download answered "Access denied" on 2026-10-07.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from ..net import FetchError, Fetcher


def parse_yahoo_chart(payload: str | bytes) -> tuple[list[tuple[date, float, float]], str]:
    j = json.loads(payload)
    if j.get("chart", {}).get("error"):
        raise FetchError(f"Yahoo chart error: {j['chart']['error']}")
    res = j["chart"]["result"][0]
    off = res["meta"].get("gmtoffset", 0)
    ts = res.get("timestamp") or []
    close = res["indicators"]["quote"][0]["close"]
    adj = (res["indicators"].get("adjclose") or [{"adjclose": close}])[0]["adjclose"]
    rows = []
    for t, a, c in zip(ts, adj, close):
        if a is None or c is None:
            continue
        d = (datetime.fromtimestamp(t, tz=timezone.utc) + timedelta(seconds=off)).date()
        rows.append((d, float(a), float(c)))
    return rows, res["meta"].get("currency", "")


class YahooChartPrices:
    BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"

    def __init__(self, fetcher: Fetcher):
        self.f = fetcher
        self.currency: dict[str, str] = {}

    def history(self, symbol: str, start: date, end: date) -> list[tuple[date, float, float]]:
        p1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
        p2 = int((datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)).timestamp())
        rows, cur = parse_yahoo_chart(self.f.get(f"{self.BASE}{quote(symbol)}?period1={p1}&period2={p2}&interval=1d",
                                                 label=f"yahoo_chart:{symbol}"))
        self.currency[symbol] = cur
        return [r for r in rows if start <= r[0] <= end]


def parse_tiingo(payload: str | bytes) -> list[tuple[date, float, float]]:
    return [(date.fromisoformat(r["date"][:10]), float(r["adjClose"]), float(r["close"])) for r in json.loads(payload)]


class TiingoPrices:
    BASE = "https://api.tiingo.com/tiingo/daily/"

    def __init__(self, fetcher: Fetcher, token: str | None = None):
        self.f = fetcher
        self.token = token or os.environ.get("TIINGO_API_KEY", "")
        self.currency: dict[str, str] = {}

    def history(self, symbol: str, start: date, end: date) -> list[tuple[date, float, float]]:
        if not self.token:
            raise FetchError("Tiingo plug needs TIINGO_API_KEY in the environment (or .env)")
        url = f"{self.BASE}{quote(symbol)}/prices?startDate={start.isoformat()}&endDate={end.isoformat()}&format=json"
        return parse_tiingo(self.f.get(url, headers={"Authorization": f"Token {self.token}"}, label=f"tiingo:{symbol}"))


def parse_fred_csv(text: str) -> list[tuple[date, float]]:
    """'observation_date,SOFR' then one row per day; FRED writes '.' for days with no value."""
    out = []
    for line in text.strip().splitlines()[1:]:
        d, _, v = line.partition(",")
        v = v.strip()
        if v and v != ".":
            out.append((date.fromisoformat(d.strip()), float(v)))
    return out


class FredRates:
    BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"

    def __init__(self, fetcher: Fetcher):
        self.f = fetcher

    def history(self, series: str, start: date, end: date) -> list[tuple[date, float]]:
        text = self.f.text(f"{self.BASE}?id={quote(series)}&cosd={start.isoformat()}&coed={end.isoformat()}", label=f"fred:{series}")
        return [r for r in parse_fred_csv(text) if start <= r[0] <= end]
