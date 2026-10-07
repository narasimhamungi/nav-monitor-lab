"""The four sockets. A plug is any class with the matching method; nothing else in the codebase
knows which plug is in use.

Swapping a free source for a professional one (Bloomberg, Preqin, a fund's own reporting pack) means
writing one class here and changing one `plug:` line in configs/. See docs/sources.md.
"""
from __future__ import annotations

import bisect
from datetime import date
from typing import Protocol

from ..schema import Snapshot, TrackRecord


class HoldingsSource(Protocol):
    def load(self) -> list[Snapshot]: ...            # oldest first


class TrackRecordSource(Protocol):
    def load(self) -> TrackRecord: ...


class PriceSource(Protocol):
    def history(self, symbol: str, start: date, end: date) -> list[tuple[date, float, float]]: ...
    # (date, adjusted close, close), oldest first


class RateSource(Protocol):
    def history(self, series: str, start: date, end: date) -> list[tuple[date, float]]: ...
    # (date, rate in percent), oldest first


class PriceBook:
    """Prices for many symbols, with 'last value on or before a date' lookups."""

    def __init__(self):
        self._dates: dict[str, list[date]] = {}
        self._adj: dict[str, list[float]] = {}
        self._close: dict[str, list[float]] = {}
        self.currency: dict[str, str] = {}

    def add(self, symbol: str, rows: list[tuple[date, float, float]], currency: str = "") -> None:
        rows = sorted(rows)
        self._dates[symbol] = [r[0] for r in rows]
        self._adj[symbol] = [r[1] for r in rows]
        self._close[symbol] = [r[2] for r in rows]
        if currency:
            self.currency[symbol] = currency

    def symbols(self) -> list[str]:
        return sorted(self._dates)

    def has(self, symbol: str) -> bool:
        return bool(self._dates.get(symbol))

    def rows(self, symbol: str) -> list[tuple[date, float, float]]:
        return list(zip(self._dates[symbol], self._adj[symbol], self._close[symbol]))

    def first_date(self, symbol: str) -> date:
        return self._dates[symbol][0]

    def last_date(self, symbol: str) -> date:
        return self._dates[symbol][-1]

    def latest_common_date(self, symbols: list[str]) -> date:
        return min(self.last_date(s) for s in symbols if self.has(s))

    def asof(self, symbol: str, d: date, adjusted: bool = True, max_gap_days: int = 10) -> float:
        """Last price on or before `d`. Raises if the symbol is missing or the nearest price is too old,
        so a gap in the data can never pass silently as a stale number."""
        if not self.has(symbol):
            raise KeyError(f"no prices for {symbol}")
        ds = self._dates[symbol]
        i = bisect.bisect_right(ds, d) - 1
        if i < 0:
            raise KeyError(f"{symbol}: no price on or before {d} (history starts {ds[0]})")
        if (d - ds[i]).days > max_gap_days:
            raise KeyError(f"{symbol}: nearest price to {d} is {ds[i]}, more than {max_gap_days} days earlier")
        return (self._adj if adjusted else self._close)[symbol][i]

    def asof_date(self, symbol: str, d: date) -> date:
        """The date of the price `asof` would return."""
        ds = self._dates[symbol]
        return ds[max(bisect.bisect_right(ds, d) - 1, 0)]

    def ret(self, symbol: str, d0: date, d1: date) -> float:
        return self.asof(symbol, d1) / self.asof(symbol, d0) - 1.0


class RateBook:
    def __init__(self):
        self._s: dict[str, list[tuple[date, float]]] = {}

    def add(self, series: str, rows: list[tuple[date, float]]) -> None:
        self._s[series] = sorted(rows)

    def has(self, series: str) -> bool:
        return bool(self._s.get(series))

    def rows(self, series: str) -> list[tuple[date, float]]:
        return list(self._s[series])

    def latest(self, series: str, on_or_before: date | None = None) -> tuple[date, float]:
        rows = self._s[series]
        if on_or_before is not None:
            rows = [r for r in rows if r[0] <= on_or_before]
        if not rows:
            raise KeyError(f"no {series} value on or before {on_or_before}")
        return rows[-1]
