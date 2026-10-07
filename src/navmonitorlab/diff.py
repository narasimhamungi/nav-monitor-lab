"""What changed between two published reports. This is the monitoring half of the tool."""
from __future__ import annotations

from .collateral import concentration
from .names import canonical_sector, keyed
from .quality import stale_share, weighted_mark_age
from .schema import Snapshot


def diff_snapshots(prev: Snapshot, cur: Snapshot, vehicle_cfg: dict, policy: dict, watchlist: dict | None = None) -> dict:
    aliases, sector_aliases = vehicle_cfg.get("company_aliases") or {}, vehicle_cfg.get("sector_aliases") or {}
    k0, k1 = keyed(prev, aliases), keyed(cur, aliases)
    rank0 = {k: i + 1 for i, k in enumerate(sorted(k0, key=lambda k: -k0[k].fair_value))}
    rank1 = {k: i + 1 for i, k in enumerate(sorted(k1, key=lambda k: -k1[k].fair_value))}
    watch = {w.lower() for w in (watchlist or {}).get("companies") or []}
    thr = float(policy.get("mover_threshold", 0.15))
    rows = []
    for k in sorted(set(k0) | set(k1), key=lambda k: -(k1[k].fair_value if k in k1 else k0[k].fair_value)):
        h0, h1 = k0.get(k), k1.get(k)
        status = "held" if h0 and h1 else ("entered" if h1 else "left")
        change = (h1.fair_value / h0.fair_value - 1.0) if h0 and h1 and h0.fair_value else None
        notes = []
        if h0 and h1:
            if h0.sponsor != h1.sponsor:
                notes.append(f"sponsor label {h0.sponsor} -> {h1.sponsor}")
            if canonical_sector(h0.sector, sector_aliases) != canonical_sector(h1.sector, sector_aliases):
                notes.append(f"sector {h0.sector} -> {h1.sector}")
            if h0.vintage != h1.vintage:
                notes.append(f"vintage {h0.vintage} -> {h1.vintage}")
            if h0.company != h1.company:
                notes.append(f"published as '{h0.company}' then '{h1.company}'")
        undisclosed = (h1 or h0).is_undisclosed
        if undisclosed and status != "held":
            notes.append("undisclosed names are matched by label only; a relabel shows as one leaving and one entering")
        rows.append({"company": k, "status": status, "fv_prev": h0.fair_value if h0 else None, "fv_cur": h1.fair_value if h1 else None,
                     "change": change, "rank_prev": rank0.get(k), "rank_cur": rank1.get(k), "listed": (h1 or h0).is_listed,
                     "undisclosed": undisclosed, "watchlist": k.lower() in watch,
                     "flag": bool(status != "held" or (change is not None and abs(change) >= thr) or k.lower() in watch),
                     "notes": "; ".join(notes)})
    c0, c1 = concentration([h.fair_value for h in prev.holdings]), concentration([h.fair_value for h in cur.holdings])

    def sector_shares(s: Snapshot) -> dict[str, float]:
        tot, m = s.total_fv, {}
        for h in s.holdings:
            sec = canonical_sector(h.sector, sector_aliases)
            m[sec] = m.get(sec, 0.0) + h.fair_value / tot
        return m

    m0, m1 = sector_shares(prev), sector_shares(cur)
    sectors = [{"sector": s, "share_prev": m0.get(s, 0.0), "share_cur": m1.get(s, 0.0), "change_pp": (m1.get(s, 0.0) - m0.get(s, 0.0)) * 100}
               for s in sorted(set(m0) | set(m1), key=lambda s: -abs(m1.get(s, 0.0) - m0.get(s, 0.0)))]
    stale_days = int(policy.get("stale_days", 100))

    def meta(s: Snapshot) -> dict:
        return {"as_of": s.as_of.isoformat(), "published": s.published.isoformat() if s.published else "",
                "published_fv": s.total_fv, "stated_share_of_portfolio": s.stated_total_pct, "implied_portfolio_fv": s.implied_portfolio_fv,
                "nav_per_share_usd": s.nav_per_share_usd, "nav_per_share_gbp": s.nav_per_share_gbp,
                "weighted_mark_age_days": weighted_mark_age(s), "stale_share": stale_share(s, stale_days),
                "cash_m": s.cash_m, "undrawn_credit_m": s.undrawn_credit_m, "investment_level_pct": s.investment_level_pct}

    held = [r for r in rows if r["status"] == "held"]
    return {"prev": meta(prev), "cur": meta(cur), "rows": rows, "sectors": sectors,
            "entered": [r["company"] for r in rows if r["status"] == "entered"],
            "left": [r["company"] for r in rows if r["status"] == "left"],
            "movers": sorted([r for r in held if abs(r["change"]) >= thr], key=lambda r: -abs(r["change"])),
            "watch": [r for r in rows if r["watchlist"]],
            "held_value_change": (sum(r["fv_cur"] for r in held) / sum(r["fv_prev"] for r in held) - 1.0) if held else None,
            "concentration_prev": c0, "concentration_cur": c1, "mover_threshold": thr}


def diff_track_records(prev_rows: list[dict], cur_rows: list[dict]) -> dict:
    """New and dropped funds and the largest DPI moves between two track-record snapshots (rows from fund_metrics)."""
    p, c = {r["fund"]: r for r in prev_rows}, {r["fund"]: r for r in cur_rows}
    moved = []
    for k in set(p) & set(c):
        if p[k]["dpi"] is not None and c[k]["dpi"] is not None and abs(c[k]["dpi"] - p[k]["dpi"]) >= 0.05:
            moved.append({"fund": k, "dpi_prev": p[k]["dpi"], "dpi_cur": c[k]["dpi"], "tvpi_prev": p[k]["tvpi"], "tvpi_cur": c[k]["tvpi"]})
    return {"new": sorted(set(c) - set(p)), "dropped": sorted(set(p) - set(c)),
            "dpi_moves": sorted(moved, key=lambda r: -abs(r["dpi_cur"] - r["dpi_prev"]))}
