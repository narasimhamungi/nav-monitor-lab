"""The data shapes every source plug must return. Analysis code only ever sees these.

Field names follow a fund's schedule of investments (company, vintage, sponsor, sector, fair value) so that a
real fund report can be dropped in through the file plug. See docs/data_dictionary.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

_TICKER = re.compile(r"\(\s*(?:NYSE|NASDAQ|LSE|OB|AMS|XETRA)\s*[:.]\s*[A-Z0-9.]+\s*\)", re.I)
_UNDISCLOSED = re.compile(r"\*|undisclosed|not disclosed|company\s*#?\d+\s*$", re.I)


@dataclass(frozen=True)
class Holding:
    company: str            # as published
    vintage: int | None
    sponsor: str
    sector: str
    fair_value: float       # in the snapshot's unit and currency
    pct_of_fv: float | None  # share of the vehicle's total portfolio fair value, as published (0-1)

    @property
    def is_listed(self) -> bool:
        """The publisher marks quoted holdings with an exchange ticker in brackets."""
        return bool(_TICKER.search(self.company))

    @property
    def is_undisclosed(self) -> bool:
        return bool(_UNDISCLOSED.search(self.company)) or self.sponsor.strip().lower() in ("not disclosed", "multiple gps")


@dataclass
class Snapshot:
    vehicle: str
    as_of: date
    published: date | None
    source_url: str
    currency: str
    unit: str
    holdings: list[Holding]
    stated_total_fv: float | None = None      # the publisher's own total row
    stated_total_pct: float | None = None     # the holdings' stated share of the whole portfolio (0-1)
    nav_per_share_usd: float | None = None
    nav_per_share_gbp: float | None = None
    valuation_mix: list[tuple[date, float]] = field(default_factory=list)  # (valuation date, share of portfolio)
    investment_level_pct: float | None = None
    cash_m: float | None = None
    undrawn_credit_m: float | None = None
    headline: str = ""
    # cash received from realisations, as stated in the report (docs/model_spec.md, section E); None = not stated
    realised_ytd_m: float | None = None          # from 1 January of the report year to the report date
    realised_month_m: float | None = None        # in the report month
    realised_prior_year_m: float | None = None   # in the whole previous calendar year
    realised_text: str = ""                      # the sentences those figures were read from

    @property
    def listed_fv(self) -> float:
        return sum(h.fair_value for h in self.holdings if h.is_listed)

    @property
    def total_fv(self) -> float:
        return sum(h.fair_value for h in self.holdings)

    @property
    def implied_portfolio_fv(self) -> float | None:
        """Whole-portfolio fair value implied by the publisher's total row and its stated share."""
        if self.stated_total_fv and self.stated_total_pct:
            return self.stated_total_fv / self.stated_total_pct
        return None

    def private_mix(self) -> list[tuple[date, float]]:
        """Valuation dates for the private holdings, weights renormalised to 1.

        Assumption (docs/model_spec.md, R-2): the bucket dated at the report date is the quoted holdings;
        every earlier bucket is private marks. With no earlier bucket, everything is treated as dated as_of.
        """
        older = [(d, w) for d, w in self.valuation_mix if d < self.as_of and w > 0]
        tot = sum(w for _, w in older)
        return [(d, w / tot) for d, w in older] if tot > 0 else [(self.as_of, 1.0)]


@dataclass(frozen=True)
class FundRecord:
    """One fund line from an investor's (LP's) published performance table."""
    fund: str               # as published
    vintage: int
    committed: float
    cash_in: float
    cash_out: float
    total_value: float      # cash out plus remaining value
    net_irr: float | None   # as a fraction; None when the publisher shows "N/M"
    multiple: float | None  # as published; None when "N/M"
    footnote: str = ""

    @property
    def remaining(self) -> float:
        return self.total_value - self.cash_out

    @property
    def dpi(self) -> float | None:
        return self.cash_out / self.cash_in if self.cash_in > 0 else None

    @property
    def rvpi(self) -> float | None:
        return self.remaining / self.cash_in if self.cash_in > 0 else None

    @property
    def tvpi(self) -> float | None:
        return self.total_value / self.cash_in if self.cash_in > 0 else None


@dataclass
class TrackRecord:
    lp: str
    program: str
    as_of: date
    source_url: str
    funds: list[FundRecord]


@dataclass(frozen=True)
class Finding:
    """A data-quality or policy observation. Findings are reported, never silently fixed."""
    severity: str   # "error" | "warn" | "info"
    code: str
    scope: str      # which dataset / snapshot / row
    message: str
    observed: str = ""
    threshold: str = ""

    def row(self) -> dict:
        return {"severity": self.severity, "code": self.code, "scope": self.scope, "message": self.message,
                "observed": self.observed, "threshold": self.threshold}


SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}
