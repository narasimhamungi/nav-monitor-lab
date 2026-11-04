# Claims ledger

Generated 2026-11-04 from the v0.2.0 build record. Tags: Demonstrated / Inferred / Assumed / Unsupported.

| Claim in README | Tag | Evidence |
|---|---|---|
| Runs a NAV-loan sizing and stress model on a real published PE portfolio of 30 holdings over 55 monthly reports | Demonstrated | `data/sample/` (55 NBPE monthly tables), `outputs/memo.md`, `tests/` |
| Screens 485 funds from a public pension disclosure and rates managers on capital returned within vintage year | Demonstrated, for one investor's active funds | `data/sample/calpers/`, `outputs/track_record.csv` |
| Backtests a mark roll-forward over 18 valuation cycles and reports it is not a reliable improvement | Demonstrated | `outputs/backtest_report.md` (robustness section) |
| Reconciles every input table to the publisher's totals and carries exceptions into the memo | Demonstrated | `tests/test_tie_out.py`, `outputs/memo.md` |
| Calibrates exit pace from cash received in 55 monthly reports (11.7%-15.9%/yr by window) and sizes the loan on it | Demonstrated on the captured sample | `data/sample/`, `runoff_sensitivity.csv` |
| Proposes 15% opening LTV, $138.4m, with three conditions | Demonstrated; illustrative, on assumed covenants, margin and sweep | `outputs/memo.md` |
| "$185m at 20% LTV" | Superseded — now a labelled sensitivity on the former 15% assumption | `runoff_sensitivity.csv` |
| The live parser reads cash received from the live pages | Inferred, from tests on real HTML from 7 reports; not yet confirmed by a `verify-live` run against the new columns | `tests/test_exit_pace_parser.py` |
| Fetches from four live public sources and cross-checks the parse against an independent capture | Demonstrated once, 2026-10-07, for holdings, track records and prices | run log of `navmon verify-live` |
| Re-runs when new data is published | Inferred until `navmon update` has picked up a newly published report; "automatically" is unsupported until the scheduled workflow has run | — (open item) |
| Compatible with Bloomberg or Preqin | Unsupported | README should say "source-agnostic; a new source is one class" |
| Manager due diligence | Unsupported — it is quantitative screening | — |
| "Underwrites NAV loans" | Unsupported as stated | README should say "runs an illustrative underwriting on public data" |

## Action
No README overclaim found beyond the two phrasings above ("Bloomberg/Preqin compatible", "underwrites NAV loans") — confirm README already uses the hedged wording; if not, apply the two substitutions shown.
