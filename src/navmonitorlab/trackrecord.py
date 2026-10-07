"""Manager track records from an investor's published fund table.

What a lender wants from a sponsor's record is evidence that capital comes back, because the loan is
repaid from distributions. So the headline measures are realisation measures (DPI, the share of
mature funds that have returned their capital), with IRR kept as a secondary column. The investor
publishing the table says the same thing: interim IRRs alone are poor indicators.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from .schema import FundRecord, TrackRecord


@dataclass(frozen=True)
class FundMetrics:
    fund: str
    family: str          # "" when the fund name maps to no manager
    basis: str           # "name" | "inferred" | ""
    vintage: int
    age: int
    committed: float
    cash_in: float
    cash_out: float
    remaining: float
    dpi: float | None
    rvpi: float | None
    tvpi: float | None
    net_irr: float | None
    interim: bool        # carries the publisher's 'not meaningful' marker
    cohort_n: int
    cohort_rank_tvpi: float | None   # 0 = worst, 1 = best, within the same vintage year
    cohort_rank_dpi: float | None

    def row(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class FamilyRecord:
    family: str
    basis: str
    funds: int
    seasoned_funds: int                 # old enough to have had the chance to distribute
    mature_funds: int                   # old enough that capital should be back
    cash_in: float
    remaining: float
    pooled_dpi: float | None
    pooled_tvpi: float | None
    pooled_mature_dpi: float | None
    share_returned: float | None        # mature funds with DPI >= 1.0
    median_dpi_rank: float | None       # seasoned funds: DPI rank within the same vintage year (0 worst, 1 best)
    median_tvpi_rank: float | None
    rating: str                         # strong | adequate | weak | insufficient
    reason: str

    def row(self) -> dict:
        return dict(self.__dict__)


class GpMap:
    def __init__(self, cfg: dict):
        self._rules = [(re.compile("^(?:" + "|".join(e["patterns"]) + ")", re.I), e["family"], e.get("basis", "name"))
                       for e in cfg.get("families", [])]
        self._sponsors = {k.strip().lower(): v for k, v in (cfg.get("sponsors") or {}).items()}

    def family_of(self, fund_name: str) -> tuple[str, str]:
        for rx, fam, basis in self._rules:
            if rx.search(fund_name):
                return fam, basis
        return "", ""

    def families_of_sponsor(self, label: str) -> list[str]:
        """'Further Global / Stone Point' -> ['Stone Point'] (only parts that map to a family)."""
        out = []
        for part in [label] + [p for p in label.split("/")]:
            fam = self._sponsors.get(part.strip().lower())
            if fam and fam not in out:
                out.append(fam)
        return out


def _rank(value: float, peers: list[float]) -> float:
    """Share of peers strictly below, plus half of ties: 0..1."""
    if len(peers) <= 1:
        return 0.5
    below = sum(1 for p in peers if p < value)
    ties = sum(1 for p in peers if p == value) - 1
    return (below + 0.5 * ties) / (len(peers) - 1)


def fund_metrics(tr: TrackRecord, gp: GpMap, cohort_min_funds: int = 5) -> list[FundMetrics]:
    by_vintage: dict[int, list[FundRecord]] = {}
    for f in tr.funds:
        if f.cash_in > 0:
            by_vintage.setdefault(f.vintage, []).append(f)
    out = []
    for f in tr.funds:
        fam, basis = gp.family_of(f.fund)
        peers = by_vintage.get(f.vintage, [])
        ranked = f.cash_in > 0 and len(peers) >= cohort_min_funds
        out.append(FundMetrics(
            fund=f.fund, family=fam, basis=basis, vintage=f.vintage, age=tr.as_of.year - f.vintage, committed=f.committed,
            cash_in=f.cash_in, cash_out=f.cash_out, remaining=f.remaining, dpi=f.dpi, rvpi=f.rvpi, tvpi=f.tvpi, net_irr=f.net_irr,
            interim=bool(f.footnote), cohort_n=len(peers),
            cohort_rank_tvpi=_rank(f.tvpi, [p.tvpi for p in peers]) if ranked else None,
            cohort_rank_dpi=_rank(f.dpi, [p.dpi for p in peers]) if ranked else None))
    return out


def _pooled(num: float, den: float) -> float | None:
    return num / den if den > 0 else None


def family_records(metrics: list[FundMetrics], scoring: dict) -> list[FamilyRecord]:
    seasoned_age, mature_age = scoring["seasoned_age_years"], scoring["mature_age_years"]
    by: dict[str, list[FundMetrics]] = {}
    for m in metrics:
        if m.family:
            by.setdefault(m.family, []).append(m)
    out = []
    for fam, ms in sorted(by.items()):
        live = [m for m in ms if m.cash_in > 0]
        seasoned = [m for m in live if m.age >= seasoned_age]
        mature = [m for m in live if m.age >= mature_age]
        share = (sum(1 for m in mature if m.dpi >= 1.0) / len(mature)) if mature else None
        d_ranks = [m.cohort_rank_dpi for m in seasoned if m.cohort_rank_dpi is not None]
        t_ranks = [m.cohort_rank_tvpi for m in seasoned if m.cohort_rank_tvpi is not None]
        med_d = statistics.median(d_ranks) if d_ranks else None
        pm_dpi = _pooled(sum(m.cash_out for m in mature), sum(m.cash_in for m in mature))
        rating, reason = rate_family(len(d_ranks), len(mature), med_d, pm_dpi, scoring)
        out.append(FamilyRecord(
            family=fam, basis="inferred" if any(m.basis == "inferred" for m in ms) else "name", funds=len(ms),
            seasoned_funds=len(seasoned), mature_funds=len(mature), cash_in=sum(m.cash_in for m in live),
            remaining=sum(m.remaining for m in live),
            pooled_dpi=_pooled(sum(m.cash_out for m in live), sum(m.cash_in for m in live)),
            pooled_tvpi=_pooled(sum(m.cash_out + m.remaining for m in live), sum(m.cash_in for m in live)),
            pooled_mature_dpi=pm_dpi, share_returned=share, median_dpi_rank=med_d,
            median_tvpi_rank=statistics.median(t_ranks) if t_ranks else None, rating=rating, reason=reason))
    return out


def rate_family(n_ranked: int, n_mature: int, median_dpi_rank: float | None, pooled_mature_dpi: float | None,
                scoring: dict) -> tuple[str, str]:
    """The rating rule, in one place. Thresholds come from configs/track_record_calpers.yaml.

    It asks a lender's question, not an allocator's: does this manager hand capital back faster or slower
    than other funds of the same vintage year in this investor's book, and have its older funds returned
    what was paid in? Ranking within a vintage year keeps a young fund from being marked down for being young.
    """
    need = scoring["min_seasoned_funds"]
    if n_ranked < need or median_dpi_rank is None:
        return "insufficient", f"{n_ranked} seasoned funds with a vintage peer group (needs {need})"
    weak, strong = scoring["weak"], scoring["strong"]
    if n_mature >= 2 and pooled_mature_dpi is not None and pooled_mature_dpi < weak["pooled_mature_dpi_max"]:
        return "weak", f"funds {scoring['mature_age_years']}+ years old have returned only {pooled_mature_dpi:.2f}x of paid-in capital"
    if median_dpi_rank < weak["median_dpi_rank_max"]:
        return "weak", f"returns capital more slowly than same-vintage peers (median rank {median_dpi_rank:.2f}, 0 = slowest)"
    if median_dpi_rank >= strong["median_dpi_rank_min"] and (pooled_mature_dpi is None or pooled_mature_dpi >= strong["pooled_mature_dpi_min"]):
        tail = "" if pooled_mature_dpi is None else f"; older funds have returned {pooled_mature_dpi:.2f}x"
        return "strong", f"returns capital faster than same-vintage peers (median rank {median_dpi_rank:.2f}){tail}"
    tail = "" if pooled_mature_dpi is None else f"; older funds have returned {pooled_mature_dpi:.2f}x"
    return "adequate", f"in line with same-vintage peers on capital returned (median rank {median_dpi_rank:.2f}){tail}"


def vintage_table(metrics: list[FundMetrics]) -> list[dict]:
    """Median DPI and TVPI by vintage year across the whole table: how fast this investor's funds return capital."""
    by: dict[int, list[FundMetrics]] = {}
    for m in metrics:
        if m.cash_in > 0:
            by.setdefault(m.vintage, []).append(m)
    return [{"vintage": v, "age": ms[0].age, "funds": len(ms), "median_dpi": statistics.median(m.dpi for m in ms),
             "median_tvpi": statistics.median(m.tvpi for m in ms),
             "pooled_dpi": sum(m.cash_out for m in ms) / sum(m.cash_in for m in ms),
             "share_returned": sum(1 for m in ms if m.dpi >= 1.0) / len(ms)} for v, ms in sorted(by.items())]


def coverage(metrics: list[FundMetrics]) -> dict:
    """How much of the investor's book the fund-name -> manager map actually covers."""
    rem = sum(m.remaining for m in metrics)
    mapped = [m for m in metrics if m.family]
    return {"funds": len(metrics), "mapped_funds": len(mapped), "mapped_share_of_funds": len(mapped) / len(metrics) if metrics else 0.0,
            "remaining_value": rem, "mapped_share_of_remaining_value": (sum(m.remaining for m in mapped) / rem) if rem else 0.0,
            "inferred_funds": sum(1 for m in mapped if m.basis == "inferred")}


RATING_ORDER = {"weak": 0, "insufficient": 1, "adequate": 2, "strong": 3}


def sponsor_overlay(pool, gp: GpMap, families: list[FamilyRecord]) -> tuple[list[dict], dict]:
    """Join each collateral holding's lead sponsor to that sponsor's record in the investor's table.

    Returns one row per pool holding and a coverage summary over the eligible holdings. With joint
    sponsors every mapped family is listed; the rating carried is the weakest among those that have
    one, and "insufficient" only if none of them has a long enough record.
    """
    by = {f.family: f for f in families}
    rows = []
    for a in pool:
        fams = [by[f] for f in gp.families_of_sponsor(a.sponsor) if f in by]
        if fams:
            rated = [f for f in fams if f.rating != "insufficient"]
            worst = min(rated or fams, key=lambda f: RATING_ORDER[f.rating])
            rating, detail = worst.rating, "; ".join(f"{f.family}: {f.rating} ({f.reason})" for f in fams)
        else:
            worst, rating, detail = None, "no record", "sponsor has no funds in the investor's table"
        rows.append({"company": a.company, "key": a.key, "sponsor": a.sponsor, "eligible": a.eligible, "fair_value": a.fair_value,
                     "families": "; ".join(f.family for f in fams), "rating": rating, "detail": detail,
                     "family_funds": worst.funds if worst else 0,
                     "pooled_mature_dpi": worst.pooled_mature_dpi if worst else None,
                     "median_dpi_rank": worst.median_dpi_rank if worst else None,
                     "mapping_basis": worst.basis if worst else ""})
    elig = [r for r in rows if r["eligible"]]
    tot = sum(r["fair_value"] for r in elig)

    def share(pred) -> float:
        return (sum(r["fair_value"] for r in elig if pred(r)) / tot) if tot else 0.0

    summary = {"eligible_fv": tot,
               "rated_share": share(lambda r: r["rating"] in ("strong", "adequate", "weak")),
               "strong_share": share(lambda r: r["rating"] == "strong"), "adequate_share": share(lambda r: r["rating"] == "adequate"),
               "weak_share": share(lambda r: r["rating"] == "weak"), "insufficient_share": share(lambda r: r["rating"] == "insufficient"),
               "no_record_share": share(lambda r: r["rating"] == "no record"),
               "rated_names": sum(1 for r in elig if r["rating"] in ("strong", "adequate", "weak")), "eligible_names": len(elig)}
    return rows, summary
