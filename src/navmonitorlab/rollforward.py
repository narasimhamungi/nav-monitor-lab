"""Roll reported fair values forward to today using listed sector moves.

Private marks are stale by construction: a monthly report carries valuations that are mostly one or
two quarter-ends old. This estimates where the marks would be if they had moved with their listed
sector since the date they were struck, scaled by a pass-through factor. It is an ESTIMATE, not a
valuation, and every output says so. The backtest module measures how wrong it has been.
"""
from __future__ import annotations

from datetime import date

from .collateral import PoolAsset
from .schema import Finding, Snapshot
from .sources.base import PriceBook


def proxy_for(sector: str, sector_proxy: dict, default_proxy: str) -> str:
    return sector_proxy.get(sector, default_proxy)


def private_window_return(prices: PriceBook, symbol: str, mix: list[tuple[date, float]], to: date, max_gap: int = 10) -> float:
    """Proxy return from each valuation date to `to`, weighted by the share of marks struck on that date."""
    p_to = prices.asof(symbol, to, max_gap_days=max_gap)
    return sum(w * (p_to / prices.asof(symbol, d, max_gap_days=max_gap) - 1.0) for d, w in mix)


def mix_index(prices: PriceBook, symbol: str, mix: list[tuple[date, float]], max_gap: int = 10) -> float:
    """Weighted proxy level across a snapshot's valuation dates (used to compare two snapshots)."""
    return sum(w * prices.asof(symbol, d, max_gap_days=max_gap) for d, w in mix)


def roll_forward(snap: Snapshot, pool: list[PoolAsset], prices: PriceBook, market_cfg: dict, *, pass_through: float,
                 to: date | None = None) -> dict:
    """Estimated value of each pool asset at `to` (default: the latest date every needed proxy has a price).

    Private holding:  est = reported x (1 + pass_through x proxy return since the valuation dates)
    Quoted holding:   est = reported x (1 + listed_pass_through x proxy return since the report date)
    """
    rf = market_cfg["roll_forward"]
    sector_proxy, default_proxy = market_cfg["sector_proxy"], market_cfg["default_proxy"]
    gap = int(rf.get("max_price_gap_days", 10))
    findings: list[Finding] = []
    scope = f"{snap.vehicle} {snap.as_of.isoformat()}"
    symbols = sorted({proxy_for(a.sector, sector_proxy, default_proxy) for a in pool})
    missing = [s for s in symbols if not prices.has(s)]
    if missing:
        findings.append(Finding("warn", "M01", scope, "No prices for a sector proxy; affected holdings are carried at reported value",
                                observed=", ".join(missing)))
    usable = [s for s in symbols if prices.has(s)]
    if not usable:
        return {"ran": False, "to": None, "rows": [], "values": {}, "findings": findings, "pass_through": pass_through}
    to = to or prices.latest_common_date(usable)
    if to < snap.as_of:
        findings.append(Finding("warn", "M02", scope, "Price history ends before the report date; roll-forward not run",
                                observed=f"prices to {to}, report dated {snap.as_of}"))
        return {"ran": False, "to": to, "rows": [], "values": {}, "findings": findings, "pass_through": pass_through}
    mix = snap.private_mix()
    rows, values = [], {}
    for a in pool:
        sym = proxy_for(a.sector, sector_proxy, default_proxy)
        mapped = a.sector in sector_proxy
        try:
            if not prices.has(sym):
                raise KeyError(sym)
            if a.listed:
                r, beta, since = prices.asof(sym, to, max_gap_days=gap) / prices.asof(sym, snap.as_of, max_gap_days=gap) - 1.0, \
                    float(rf.get("listed_pass_through", 1.0)), snap.as_of
            else:
                r, beta, since = private_window_return(prices, sym, mix, to, gap), pass_through, min(d for d, _ in mix)
        except KeyError as e:
            findings.append(Finding("warn", "M03", a.key, "Price lookup failed; holding carried at reported value", observed=str(e)))
            r, beta, since = 0.0, 0.0, snap.as_of
        est = a.fair_value * (1.0 + beta * r)
        values[a.key] = est
        rows.append({"company": a.company, "key": a.key, "sector": a.sector, "proxy": sym, "proxy_is_default": not mapped, "listed": a.listed,
                     "eligible": a.eligible, "reported_fv": a.fair_value, "oldest_mark": since.isoformat(), "proxy_return": r,
                     "pass_through": beta, "estimated_fv": est, "change": est / a.fair_value - 1.0 if a.fair_value else 0.0})
    unmapped = sorted({r["sector"] for r in rows if r["proxy_is_default"]})
    if unmapped:
        findings.append(Finding("info", "M04", scope, "Sectors with no proxy in configs/market.yaml use the default proxy",
                                observed=f"{', '.join(unmapped)} -> {default_proxy}"))
    rep = sum(r["reported_fv"] for r in rows)
    est = sum(r["estimated_fv"] for r in rows)
    age_today = sum(w * (to - d).days for d, w in mix)
    return {"ran": True, "to": to, "rows": rows, "values": values, "findings": findings, "pass_through": pass_through,
            "reported_fv": rep, "estimated_fv": est, "change": est / rep - 1.0 if rep else 0.0,
            "weighted_private_mark_age_days": age_today, "days_since_report": (to - snap.as_of).days}


def discount_to_nav(snap: Snapshot, prices: PriceBook, listed_cfg: dict | None, to: date | None = None) -> dict | None:
    """The market's own haircut: how far the vehicle's share price sits below its last reported NAV per share.
    It reflects more than doubt about the marks (fees, leverage, liquidity), so it is context, not a valuation."""
    if not listed_cfg or not prices.has(listed_cfg["symbol"]):
        return None
    nav = getattr(snap, listed_cfg.get("nav_field", "nav_per_share_gbp"), None)
    if not nav:
        return None
    sym = listed_cfg["symbol"]
    to = to or prices.last_date(sym)
    div = float(listed_cfg.get("price_divisor", 1))
    try:
        price = prices.asof(sym, to, adjusted=False) / div
    except KeyError:
        return None                                   # no usable share price near the date: say nothing, do not guess
    try:
        at_report = prices.asof(sym, snap.as_of, adjusted=False) / div
    except KeyError:
        at_report = None
    return {"symbol": sym, "price_date": prices.asof_date(sym, to).isoformat(),
            "share_price": price, "nav_per_share": nav, "nav_date": snap.as_of.isoformat(), "discount": 1.0 - price / nav,
            "discount_at_report_date": None if at_report is None else 1.0 - at_report / nav}
