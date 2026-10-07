"""Cash received from realisations: read it from the reports, reconcile it, and turn it into an exit pace.

Three steps, kept apart so each can be checked on its own:

1. `read_statements` reads one report's text. It accepts only sentences that state CASH RECEIVED. Figures
   the publisher calls announced, pending, expected or pro forma are not cash and are never read. The
   accepted wordings are regular expressions in the vehicle config, so another vehicle needs config, not code.
2. `cash_series` puts the reports in order, derives a running total where a report states only the month's
   cash, and reconciles the publisher's own numbers against each other. Findings are reported, never fixed.
3. `calibrate` divides cash received over trailing windows by the average portfolio fair value over the same
   window and annualises it. The base case is chosen by a rule named in configs/facility.yaml.

Definitions are in docs/model_spec.md, section E.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime

from .schema import Finding, Snapshot

MONTHS = [calendar.month_name[i] for i in range(1, 13)]
_PLACEHOLDERS = {
    "{amt}": r"\$(?P<amt>\d[\d,]*(?:\.\d+)?) ?mil+ion\d?",          # "$56 million"; the publisher also writes "milllion"
    "{year}": r"(?P<year>20\d\d)\d?",                                # a footnote mark can follow the year ("20243")
    "{date}": r"(?P<through>\d{1,2} [A-Z][a-z]+ 20\d\d)",
    "{month}": r"(?P<month>" + "|".join(MONTHS) + r")(?: 20\d\d)?",
    "{ytd}": r"year[- ]to[- ]date",
}


def compile_patterns(cfg: dict | None) -> dict[str, list[dict]]:
    """Turn the config's wordings into compiled expressions. Unknown kinds are an error, not ignored."""
    out: dict[str, list[dict]] = {"year_to_date": [], "month": [], "year": []}
    for kind, items in (cfg or {}).items():
        if kind not in out:
            raise ValueError(f"realisations: unknown statement kind '{kind}'; use year_to_date, month or year")
        for item in items or []:
            spec = {"re": item} if isinstance(item, str) else dict(item)
            text = spec["re"]
            for k, v in _PLACEHOLDERS.items():
                text = text.replace(k, v)
            spec["rx"] = re.compile(text, re.I)
            out[kind].append(spec)
    return out


def _amount(m: re.Match) -> float:
    return float(m.group("amt").replace(",", ""))


def _month_end(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def read_statements(text: str, as_of: date, patterns: dict[str, list[dict]], scope: str = "") -> tuple[dict, list[Finding]]:
    """Read one report. Returns the stated figures and any findings.

    - `realised_ytd_m`: cash received from 1 January of the report year to the report date.
    - `realised_month_m`: cash received in the report month.
    - `realised_prior_year_m`: cash received in the whole previous calendar year (stated in results announcements).
    - `realised_text`: the phrases the figures were read from.
    A figure is used only if it is dated to this report: a "through <date>" must be the report date, a named
    month must be the report month, a named year must be the report year (or the year before, for the
    prior-year total). Two different figures for the same thing are a conflict and neither is used.
    """
    scope = scope or as_of.isoformat()
    found: dict[str, list[tuple[float, str]]] = {"ytd": [], "month": [], "prior": []}
    findings: list[Finding] = []
    for line in text.split("\n"):
        if "$" not in line:
            continue
        for kind in ("year_to_date", "year", "month"):
            for spec in patterns.get(kind, []):
                for m in spec["rx"].finditer(line):
                    g = m.groupdict()
                    amt, target = _amount(m), "ytd" if kind != "month" else "month"
                    if g.get("through"):
                        try:
                            through = datetime.strptime(g["through"], "%d %B %Y").date()
                        except ValueError:
                            continue
                        if through != as_of:
                            findings.append(Finding("info", "R05", scope, "Cash-received figure is dated to a different day than the report; not used",
                                                    observed=m.group(0)))
                            continue
                    if g.get("year"):
                        yr = int(g["year"])
                        if yr == as_of.year - 1 and kind == "year":
                            target = "prior"
                        elif yr != as_of.year:
                            continue
                    if spec.get("expect_month") and as_of.month != int(spec["expect_month"]):
                        findings.append(Finding("info", "R05", scope, "Cash-received figure covers a different period than the report; not used",
                                                observed=m.group(0)))
                        continue
                    if g.get("month") and g["month"].capitalize() != MONTHS[as_of.month - 1]:
                        continue
                    found[target].append((amt, " ".join(m.group(0).split())))
    out: dict = {"realised_ytd_m": None, "realised_month_m": None, "realised_prior_year_m": None, "realised_text": ""}
    used: list[str] = []
    for key, fld, label in (("ytd", "realised_ytd_m", "year-to-date cash received"), ("month", "realised_month_m", "cash received in the month"),
                            ("prior", "realised_prior_year_m", "previous year's cash received")):
        values = sorted({a for a, _ in found[key]})
        if len(values) == 1:
            out[fld] = values[0]
            for _, line in found[key]:
                if line not in used:
                    used.append(line)
        elif len(values) > 1:
            findings.append(Finding("warn", "R06", scope, f"The report gives more than one figure for {label}; none is used",
                                    observed=", ".join(f"{v:g}" for v in values)))
    out["realised_text"] = " | ".join(used)
    return out, findings


def _prev_month_end(d: date) -> date:
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    return date(y, m, calendar.monthrange(y, m)[1])


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def cash_series(snaps: list[Snapshot], tolerance: float = 1.0) -> tuple[list[dict], list[Finding]]:
    """One row per report: cash received this year to date, how it is known, and the running total since
    the start of the first year in the data.

    basis: "stated" (the report gives the year-to-date figure), "derived" (previous running total plus the
    month's stated cash), or "" (the report states neither; the gap closes at the next stated figure).
    """
    snaps = sorted(snaps, key=lambda s: s.as_of)
    rows: list[dict] = []
    findings: list[Finding] = []
    by_date: dict[date, dict] = {}
    for s in snaps:
        ytd, basis = s.realised_ytd_m, "stated" if s.realised_ytd_m is not None else ""
        prev = by_date.get(_prev_month_end(s.as_of))
        prev_ytd = 0.0 if s.as_of.month == 1 else (prev["ytd"] if prev else None)
        if s.realised_month_m is not None and prev_ytd is not None:
            if ytd is None:
                ytd, basis = prev_ytd + s.realised_month_m, "derived"
            elif abs(prev_ytd + s.realised_month_m - ytd) > tolerance:
                findings.append(Finding("warn", "R02", f"{s.vehicle} {s.as_of}", "Cash received does not tie: previous year-to-date plus this month's cash is not this report's year-to-date",
                                        observed=f"{prev_ytd:g} + {s.realised_month_m:g} = {prev_ytd + s.realised_month_m:g} vs stated {ytd:g} (difference {ytd - prev_ytd - s.realised_month_m:+g})",
                                        threshold=f"within {tolerance:g}"))
        if ytd is not None and prev and prev["ytd"] is not None and s.as_of.month > 1 and ytd < prev["ytd"] - tolerance:
            findings.append(Finding("warn", "R03", f"{s.vehicle} {s.as_of}", "Year-to-date cash received is lower than in the previous report",
                                    observed=f"{ytd:g} after {prev['ytd']:g}"))
        row = {"as_of": s.as_of, "ytd": ytd, "basis": basis, "month_stated": s.realised_month_m, "prior_year_stated": s.realised_prior_year_m,
               "portfolio_fv": s.implied_portfolio_fv, "text": s.realised_text}
        rows.append(row)
        by_date[s.as_of] = row

    # whole-year totals: the December report, cross-checked against any later statement of the same year
    totals: dict[int, float] = {}
    for r in rows:
        if r["as_of"].month == 12 and r["ytd"] is not None:
            totals[r["as_of"].year] = r["ytd"]
    for r in rows:
        if r["prior_year_stated"] is None:
            continue
        yr = r["as_of"].year - 1
        if yr in totals and abs(totals[yr] - r["prior_year_stated"]) > tolerance:
            findings.append(Finding("warn", "R04", f"{snaps[0].vehicle} {yr}", "The year's cash received in the December report differs from the figure in a later report",
                                    observed=f"December report {totals[yr]:g} vs {r['prior_year_stated']:g} stated in the {r['as_of']} report"))
        totals.setdefault(yr, r["prior_year_stated"])

    # running total since 1 January of the first year; it stops being defined after a year with no total
    if rows:
        first_year, base, broken = rows[0]["as_of"].year, 0.0, False
        for yr in range(first_year, rows[-1]["as_of"].year + 1):
            for r in rows:
                if r["as_of"].year == yr:
                    r["cumulative"] = None if (broken or r["ytd"] is None) else base + r["ytd"]
            if yr in totals:
                base += totals[yr]
            elif yr < rows[-1]["as_of"].year:
                broken = True
                findings.append(Finding("warn", "R07", f"{snaps[0].vehicle} {yr}", "No total for the year's cash received; windows that span this year-end cannot be computed"))
        for a, b in zip(rows, rows[1:]):
            a_c, b_c = a.get("cumulative"), b.get("cumulative")
            b["cash_in_month"] = (b_c - a_c) if (a_c is not None and b_c is not None and _months_between(a["as_of"], b["as_of"]) == 1) else None
        rows[0]["cash_in_month"] = rows[0]["ytd"] if rows[0]["as_of"].month == 1 else None
    missing = [r["as_of"].isoformat() for r in rows if r["ytd"] is None]
    if missing:
        findings.append(Finding("info", "R01", snaps[0].vehicle, "Reports that do not state cash received from realisations; the gap closes at the next report that does",
                                observed=f"{len(missing)} of {len(rows)}: " + ", ".join(missing)))
    return rows, findings


def year_totals(rows: list[dict]) -> dict[int, float]:
    out: dict[int, float] = {}
    for r in rows:
        if r["as_of"].month == 12 and r["ytd"] is not None:
            out[r["as_of"].year] = r["ytd"]
    for r in rows:
        if r["prior_year_stated"] is not None:
            out.setdefault(r["as_of"].year - 1, r["prior_year_stated"])
    return out


def calibrate(rows: list[dict], cfg: dict, fallback_pace: float) -> dict:
    """Exit pace = cash received over a window / average portfolio fair value over the same window, annualised.

    Windows end at the latest report with a known running total. A window of W months starts W months
    earlier; the running total must be known at that month-end (a year-start counts: the count restarts at
    zero each January). "all" starts at 1 January of the first year in the data. The average fair value is
    taken over the month-end reports from the window's start to the month before its end.
    """
    rule, min_months = str(cfg.get("base_rule", "lowest")), int(cfg.get("min_months", 12))
    out: dict = {"source": "assumed", "rule": rule, "windows": [], "base_pace": fallback_pace, "base_window": None, "end": None,
                 "fallback_pace": fallback_pace, "reason": ""}
    known = [r for r in rows if r.get("cumulative") is not None]
    if not known:
        out["reason"] = "no report states cash received from realisations"
        return out
    end = known[-1]
    out["end"], out["end_basis"] = end["as_of"], end["basis"]
    out["reports_after_end"] = [r["as_of"] for r in rows if r["as_of"] > end["as_of"]]
    anchors: dict[date, float] = {r["as_of"]: r["cumulative"] for r in known}
    first_year = rows[0]["as_of"].year
    totals, base = year_totals(rows), 0.0
    anchors.setdefault(date(first_year - 1, 12, 31), 0.0)
    for yr in range(first_year, end["as_of"].year):
        if yr not in totals:
            break
        base += totals[yr]
        anchors.setdefault(date(yr, 12, 31), base)
    origin = date(first_year - 1, 12, 31)

    def window(label: str, start: date) -> dict:
        w = {"window": label, "start": start, "end": end["as_of"], "months": _months_between(start, end["as_of"]), "cash": None,
             "avg_portfolio_fv": None, "pace": None, "note": ""}
        if start not in anchors:
            w["note"] = "running total not known at the start of the window"
            return w
        if w["months"] < min_months:
            w["note"] = f"shorter than {min_months} months"
            return w
        fv = [r["portfolio_fv"] for r in rows if start <= r["as_of"] < end["as_of"] and r["portfolio_fv"]]
        if not fv:
            w["note"] = "no portfolio fair value in the window"
            return w
        w["cash"] = anchors[end["as_of"]] - anchors[start]
        w["avg_portfolio_fv"], w["fv_observations"] = sum(fv) / len(fv), len(fv)
        w["pace"] = w["cash"] / w["avg_portfolio_fv"] * 12.0 / w["months"]
        return w

    for spec in cfg.get("windows_months", [12, 24, "all"]):
        if str(spec).lower() == "all":
            out["windows"].append(window("all", origin))
        else:
            n = int(spec)
            y, m = end["as_of"].year, end["as_of"].month - n
            while m <= 0:
                y, m = y - 1, m + 12
            out["windows"].append(window(f"{n} months", date(y, m, calendar.monthrange(y, m)[1])))
    usable = [w for w in out["windows"] if w["pace"] is not None]
    if not usable:
        out["reason"] = "no window could be computed: " + "; ".join(f"{w['window']}: {w['note']}" for w in out["windows"])
        return out
    if rule == "lowest":
        pick = min(usable, key=lambda w: w["pace"])
    elif rule == "highest":
        pick = max(usable, key=lambda w: w["pace"])
    elif rule == "median":
        pick = sorted(usable, key=lambda w: w["pace"])[(len(usable) - 1) // 2]
    else:
        named = [w for w in usable if w["window"] in (rule, f"{rule} months")]
        if not named:
            out["reason"] = f"the window named by base_rule ('{rule}') could not be computed"
            return out
        pick = named[0]
    out.update(source="calibrated", base_pace=pick["pace"], base_window=pick["window"])
    return out
