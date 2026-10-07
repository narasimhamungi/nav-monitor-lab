"""Excel export: one workbook, one sheet per output table, values only.

This is a results export for people who work in Excel. It is not a formula model; the formula-driven
NAV model lives in fund-finance-lab (excel/nav_facility_stress.xlsx).
"""
from __future__ import annotations

import csv
from pathlib import Path

SHEETS = [("Summary", "pool_summary.csv"), ("Collateral", "collateral.csv"), ("Sizing", "sizing_candidates.csv"),
          ("Stress uniform", "stress_uniform.csv"), ("Stress scenarios", "stress_scenarios.csv"), ("Stress names", "stress_single_name.csv"),
          ("Realisations", "realisations.csv"), ("Exit pace", "exit_pace_calibration.csv"), ("Runoff", "runoff.csv"),
          ("Runoff pace", "runoff_pace_grid.csv"), ("Runoff sensitivity", "runoff_sensitivity.csv"), ("Roll forward", "roll_forward.csv"),
          ("Backtest", "backtest_periods.csv"), ("Backtest summary", "backtest_summary.csv"), ("Backtest robustness", "backtest_robustness.csv"), ("Covenant replay", "covenant_replay_summary.csv"),
          ("Sponsors", "sponsor_overlay.csv"), ("Families", "track_record_families.csv"), ("Vintages", "track_record_vintages.csv"),
          ("Changes", "changes.csv"), ("Findings", "findings.csv")]


def _value(text: str):
    if text == "":
        return None
    if text in ("True", "False"):
        return text == "True"
    try:
        return int(text) if text.lstrip("-").isdigit() else float(text)
    except ValueError:
        return text


def export(out_dir: Path, path: Path | None = None) -> Path | None:
    """Build the workbook from the CSVs already written to `out_dir`. Returns None if openpyxl is absent."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None
    out_dir = Path(out_dir)
    path = path or out_dir / "nav_monitor.xlsx"
    wb = Workbook()
    wb.remove(wb.active)
    for title, name in SHEETS:
        src = out_dir / name
        if not src.exists():
            continue
        ws = wb.create_sheet(title)
        with open(src, newline="", encoding="utf-8") as fh:
            for i, row in enumerate(csv.reader(fh)):
                ws.append(row if i == 0 else [_value(c) for c in row])
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.freeze_panes = "A2"
        for i, col in enumerate(ws.columns, 1):
            width = max((len(str(c.value)) for c in col[:60] if c.value is not None), default=8)
            ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 8), 60)
    note = wb.create_sheet("Read me", 0)
    for line in ("nav-monitor-lab results export (values only).", "Each sheet is one CSV from the same run; memo.md quotes these figures.",
                 "Illustrative analysis on public data. Not a rating, not a valuation, not advice.",
                 "The formula-driven NAV model is in fund-finance-lab: excel/nav_facility_stress.xlsx."):
        note.append([line])
    note.column_dimensions["A"].width = 100
    wb.save(path)
    return path
