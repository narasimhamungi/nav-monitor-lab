"""Turn a published holdings table into a collateral pool: which names count, which do not, and why."""
from __future__ import annotations

from dataclasses import dataclass

from .names import canonical_company, canonical_sector
from .schema import Snapshot


@dataclass(frozen=True)
class PoolAsset:
    key: str            # comparison key (canonical company name)
    company: str        # as published
    sponsor: str
    sector: str         # after sector aliases
    vintage: int | None
    fair_value: float
    listed: bool
    eligible: bool
    reason: str         # why it is excluded; "" when eligible

    def row(self) -> dict:
        return dict(self.__dict__)


def build_pool(snap: Snapshot, vehicle_cfg: dict, collateral_cfg: dict) -> list[PoolAsset]:
    """Every published holding, marked eligible or not. Holdings outside the published table get no
    credit at all: they are simply not in the pool."""
    aliases, sector_aliases = vehicle_cfg.get("company_aliases") or {}, vehicle_cfg.get("sector_aliases") or {}
    excluded_names = {n.lower() for n in collateral_cfg.get("exclude_names") or []}
    min_fv = float(collateral_cfg.get("min_fair_value") or 0.0)
    seen: dict[str, int] = {}
    out = []
    for h in sorted(snap.holdings, key=lambda x: -x.fair_value):
        key = canonical_company(h.company, aliases)
        if key in seen:
            seen[key] += 1
            key = f"{key} [{seen[key]}]"
        else:
            seen[key] = 1
        reason = ""
        if collateral_cfg.get("exclude_undisclosed", True) and h.is_undisclosed:
            reason = "name or sponsor not disclosed"
        elif key.lower() in excluded_names or h.company.lower() in excluded_names:
            reason = "excluded by name in configs/facility.yaml"
        elif h.fair_value < min_fv:
            reason = f"below minimum fair value {min_fv:g}"
        out.append(PoolAsset(key=key, company=h.company, sponsor=h.sponsor, sector=canonical_sector(h.sector, sector_aliases),
                             vintage=h.vintage, fair_value=h.fair_value, listed=h.is_listed, eligible=not reason, reason=reason))
    return out


def concentration(values: list[float]) -> dict:
    """Shares of the largest names and the Herfindahl index, on whatever values are passed in."""
    tot = sum(values)
    if tot <= 0:
        return {"n": 0, "top1": 0.0, "top5": 0.0, "top10": 0.0, "hhi": 0.0, "effective_names": 0.0}
    v = sorted(values, reverse=True)
    hhi = sum((x / tot) ** 2 for x in v)
    return {"n": len(v), "top1": v[0] / tot, "top5": sum(v[:5]) / tot, "top10": sum(v[:10]) / tot, "hhi": hhi,
            "effective_names": 1 / hhi if hhi else 0.0}


def sector_mix(pool: list[PoolAsset], eligible_only: bool = True) -> dict[str, float]:
    rows = [a for a in pool if a.eligible or not eligible_only]
    tot = sum(a.fair_value for a in rows)
    mix: dict[str, float] = {}
    for a in rows:
        mix[a.sector] = mix.get(a.sector, 0.0) + (a.fair_value / tot if tot else 0.0)
    return dict(sorted(mix.items(), key=lambda kv: -kv[1]))


def pool_summary(snap: Snapshot, pool: list[PoolAsset]) -> dict:
    elig = [a for a in pool if a.eligible]
    published = sum(a.fair_value for a in pool)
    e = sum(a.fair_value for a in elig)
    portfolio = snap.implied_portfolio_fv
    return {
        "as_of": snap.as_of.isoformat(), "published_names": len(pool), "published_fv": published,
        "stated_total_fv": snap.stated_total_fv, "stated_share_of_portfolio": snap.stated_total_pct,
        "implied_portfolio_fv": portfolio, "eligible_names": len(elig), "eligible_fv": e,
        "excluded_names": len(pool) - len(elig), "excluded_fv": published - e,
        "undisclosed_share_of_published": (sum(a.fair_value for a in pool if not a.eligible and "disclosed" in a.reason) / published) if published else 0.0,
        "eligible_share_of_portfolio": (e / portfolio) if portfolio else None,
        "listed_share_of_eligible": (sum(a.fair_value for a in elig if a.listed) / e) if e else 0.0,
        **{f"eligible_{k}": v for k, v in concentration([a.fair_value for a in elig]).items()},
    }
