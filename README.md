# nav-monitor-lab

Underwrites and monitors an illustrative NAV loan on a real, published private equity portfolio. It reads
a listed vehicle's monthly holdings from the UK regulatory archive, reads its sponsors' track records from a
public pension fund's disclosure, sizes and stresses a loan with
[fund-finance-lab](https://github.com/narasimhamungi/fund-finance-lab), rolls stale marks forward with listed
markets, tests that estimate against the vehicle's own history, calibrates the pace of exits from the cash
the vehicle reports receiving, and writes a memo with a rule-based recommendation. When the publishers release new data, one command re-runs everything and reports what changed.

> Illustrative analysis on public data. The loan terms are assumptions, not observed market terms. Not a
> rating, not a valuation, not advice.

## What it found on the shipped data

Run on NB Private Equity Partners (NBPE) holdings as of 31 August 2026, CalPERS sponsor records as of
31 March 2026 and prices to 6 October 2026. Full memo: [`outputs/sample/memo.md`](outputs/sample/memo.md).

- **Recommendation: proceed with conditions at 15% opening LTV**: a loan of $138.4m against eligible NAV of
  $922.9m. 20% fails one test: at the calibrated exit pace $32.7m is still unpaid at maturity.
- **The exit pace is calibrated, not assumed.** Cash received from realisations, read from 55 monthly reports,
  divided by average portfolio fair value: 15.9% a year over the last 12 months, 11.7% over 24, 12.1% since
  January 2022. The base case is the lowest, by a rule in the config. Version 0.1.0 assumed 15% and proposed
  20% LTV ($184.6m); that result is kept in the memo as a labelled sensitivity. Nothing else was changed.
- **Three conditions**, each a rule with its observed number: a rated sponsor record exists for only 17% of
  eligible value; the vehicle is itself borrowing (investment level 115%); repayment needs 10.0% of the pool
  realised a year against a base pace of 11.7%, and policy wants it to work at 80% of the base pace.
- **Passing listed-market moves through to private marks in full is the worst option.** Over 18 quarterly
  valuation cycles and 433 company observations, the fitted pass-through is 0.13. Full pass-through gave an
  average error of 5.8% a quarter against 1.7% for simply carrying stale marks.
- **The roll-forward estimate is not a reliable improvement.** It beat stale marks on two of the three
  possible sets of reporting months, not all three. The memo says so and treats the estimate as a direction
  check only.
- **A 25% loan struck in February 2022 would have hit the cash-sweep level in June 2022** on full
  pass-through values, and never on reported values. Reported marks barely moved that year.
- **Data-quality findings, reported and not corrected**: three of the 55 monthly holdings tables do not sum
  to the publisher's own total row; one month's cash received does not tie to the month before (53 + 8 against
  a stated 66); 8 of 55 reports give no figure for cash received; one month lists the same undisclosed name
  twice; the pension fund's table prints a 700.9% IRR for a 2023 fund and shows one fund with $795m paid in
  against a $38m commitment.

## What is and is not verified

| Claim | Status |
|---|---|
| Analysis runs end to end on real published data, offline, with byte-identical outputs on a re-run | Demonstrated (`pytest`, 114 tests) |
| Shipped CalPERS data matches the live page | Demonstrated on 2026-10-07: 485 rows tie to five column sums read off the page |
| Shipped NBPE holdings match the publisher | Demonstrated: 52 of 55 tables tie to their own total row; the other three are the publisher's inconsistency |
| Live parsers read the real pages | Demonstrated against real excerpts of each page and API response (`tests/fixtures/`) |
| Live fetch works from a normal machine | Demonstrated on 2026-10-07 (Windows, Python 3.14): all four sources answered; 55 reports, 485 funds, 9 price series and 2 rate series fetched |
| Live parsers and the shipped sample agree | Demonstrated by `navmon verify-live`: 55 of 55 holdings tables, 485 of 485 funds and 774 of 774 closes. One sample row carried a footnote digit in a company name; corrected and recorded in `data/sample/manifest.json` |
| Result on freshly fetched data equals the shipped result | Demonstrated for version 0.1.0 (same verdict, loan and conditions). Not yet repeated for 0.2.0 |
| Cash received is read correctly from the reports | Demonstrated on the captured text of all 55 reports: the reader, the same wordings run in a browser over each full report, and a reading by eye agree. Year totals for 2023 to 2025 match the figures the publisher restates in its annual results |
| The live parser reads cash received from the live pages | **Not yet demonstrated.** Tested on real HTML from seven reports. `navmon refresh` then `navmon verify-live` checks all 55 |
| It re-runs when new data is published | **Not yet demonstrated.** `navmon update` has run once; no new report has been published since |
| Tiingo price plug | **Not exercised.** Written from Tiingo's documented format |
| Scheduled refresh on GitHub Actions | **Not yet run** |
| It screens private debt managers | No. Private equity only (see `docs/decisions.md`, D-02) |
| It is manager due diligence | No. It is quantitative screening of one investor's public table |

## Quick start

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
pytest -q
navmon run --data data/sample --out outputs/check     # offline, on the shipped data
navmon check-sources                                  # which live sources answer from this machine
navmon update                                         # fetch the latest and re-run
```

Every command, with what to expect from each: [`docs/COMMANDS.md`](docs/COMMANDS.md).

## How it is put together

```
live sources ──> navmon refresh ──> data/live/*.csv ──> navmon run ──> outputs/<name>/memo.md + tables + workbook
 (plugs)          (only step that          (plain files,        (no network,
                   touches the network)     hashed)              reproducible)
```

Four sockets, each with a free plug today. A professional source is one new class and one config line
(`docs/sources.md`).

| Socket | Free plug in use | What a firm would plug in |
|---|---|---|
| Holdings and fair values | FCA National Storage Mechanism (regulatory announcements) | The fund's reporting pack and data room |
| Manager track records | CalPERS fund performance table | Preqin, PitchBook, MSCI Burgiss |
| Prices | Yahoo chart endpoint (Tiingo plug also included) | Bloomberg, LSEG, FactSet |
| Reference rates | FRED (SOFR, SONIA) | The same feed as prices |
| Any of the above | File plug: a CSV in the documented layout | An export from any of them |

Everything that is a choice lives in `configs/`: one YAML per vehicle, the fund-name-to-manager map, the
sector proxies, the covenant levels, the stress scenarios and every policy threshold behind the memo.

| Path | Purpose |
|---|---|
| `src/navmonitorlab/sources/` | The plugs and the sockets they fit |
| `src/navmonitorlab/quality.py` | Tie-outs and data checks; findings are reported, never fixed |
| `src/navmonitorlab/trackrecord.py` | Realisation metrics, vintage ranks, sponsor ratings, overlay on the pool |
| `src/navmonitorlab/sizing.py` | Bridge to fund-finance-lab; sector scenarios; repayment from exits |
| `src/navmonitorlab/realisations.py` | Cash received from realisations: reading, reconciliation, exit-pace calibration |
| `src/navmonitorlab/rollforward.py`, `backtest.py` | Market estimate, its measured error, covenant replay |
| `src/navmonitorlab/diff.py` | What changed since the previous report |
| `src/navmonitorlab/recommend.py`, `report.py` | Rules, verdict, memo and tables |
| `data/sample/` | Real published data captured 2026-10-07, with hashes and tie-outs |
| `docs/` | Plan and status, commands, sources, data dictionary, model spec, decisions, limitations |

## Limits

The collateral is a listed vehicle's published top 30 holdings, not a private fund asking for a loan; no
fund documents or company financials were seen. Sponsor records come from one investor, active funds only.
The exit pace is the whole portfolio's past pace, applied to the eligible pool and to the next four years.
The data is monthly and lagged, not a live feed: prices and rates move daily, holdings monthly, track
records quarterly. Full list in [`docs/limitations.md`](docs/limitations.md).
