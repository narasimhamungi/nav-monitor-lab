"""Source plugs and the registry that turns a `plug:` name in a config into an object."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..net import Fetcher
from .base import PriceBook, RateBook
from .calpers import CalpersTrackRecord
from .fca_nsm import FcaNsmHoldings
from .files import FileHoldings, FilePrices, FileRates, FileTrackRecord
from .market import FredRates, TiingoPrices, YahooChartPrices

HOLDINGS_PLUGS = ("file", "fca_nsm")
TRACK_PLUGS = ("file", "calpers_html")
PRICE_PLUGS = ("file", "yahoo_chart", "tiingo")
RATE_PLUGS = ("file", "fred_csv")


def _need(name: str, allowed: tuple[str, ...], kind: str) -> None:
    if name not in allowed:
        raise ValueError(f"unknown {kind} plug '{name}'; available: {', '.join(allowed)}")


def holdings_source(cfg: dict, *, fetcher: Fetcher | None = None, data_dir: Path | None = None):
    plug = cfg["plug"]
    _need(plug, HOLDINGS_PLUGS, "holdings")
    if plug == "file":
        return FileHoldings(data_dir / cfg["holdings_csv"], data_dir / cfg["snapshots_csv"], cfg.get("vehicle"))
    return FcaNsmHoldings(fetcher, vehicle=cfg["vehicle"], lei=cfg["lei"], headline_include=cfg["headline_include"],
                          headline_exclude=cfg.get("headline_exclude", ""),
                          since=date.fromisoformat(str(cfg["since"])) if cfg.get("since") else None,
                          columns=cfg.get("columns"), currency=cfg.get("currency", "USD"), unit=cfg.get("unit", "millions"),
                          max_announcements=cfg.get("max_announcements"), realisations=cfg.get("realisations"))


def track_source(cfg: dict, *, fetcher: Fetcher | None = None, data_dir: Path | None = None):
    plug = cfg["plug"]
    _need(plug, TRACK_PLUGS, "track-record")
    if plug == "file":
        return FileTrackRecord(data_dir / cfg["csv"], cfg.get("url", ""))
    return CalpersTrackRecord(fetcher, **({"url": cfg["url"]} if cfg.get("url") else {}))


def price_source(cfg: dict, *, fetcher: Fetcher | None = None, data_dir: Path | None = None):
    plug = cfg["plug"]
    _need(plug, PRICE_PLUGS, "price")
    if plug == "file":
        return FilePrices(data_dir / cfg["csv"])
    return YahooChartPrices(fetcher) if plug == "yahoo_chart" else TiingoPrices(fetcher)


def rate_source(cfg: dict, *, fetcher: Fetcher | None = None, data_dir: Path | None = None):
    plug = cfg["plug"]
    _need(plug, RATE_PLUGS, "rate")
    return FileRates(data_dir / cfg["csv"]) if plug == "file" else FredRates(fetcher)


__all__ = ["PriceBook", "RateBook", "holdings_source", "track_source", "price_source", "rate_source",
           "HOLDINGS_PLUGS", "TRACK_PLUGS", "PRICE_PLUGS", "RATE_PLUGS"]
