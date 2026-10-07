"""Data-quality checks. Each returns findings; nothing here changes a number.

Holdings checks tie every published table back to the publisher's own total row. Track-record checks
recompute what can be recomputed and flag what cannot be meaningful.
"""
from __future__ import annotations

import re
from collections import Counter

from .names import canonical_company
from .schema import Finding, Snapshot, TrackRecord


def check_snapshot(s: Snapshot, *, fv_tol: float = 0.55, pct_tol: float = 0.006, stale_days: int = 100) -> list[Finding]:
    """One published holdings table against its own stated totals."""
    scope = f"{s.vehicle} {s.as_of.isoformat()}"
    out: list[Finding] = []
    if not s.holdings:
        return [Finding("error", "Q00", scope, "Snapshot has no holdings")]
    total = s.total_fv
    if s.stated_total_fv is None:
        out.append(Finding("warn", "Q01", scope, "No total row published; holdings cannot be tied out"))
    elif abs(total - s.stated_total_fv) > fv_tol:
        out.append(Finding("warn", "Q01", scope, "Holdings do not sum to the publisher's own total row",
                           observed=f"rows {total:,.1f} vs stated {s.stated_total_fv:,.1f} (difference {total - s.stated_total_fv:+,.1f})",
                           threshold=f"within {fv_tol}"))
    pcts = [h.pct_of_fv for h in s.holdings if h.pct_of_fv is not None]
    if s.stated_total_pct is not None and pcts and abs(sum(pcts) - s.stated_total_pct) > pct_tol:
        out.append(Finding("warn", "Q02", scope, "Holdings' percentages do not sum to the stated share of the portfolio",
                           observed=f"rows {sum(pcts):.1%} vs stated {s.stated_total_pct:.1%}", threshold=f"within {pct_tol:.1%}"))
    implied = s.implied_portfolio_fv
    if implied:
        for h in s.holdings:
            if h.pct_of_fv is None or h.pct_of_fv <= 0:
                continue
            lo, hi = (h.fair_value - 0.05) / (h.pct_of_fv + 0.0005), (h.fair_value + 0.05) / max(h.pct_of_fv - 0.0005, 1e-9)
            if not (lo * 0.985 <= implied <= hi * 1.015):
                out.append(Finding("warn", "Q03", scope, "A row's fair value and percentage imply a different portfolio size from the total row",
                                   observed=f"{h.company}: {h.fair_value} at {h.pct_of_fv:.1%} implies {h.fair_value / h.pct_of_fv:,.0f}; total row implies {implied:,.0f}"))
    dup = [k for k, n in Counter(h.company for h in s.holdings).items() if n > 1]
    if dup:
        out.append(Finding("info", "Q04", scope, "The same name appears more than once in the table", observed="; ".join(dup)))
    if not s.valuation_mix:
        out.append(Finding("warn", "Q05", scope, "No valuation-date breakdown published; mark age unknown"))
    else:
        w = sum(x for _, x in s.valuation_mix)
        if abs(w - 1.0) > 0.021:
            out.append(Finding("warn", "Q06", scope, "Valuation-date breakdown does not sum to 100%", observed=f"{w:.0%}"))
    if s.nav_per_share_usd is None:
        out.append(Finding("info", "Q07", scope, "NAV per share not found in the announcement"))
    return out


def stale_share(s: Snapshot, stale_days: int) -> float:
    """Share of the portfolio valued more than `stale_days` before the report date."""
    return sum(w for d, w in s.valuation_mix if (s.as_of - d).days > stale_days)


def weighted_mark_age(s: Snapshot) -> float:
    """Average age of the marks at the report date, in days, weighted by share of portfolio."""
    w = sum(x for _, x in s.valuation_mix)
    return sum((s.as_of - d).days * x for d, x in s.valuation_mix) / w if w else float("nan")


def check_history(snaps: list[Snapshot], company_aliases: dict[str, str], sector_aliases: dict[str, str] | None = None) -> list[Finding]:
    """Things only visible across months: a company whose vintage, sector or sponsor label changes.
    Sector renames already covered by the vehicle config's sector_aliases are not reported."""
    sector_aliases = sector_aliases or {}
    out: list[Finding] = []
    seen: dict[str, dict[str, dict]] = {}
    for s in snaps:
        for h in s.holdings:
            if h.is_undisclosed:
                continue
            k = canonical_company(h.company, company_aliases)
            rec = seen.setdefault(k, {"vintage": {}, "sector": {}, "sponsor": {}})
            for fld, val in (("vintage", h.vintage), ("sector", sector_aliases.get(h.sector, h.sector)), ("sponsor", h.sponsor)):
                rec[fld].setdefault(val, s.as_of)
    labels = {"vintage": ("Q10", "The publisher has shown different vintage years for the same company"),
              "sector": ("Q11", "The publisher has shown different sectors for the same company"),
              "sponsor": ("Q12", "The publisher has shown different lead-sponsor labels for the same company")}
    for k, rec in sorted(seen.items()):
        for fld, (code, msg) in labels.items():
            if len(rec[fld]) > 1:
                hist = "; ".join(f"{v} (first seen {d.isoformat()})" for v, d in sorted(rec[fld].items(), key=lambda x: x[1]))
                out.append(Finding("info", code, k, msg, observed=hist))
    return out


_NAME_FOOTNOTE = re.compile(r"(L\.P\.|LP|SCSp)\s?\d$")


def check_track_record(tr: TrackRecord, *, multiple_tolerance: float = 0.06, extreme_irr_abs: float = 1.0,
                       called_over_committed_warn: float = 3.0) -> list[Finding]:
    out: list[Finding] = []
    scope = f"{tr.lp} {tr.as_of.isoformat()}"
    n_nm = sum(1 for f in tr.funds if f.net_irr is None)
    out.append(Finding("info", "T09", scope, "The table lists active partnerships only; exited funds are absent, so results are "
                       "biased towards managers the investor still holds", observed=f"{len(tr.funds)} funds, {n_nm} with IRR 'N/M'"))
    marked = [f for f in tr.funds if f.footnote]
    if marked:
        oldest_marked = min(f.vintage for f in marked)
        out.append(Finding("info", "T02", scope, "Rows carrying the 'not meaningful' footnote marker; their IRR and multiple are "
                           "interim and should not be ranked", observed=f"{len(marked)} rows, vintages {oldest_marked}-{max(f.vintage for f in marked)}"))
        shown = [f for f in marked if f.net_irr is not None]
        if shown:
            out.append(Finding("info", "T03", scope, "The publisher marks these rows 'not meaningful' yet still prints an IRR for them",
                               observed=f"{len(shown)} of {len(marked)} marked rows"))
    for f in tr.funds:
        if f.cash_in <= 0:
            out.append(Finding("warn", "T06", f.fund, "No cash paid in; multiples are undefined", observed=f"cash in {f.cash_in:,.0f}, value {f.total_value:,.0f}"))
            continue
        if f.multiple is not None and abs(f.tvpi - f.multiple) > multiple_tolerance:
            out.append(Finding("warn", "T01", f.fund, "Published multiple does not match value divided by cash in",
                               observed=f"published {f.multiple:.1f}x, recomputed {f.tvpi:.2f}x", threshold=f"within {multiple_tolerance}"))
        if f.total_value < f.cash_out - 0.5:
            out.append(Finding("error", "T05", f.fund, "Cash out plus remaining value is below cash out",
                               observed=f"total {f.total_value:,.0f} < cash out {f.cash_out:,.0f}"))
        if f.net_irr is not None and abs(f.net_irr) >= extreme_irr_abs:
            out.append(Finding("warn", "T04", f.fund, "Extreme net IRR; typical of a very young fund and not a track record",
                               observed=f"{f.net_irr:.1%}, vintage {f.vintage}", threshold=f"|IRR| >= {extreme_irr_abs:.0%}"))
        if f.committed > 0 and f.cash_in / f.committed >= called_over_committed_warn:
            out.append(Finding("warn", "T07", f.fund, "Cash paid in is a multiple of the stated commitment; the commitment figure is "
                               "not comparable (recycling, or a partial figure)",
                               observed=f"cash in {f.cash_in:,.0f} vs committed {f.committed:,.0f} ({f.cash_in / f.committed:.1f}x)",
                               threshold=f">= {called_over_committed_warn:.1f}x"))
        if "?" in f.fund:
            out.append(Finding("info", "T08", f.fund, "Fund name contains a character the publisher's page failed to encode"))
        if _NAME_FOOTNOTE.search(f.fund):
            out.append(Finding("info", "T11", f.fund, "Fund name ends in a digit that looks like a footnote mark typed into the name"))
    return out
