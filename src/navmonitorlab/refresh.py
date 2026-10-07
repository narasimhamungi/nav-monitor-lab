"""Fetch from the live plugs and store the result as normalised files.

`navmon refresh` is the only command that touches the network. It writes the same CSV layout the
analysis reads, plus a manifest recording every URL fetched, when, and the sha256 of what came back.
A source that fails does not stop the others, and never overwrites good data with nothing.
"""
from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

from .net import FetchError, Fetcher, sha256_file
from .rollforward import proxy_for
from .sources import holdings_source, price_source, rate_source, track_source
from .sources.files import (PRICE_COLS, RATE_COLS, FileHoldings, FileTrackRecord, save_snapshots, save_track_record, write_csv)

STEPS = ("holdings", "track", "prices", "rates")


def needed_symbols(cfg: dict) -> list[str]:
    m, v = cfg["market"], cfg["vehicle"]
    syms = set(m["sector_proxy"].values()) | {m["default_proxy"]}
    if v.get("listed_share", {}).get("symbol"):
        syms.add(v["listed_share"]["symbol"])
    return sorted(syms)


def _seed(live: Path, sample: Path | None, names: list[str]) -> bool:
    """A failed source with nothing on disk yet falls back to the shipped sample, and says so."""
    if sample is None:
        return False
    seeded = False
    for n in names:
        if not (live / n).exists() and (sample / n).exists():
            live.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sample / n, live / n)
            seeded = True
    return seeded


def refresh(cfg: dict, live_dir: Path, *, cache_dir: Path | None = None, sample_dir: Path | None = None,
            fetcher: Fetcher | None = None, only: tuple[str, ...] = STEPS, today: date | None = None) -> dict:
    live_dir = Path(live_dir)
    live_dir.mkdir(parents=True, exist_ok=True)
    f = fetcher or Fetcher(cache_dir=cache_dir)
    today = today or date.today()
    veh, market, track = cfg["vehicle"], cfg["market"], cfg["track"]
    report: dict = {"steps": {}, "seeded_from_sample": []}

    def fail(step: str, err: Exception, files: list[str]) -> None:
        seeded = _seed(live_dir, sample_dir, files)
        report["steps"][step] = {"status": "FAILED", "error": str(err), "kept_existing": not seeded and all((live_dir / n).exists() for n in files),
                                 "seeded_from_sample": seeded}
        if seeded:
            report["seeded_from_sample"] += files

    if "holdings" in only:
        hfile, sfile = veh["files"]["holdings_csv"], veh["files"]["snapshots_csv"]
        try:
            before = {s.as_of for s in FileHoldings(live_dir / hfile, live_dir / sfile).load()} if (live_dir / sfile).exists() else set()
            src = holdings_source({**veh["live"], "vehicle": veh["vehicle"], "currency": veh.get("currency", "USD"), "unit": veh.get("unit", "millions")}, fetcher=f)
            snaps = src.load()
            if not snaps:
                raise FetchError("no announcement produced a holdings table")
            save_snapshots(snaps, live_dir / hfile, live_dir / sfile)
            new = sorted(s.as_of.isoformat() for s in snaps if s.as_of not in before)
            report["steps"]["holdings"] = {"status": "OK", "snapshots": len(snaps), "latest": snaps[-1].as_of.isoformat(),
                                           "new_since_last_refresh": new if before else "first refresh",
                                           "reports_stating_cash_received": sum(1 for s in snaps if s.realised_ytd_m is not None or s.realised_month_m is not None),
                                           "parser_findings": [x.row() for x in getattr(src, "findings", [])]}
        except (FetchError, ValueError, KeyError) as e:
            fail("holdings", e, [hfile, sfile])

    if "track" in only:
        tfile = track["files"]["csv"]
        try:
            prev = FileTrackRecord(live_dir / tfile).load() if (live_dir / tfile).exists() else None
            src = track_source(track["live"], fetcher=f)
            tr = src.load()
            if not tr.funds:
                raise FetchError("the track-record page produced no rows")
            if prev is not None and prev.as_of != tr.as_of:      # keep the superseded snapshot so changes can be diffed later
                hist = live_dir / "history"
                hist.mkdir(exist_ok=True)
                shutil.copyfile(live_dir / tfile, hist / f"{Path(tfile).stem}_{prev.as_of.isoformat()}.csv")
            save_track_record(tr, live_dir / tfile)
            report["steps"]["track"] = {"status": "OK", "funds": len(tr.funds), "as_of": tr.as_of.isoformat(),
                                        "previous_as_of": prev.as_of.isoformat() if prev else None,
                                        "parser_findings": [x.row() for x in getattr(src, "findings", [])]}
        except (FetchError, ValueError, KeyError) as e:
            fail("track", e, [tfile])

    if "prices" in only:
        pfile = market["prices"]["files"]["csv"]
        try:
            src = price_source(market["prices"]["live"], fetcher=f)
            start = date.fromisoformat(str(market["prices"]["history_start"]))
            rows, got, errors = [], [], []
            for sym in needed_symbols(cfg):
                try:
                    hist = src.history(sym, start, today)
                except FetchError as e:
                    errors.append(f"{sym}: {e}"); continue
                if not hist:
                    errors.append(f"{sym}: empty history"); continue
                got.append(sym)
                rows += [{"date": d.isoformat(), "symbol": sym, "adj_close": f"{a:.4f}", "close": f"{c:.4f}",
                          "currency": getattr(src, "currency", {}).get(sym, "")} for d, a, c in hist]
            if not rows:
                raise FetchError("; ".join(errors) or "no prices returned")
            write_csv(live_dir / pfile, PRICE_COLS, sorted(rows, key=lambda r: (r["symbol"], r["date"])))
            report["steps"]["prices"] = {"status": "OK" if not errors else "PARTIAL", "symbols": got, "errors": errors,
                                         "latest": max(r["date"] for r in rows), "plug": market["prices"]["live"]["plug"]}
        except (FetchError, ValueError, KeyError) as e:
            fail("prices", e, [pfile])

    if "rates" in only:
        rfile = market["rates"]["files"]["csv"]
        try:
            src = rate_source(market["rates"]["live"], fetcher=f)
            start = date.fromisoformat(str(market["prices"]["history_start"]))
            rows = []
            for sid in [market["rates"]["base_rate_series"]] + list(market["rates"].get("also_fetch") or []):
                rows += [{"date": d.isoformat(), "series": sid, "value_pct": f"{v:g}"} for d, v in src.history(sid, start, today + timedelta(days=1))]
            if not rows:
                raise FetchError("no rate observations returned")
            write_csv(live_dir / rfile, RATE_COLS, rows)
            report["steps"]["rates"] = {"status": "OK", "observations": len(rows), "latest": max(r["date"] for r in rows)}
        except (FetchError, ValueError, KeyError) as e:
            fail("rates", e, [rfile])

    manifest = {"refreshed_on": today.isoformat(), "steps": report["steps"], "seeded_from_sample": report["seeded_from_sample"],
                "fetches": f.log, "files_sha256": {p.name: sha256_file(p) for p in sorted(live_dir.glob("*.csv"))}}
    (live_dir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    report["manifest"] = str(live_dir / "manifest.json")
    return report


def check_sources(cfg: dict, fetcher: Fetcher | None = None, today: date | None = None) -> list[dict]:
    """A small live call to each plug, checked for shape. Run this first on a new machine."""
    from .sources.calpers import CalpersTrackRecord
    from .realisations import compile_patterns
    from .sources.fca_nsm import FcaNsmHoldings, parse_announcement
    from .sources.market import FredRates, TiingoPrices, YahooChartPrices
    f = fetcher or Fetcher()
    today = today or date.today()
    veh, market = cfg["vehicle"], cfg["market"]
    out = []

    def attempt(name: str, fn) -> None:
        try:
            out.append({"source": name, "status": "PASS", "detail": fn()})
        except Exception as e:                       # a smoke test reports every failure, whatever its type
            out.append({"source": name, "status": "FAIL", "detail": f"{type(e).__name__}: {e}"})

    def nsm() -> str:
        src = FcaNsmHoldings(f, vehicle=veh["vehicle"], lei=veh["live"]["lei"], headline_include=veh["live"]["headline_include"],
                             headline_exclude=veh["live"].get("headline_exclude", ""), columns=veh["live"].get("columns"))
        found = src.discover()
        if not found:
            raise FetchError("search returned no matching announcements")
        snap, fs = parse_announcement(f.text(found[0]["url"]), vehicle=veh["vehicle"], source_url=found[0]["url"],
                                      published=found[0]["published"], columns=veh["live"].get("columns"),
                                      realisation_patterns=compile_patterns(veh["live"].get("realisations")) if veh["live"].get("realisations") else None)
        if snap is None:
            raise FetchError("latest announcement did not parse: " + "; ".join(x.message for x in fs))
        cash = [f"{label} {v:g}" for label, v in (("year to date", snap.realised_ytd_m), ("in the month", snap.realised_month_m)) if v is not None]
        return (f"{len(found)} announcements; latest report {snap.as_of} with {len(snap.holdings)} holdings, "
                f"rows sum {snap.total_fv:,.1f} vs stated {snap.stated_total_fv}; cash received: {', '.join(cash) or 'not stated in this report'}")

    def calpers() -> str:
        tr = CalpersTrackRecord(f, **({"url": cfg["track"]["live"]["url"]} if cfg["track"]["live"].get("url") else {})).load()
        return f"{len(tr.funds)} funds as of {tr.as_of}"

    def yahoo() -> str:
        rows = YahooChartPrices(f).history(market["default_proxy"], today - timedelta(days=10), today)
        return f"{market['default_proxy']}: {len(rows)} daily rows, latest {rows[-1][0]} close {rows[-1][2]:.2f}"

    def tiingo() -> str:
        rows = TiingoPrices(f).history(market["default_proxy"], today - timedelta(days=10), today)
        return f"{market['default_proxy']}: {len(rows)} daily rows, latest {rows[-1][0]} close {rows[-1][2]:.2f}"

    def fred() -> str:
        sid = market["rates"]["base_rate_series"]
        rows = FredRates(f).history(sid, today - timedelta(days=30), today)
        return f"{sid}: {len(rows)} observations, latest {rows[-1][0]} at {rows[-1][1]}%"

    attempt("holdings: fca_nsm", nsm)
    attempt("track record: calpers_html", calpers)
    attempt("prices: yahoo_chart", yahoo)
    attempt("prices: tiingo (needs TIINGO_API_KEY)", tiingo)
    attempt("rates: fred_csv", fred)
    return out


def verify_live(cfg: dict, live_dir: Path, sample_dir: Path, price_tolerance: float = 0.005) -> dict:
    """Cross-check what the live plugs parsed against the shipped sample, wherever the two overlap.

    The sample was captured through a browser on 2026-10-07; the live plugs are separate code. Agreement
    on the overlap is evidence that both read the pages correctly. Adjusted closes are not compared
    because data vendors restate them after every dividend; raw closes are.
    """
    from .sources.files import FilePrices
    veh, track, market = cfg["vehicle"], cfg["track"], cfg["market"]
    live_dir, sample_dir = Path(live_dir), Path(sample_dir)
    res: dict = {}

    def load_h(d: Path):
        return {s.as_of: s for s in FileHoldings(d / veh["files"]["holdings_csv"], d / veh["files"]["snapshots_csv"]).load()}

    a, b = load_h(live_dir), load_h(sample_dir)
    mism = []
    for d in sorted(set(a) & set(b)):
        la = {(h.company, h.fair_value, h.pct_of_fv, h.sponsor, h.sector, h.vintage) for h in a[d].holdings}
        lb = {(h.company, h.fair_value, h.pct_of_fv, h.sponsor, h.sector, h.vintage) for h in b[d].holdings}
        if la != lb:
            mism.append({"as_of": d.isoformat(), "only_in_live": sorted(map(str, la - lb))[:5], "only_in_sample": sorted(map(str, lb - la))[:5]})
        for fld in ("stated_total_fv", "stated_total_pct", "nav_per_share_usd", "nav_per_share_gbp", "valuation_mix",
                    "realised_ytd_m", "realised_month_m", "realised_prior_year_m"):
            if getattr(a[d], fld) != getattr(b[d], fld):
                mism.append({"as_of": d.isoformat(), "field": fld, "live": str(getattr(a[d], fld)), "sample": str(getattr(b[d], fld))})
    res["holdings"] = {"overlapping_snapshots": len(set(a) & set(b)), "only_in_live": sorted(d.isoformat() for d in set(a) - set(b)),
                       "only_in_sample": sorted(d.isoformat() for d in set(b) - set(a)), "mismatches": mism}

    ta, tb = FileTrackRecord(live_dir / track["files"]["csv"]).load(), FileTrackRecord(sample_dir / track["files"]["csv"]).load()
    if ta.as_of == tb.as_of:
        fa, fb = {f.fund: f for f in ta.funds}, {f.fund: f for f in tb.funds}
        diff = [k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)]
        res["track_record"] = {"same_as_of": True, "funds_live": len(fa), "funds_sample": len(fb), "mismatched_funds": sorted(diff)[:10],
                               "mismatches": len(diff)}
    else:
        res["track_record"] = {"same_as_of": False, "live_as_of": ta.as_of.isoformat(), "sample_as_of": tb.as_of.isoformat(),
                               "note": "the publisher has updated the table since the sample was captured; nothing to compare"}

    pa, pb = FilePrices(live_dir / market["prices"]["files"]["csv"]), FilePrices(sample_dir / market["prices"]["files"]["csv"])
    bad, n = [], 0
    far0, far1 = date(1990, 1, 1), date(2100, 1, 1)
    for sym in sorted(set(pa.symbols()) & set(pb.symbols())):
        la = {d: c for d, _, c in pa.history(sym, far0, far1)}
        for d, _, c in pb.history(sym, far0, far1):
            if d in la:
                n += 1
                if abs(la[d] / c - 1.0) > price_tolerance:
                    bad.append({"symbol": sym, "date": d.isoformat(), "live_close": la[d], "sample_close": c})
    res["prices"] = {"compared_closes": n, "mismatches": len(bad), "examples": bad[:10]}
    res["agree"] = not mism and res["track_record"].get("mismatches", 0) == 0 and not bad
    return res
