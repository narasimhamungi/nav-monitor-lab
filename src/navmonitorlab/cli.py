"""navmon: command line for nav-monitor-lab.

  navmon run            analyse the data on disk and write the memo, tables and workbook
  navmon refresh        fetch the latest published data from the live sources
  navmon update         refresh, then run (the one command a scheduled job needs)
  navmon check-sources  one small live call per source, to see what is reachable from this machine
  navmon verify-live    compare what the live sources parsed with the shipped sample

Run from the repository root. `run` never touches the network.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from . import __version__, config, excel, pipeline, refresh as refresh_mod, report


def _load_env(path: Path = Path(".env")) -> None:
    """KEY=VALUE lines from .env override the environment (stale Windows `setx` values lose)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def _data_dir(arg: str | None, cfg: dict) -> Path:
    if arg:
        return Path(arg)
    live = Path("data/live")
    return live if (live / cfg["vehicle"]["files"]["snapshots_csv"]).exists() else Path("data/sample")


def cmd_run(a) -> int:
    cfg = config.load(Path(a.config), a.vehicle)
    data = _data_dir(a.data, cfg)
    res = pipeline.analyse(cfg, data, as_of=date.fromisoformat(a.as_of) if a.as_of else None,
                           compare_to=date.fromisoformat(a.compare_to) if a.compare_to else None)
    out = Path(a.out)
    files = report.write_outputs(res, out)
    xlsx = None if a.no_excel else excel.export(out)
    (out / "run_manifest.json").write_text(json.dumps(pipeline.run_manifest(cfg, data, res, files), indent=1) + "\n", encoding="utf-8", newline="\n")
    prop = res["proposed"]
    print(f"Data: {data}  |  holdings as of {res['snapshot'].as_of}  |  track record as of {res['track_record'].as_of}"
          + (f"  |  prices to {res['roll_forward']['to']}" if res["roll_forward"].get("to") else "  |  no market data"))
    print(f"Verdict: {res['verdict']}" + (f"  |  opening LTV {prop['opening_ltv']:.0%}, loan {prop['loan']:,.1f}" if prop else ""))
    for f in res["flags"]:
        if f.severity != "note":
            print(f"  [{f.severity}] {f.title}: {f.observed}")
    fc = res["finding_counts"]
    print(f"Findings: {fc.get('error', 0)} errors, {fc.get('warn', 0)} warnings, {fc.get('info', 0)} notes")
    print(f"Wrote {len(files) + 1 + (1 if xlsx else 0)} files to {out}  (start with {out / 'memo.md'})")
    if not a.no_excel and xlsx is None:
        print("Excel export skipped: openpyxl is not installed (pip install openpyxl)")
    return 0


def _print_refresh(rep: dict) -> None:
    for step, info in rep["steps"].items():
        extra = {k: v for k, v in info.items() if k not in ("status", "parser_findings") and v not in (None, [], "")}
        print(f"  {step:9s} {info['status']:8s} {json.dumps(extra, default=str)}")
        for pf in info.get("parser_findings") or []:
            print(f"            finding {pf['code']}: {pf['message']} ({pf['scope']})")
    if rep["seeded_from_sample"]:
        print("  WARNING: these files were copied from data/sample because the live fetch failed and nothing was on disk: "
              + ", ".join(rep["seeded_from_sample"]))


def cmd_refresh(a) -> int:
    cfg = config.load(Path(a.config), a.vehicle)
    only = tuple(x.strip() for x in a.only.split(",")) if a.only else refresh_mod.STEPS
    rep = refresh_mod.refresh(cfg, Path(a.data), cache_dir=Path(a.cache), sample_dir=Path("data/sample"), only=only)
    print(f"Refresh into {a.data}:")
    _print_refresh(rep)
    return 0 if all(s["status"] in ("OK", "PARTIAL") for s in rep["steps"].values()) else 1


def cmd_update(a) -> int:
    rc = cmd_refresh(a)
    a.data = a.data if Path(a.data).exists() else None
    cmd_run(a)
    return rc


def cmd_check(a) -> int:
    cfg = config.load(Path(a.config), a.vehicle)
    rows = refresh_mod.check_sources(cfg)
    for r in rows:
        print(f"  {r['status']:4s}  {r['source']:40s} {r['detail']}")
    return 0 if all(r["status"] == "PASS" or "tiingo" in r["source"] for r in rows) else 1


def cmd_verify(a) -> int:
    cfg = config.load(Path(a.config), a.vehicle)
    res = refresh_mod.verify_live(cfg, Path(a.live), Path(a.sample))
    print(json.dumps(res, indent=1, default=str))
    print("AGREE: live parsers and the captured sample match on everything they share." if res["agree"]
          else "DIFFERENCES FOUND: see the mismatches above.")
    return 0 if res["agree"] else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):          # a Windows console that cannot show a character prints "?" instead of failing
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    _load_env()
    p = argparse.ArgumentParser(prog="navmon", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"navmon {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--config", default="configs", help="config directory (default: configs)")
        sp.add_argument("--vehicle", default=None, help="vehicle config file name inside the config directory")

    def run_args(sp):
        sp.add_argument("--out", default="outputs/latest", help="output directory (default: outputs/latest)")
        sp.add_argument("--as-of", dest="as_of", default=None, help="analyse the report dated YYYY-MM-DD (default: latest)")
        sp.add_argument("--compare-to", dest="compare_to", default=None, help="change log against the report dated YYYY-MM-DD (default: previous)")
        sp.add_argument("--no-excel", action="store_true", help="skip the workbook")

    sp = sub.add_parser("run", help="analyse the data on disk"); common(sp); run_args(sp)
    sp.add_argument("--data", default=None, help="data directory (default: data/live if it exists, else data/sample)")
    sp.set_defaults(fn=cmd_run)
    for name, fn, hlp in (("refresh", cmd_refresh, "fetch the latest published data"), ("update", cmd_update, "refresh, then run")):
        sp = sub.add_parser(name, help=hlp); common(sp)
        sp.add_argument("--data", default="data/live", help="where to store fetched data (default: data/live)")
        sp.add_argument("--cache", default="data/raw", help="raw download cache, not committed (default: data/raw)")
        sp.add_argument("--only", default=None, help="comma-separated subset of: holdings,track,prices,rates")
        if name == "update":
            run_args(sp)
        sp.set_defaults(fn=fn)
    sp = sub.add_parser("check-sources", help="one small live call per source"); common(sp); sp.set_defaults(fn=cmd_check)
    sp = sub.add_parser("verify-live", help="compare live-parsed data with the shipped sample"); common(sp)
    sp.add_argument("--live", default="data/live"); sp.add_argument("--sample", default="data/sample"); sp.set_defaults(fn=cmd_verify)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except (FileNotFoundError, ValueError) as e:
        print(f"navmon: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
