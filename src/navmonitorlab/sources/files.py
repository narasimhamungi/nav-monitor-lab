"""File plugs: read (and write) the normalised CSV layout.

This is the plug a professional source arrives through in practice: an export from a data vendor or
a fund's reporting pack, saved in the layout documented in docs/data_dictionary.md. It is also where
`navmon refresh` stores what the live plugs fetched, so every analysis run reads plain files.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from ..schema import FundRecord, Holding, Snapshot, TrackRecord

HOLDING_COLS = ["vehicle", "as_of", "company", "vintage", "sponsor", "sector", "fair_value", "pct_of_fv"]
SNAPSHOT_COLS = ["vehicle", "as_of", "published", "source_url", "headline", "currency", "unit", "stated_total_fv",
                 "stated_total_pct", "nav_per_share_usd", "nav_per_share_gbp", "valuation_mix", "investment_level_pct",
                 "cash_m", "undrawn_credit_m", "realised_ytd_m", "realised_month_m", "realised_prior_year_m", "realised_text"]
TRACK_COLS = ["lp", "program", "as_of", "fund", "vintage", "committed", "cash_in", "cash_out", "total_value",
              "net_irr", "multiple", "footnote"]
PRICE_COLS = ["date", "symbol", "adj_close", "close", "currency"]
RATE_COLS = ["date", "series", "value_pct"]


def _f(x) -> float | None:
    x = (x or "").strip()
    return float(x) if x not in ("", "N/M", "n/a") else None


def _read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def mix_to_text(mix: list[tuple[date, float]]) -> str:
    return ";".join(f"{d.isoformat()}:{w:.2f}" for d, w in mix)


def mix_from_text(text: str) -> list[tuple[date, float]]:
    out = []
    for part in (text or "").split(";"):
        if part.strip():
            d, w = part.split(":")
            out.append((date.fromisoformat(d.strip()), float(w)))
    return out


def pct_text_to_fraction(text: str) -> float | None:
    """'41.3%' -> 0.413; 'N/M' or '' -> None."""
    t = (text or "").replace("%", "").strip()
    return None if t in ("", "N/M", "n/a") else float(t) / 100.0


def multiple_text(text: str) -> float | None:
    t = (text or "").lower().replace("x", "").strip()
    return None if t in ("", "n/m", "n/a") else float(t)


class FileHoldings:
    def __init__(self, holdings_csv: Path, snapshots_csv: Path, vehicle: str | None = None):
        self.holdings_csv, self.snapshots_csv, self.vehicle = Path(holdings_csv), Path(snapshots_csv), vehicle

    def load(self) -> list[Snapshot]:
        by: dict[tuple[str, str], list[Holding]] = {}
        for r in _read(self.holdings_csv):
            by.setdefault((r["vehicle"], r["as_of"]), []).append(Holding(
                company=r["company"], vintage=int(r["vintage"]) if (r.get("vintage") or "").strip() else None,
                sponsor=r["sponsor"], sector=r["sector"], fair_value=float(r["fair_value"]), pct_of_fv=_f(r.get("pct_of_fv"))))
        out = []
        for s in _read(self.snapshots_csv):
            if self.vehicle and s["vehicle"] != self.vehicle:
                continue
            out.append(Snapshot(
                vehicle=s["vehicle"], as_of=date.fromisoformat(s["as_of"]),
                published=date.fromisoformat(s["published"]) if s.get("published") else None,
                source_url=s.get("source_url", ""), currency=s.get("currency", ""), unit=s.get("unit", ""),
                holdings=by.get((s["vehicle"], s["as_of"]), []),
                stated_total_fv=_f(s.get("stated_total_fv")), stated_total_pct=_f(s.get("stated_total_pct")),
                nav_per_share_usd=_f(s.get("nav_per_share_usd")), nav_per_share_gbp=_f(s.get("nav_per_share_gbp")),
                valuation_mix=mix_from_text(s.get("valuation_mix", "")), investment_level_pct=_f(s.get("investment_level_pct")),
                cash_m=_f(s.get("cash_m")), undrawn_credit_m=_f(s.get("undrawn_credit_m")), headline=s.get("headline", ""),
                realised_ytd_m=_f(s.get("realised_ytd_m")), realised_month_m=_f(s.get("realised_month_m")),
                realised_prior_year_m=_f(s.get("realised_prior_year_m")), realised_text=s.get("realised_text") or ""))
        return sorted(out, key=lambda x: x.as_of)


def save_snapshots(snaps: list[Snapshot], holdings_csv: Path, snapshots_csv: Path) -> None:
    hrows, srows = [], []
    for s in sorted(snaps, key=lambda x: x.as_of):
        srows.append({"vehicle": s.vehicle, "as_of": s.as_of.isoformat(), "published": s.published.isoformat() if s.published else "",
                      "source_url": s.source_url, "headline": s.headline, "currency": s.currency, "unit": s.unit,
                      "stated_total_fv": "" if s.stated_total_fv is None else s.stated_total_fv,
                      "stated_total_pct": "" if s.stated_total_pct is None else round(s.stated_total_pct, 4),
                      "nav_per_share_usd": "" if s.nav_per_share_usd is None else f"{s.nav_per_share_usd:.2f}",
                      "nav_per_share_gbp": "" if s.nav_per_share_gbp is None else f"{s.nav_per_share_gbp:.2f}",
                      "valuation_mix": mix_to_text(s.valuation_mix),
                      "investment_level_pct": "" if s.investment_level_pct is None else f"{s.investment_level_pct:g}",
                      "cash_m": "" if s.cash_m is None else f"{s.cash_m:g}",
                      "undrawn_credit_m": "" if s.undrawn_credit_m is None else f"{s.undrawn_credit_m:g}",
                      "realised_ytd_m": "" if s.realised_ytd_m is None else f"{s.realised_ytd_m:g}",
                      "realised_month_m": "" if s.realised_month_m is None else f"{s.realised_month_m:g}",
                      "realised_prior_year_m": "" if s.realised_prior_year_m is None else f"{s.realised_prior_year_m:g}",
                      "realised_text": s.realised_text})
        for h in s.holdings:
            hrows.append({"vehicle": s.vehicle, "as_of": s.as_of.isoformat(), "company": h.company,
                          "vintage": "" if h.vintage is None else h.vintage, "sponsor": h.sponsor, "sector": h.sector,
                          "fair_value": h.fair_value, "pct_of_fv": "" if h.pct_of_fv is None else round(h.pct_of_fv, 4)})
    write_csv(holdings_csv, HOLDING_COLS, hrows)
    write_csv(snapshots_csv, SNAPSHOT_COLS, srows)


class FileTrackRecord:
    def __init__(self, path: Path, source_url: str = ""):
        self.path, self.source_url = Path(path), source_url

    def load(self) -> TrackRecord:
        rows = _read(self.path)
        funds = [FundRecord(fund=r["fund"], vintage=int(r["vintage"]), committed=float(r["committed"]), cash_in=float(r["cash_in"]),
                            cash_out=float(r["cash_out"]), total_value=float(r["total_value"]),
                            net_irr=pct_text_to_fraction(r["net_irr"]), multiple=multiple_text(r["multiple"]),
                            footnote=(r.get("footnote") or "").strip()) for r in rows]
        first = rows[0]
        return TrackRecord(lp=first["lp"], program=first["program"], as_of=date.fromisoformat(first["as_of"]),
                           source_url=self.source_url, funds=funds)


def save_track_record(tr: TrackRecord, path: Path) -> None:
    rows = [{"lp": tr.lp, "program": tr.program, "as_of": tr.as_of.isoformat(), "fund": f.fund, "vintage": f.vintage,
             "committed": f"{f.committed:.0f}", "cash_in": f"{f.cash_in:.0f}", "cash_out": f"{f.cash_out:.0f}",
             "total_value": f"{f.total_value:.0f}", "net_irr": "N/M" if f.net_irr is None else f"{f.net_irr * 100:.1f}%",
             "multiple": "N/M" if f.multiple is None else f"{f.multiple:.1f}x", "footnote": f.footnote} for f in tr.funds]
    write_csv(path, TRACK_COLS, rows)


class FilePrices:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._rows: dict[str, list[tuple[date, float, float]]] = {}
        self.currency: dict[str, str] = {}
        for r in _read(self.path):
            self._rows.setdefault(r["symbol"], []).append((date.fromisoformat(r["date"]), float(r["adj_close"]), float(r["close"])))
            if r.get("currency"):
                self.currency[r["symbol"]] = r["currency"]

    def symbols(self) -> list[str]:
        return sorted(self._rows)

    def history(self, symbol: str, start: date, end: date) -> list[tuple[date, float, float]]:
        return sorted(r for r in self._rows.get(symbol, []) if start <= r[0] <= end)


class FileRates:
    def __init__(self, path: Path):
        self._rows: dict[str, list[tuple[date, float]]] = {}
        for r in _read(Path(path)):
            self._rows.setdefault(r["series"], []).append((date.fromisoformat(r["date"]), float(r["value_pct"])))

    def series(self) -> list[str]:
        return sorted(self._rows)

    def history(self, series: str, start: date, end: date) -> list[tuple[date, float]]:
        return sorted(r for r in self._rows.get(series, []) if start <= r[0] <= end)
