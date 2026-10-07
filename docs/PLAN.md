# Plan and build checklist

Status as of 2026-10-07, version 0.2.0. Version 0.1.0 was run live on the author's Windows machine; the
exit-pace calibration added in 0.2.0 has run on the captured sample only. "Done" means built and covered by a
passing test or a recorded run.

## Goal

Run fund-finance-lab's NAV-loan model on a real published portfolio, add the sponsor track record a lender
would screen, measure how far stale private marks can be trusted, and re-run when new data is published.

## Scope decisions (changed from the original brief)

| Brief said | Built | Why |
|---|---|---|
| HVPE or Pantheon holdings as collateral | NBPE top-30 holdings | HVPE's monthly update has no holdings and PIN's lists five companies by percentage; NBPE publishes 30 names with fair values, about 80% of its portfolio |
| Private equity and private debt managers | Private equity only | CalPERS shows "N/M" or 0.1% IRR on all 66 private debt lines |
| Refresh and diff on CalPERS | Diff on NBPE monthlies; CalPERS snapshots are archived for later diffs | CalPERS is one snapshot with a two-quarter lag; no history was found |
| Quarterly, lagged data | Monthly holdings plus a daily market layer | So the output moves between publications |
| One hard-coded source per need | Four sockets with swappable plugs and a file plug | So a professional feed is one class and one config line |
| Name: nav-diligence-lab | nav-monitor-lab | It underwrites and monitors; it does not do manager due diligence |

## Checklist

### Stage 0: sources
- [x] CalPERS PE table: columns, row count, markup captured from the live page
- [x] NBPE monthly announcements: 55 months of top-30 tables on the FCA archive, consistent headings
- [x] FCA NSM search API: request and response shape captured
- [x] Yahoo chart endpoint and FRED CSV: response shapes captured
- [x] Stooq tested and dropped ("Access denied" to CSV downloads)
- [x] fund-finance-lab read: takes an asset list, installable, no release tag (pinned to commit `d771874`)

### Stage 1: real-data underwriting
- [x] Schema, file plug, config loader
- [x] Holdings tie-out to the publisher's total row; findings carried, nothing corrected
- [x] Collateral pool with eligibility reasons; concentration measures
- [x] Sizing through fund-finance-lab: opening-LTV grid, uniform drawdowns, largest-name losses
- [x] Sector scenarios (configured and market-history driven)
- [x] Repayment from exits: base, drought, drought plus markdown, breakeven pace
- [x] Rule-based recommendation: terms, conditions, verdict
- [x] Memo, CSV tables, Excel export, run manifest with hashes
- [x] Byte-identical outputs on re-run

### Stage 2: market layer
- [x] Roll-forward from valuation dates using sector proxies; quoted holdings handled separately
- [x] Discount to NAV from the vehicle's own share price
- [x] Base rate from SOFR for the all-in cost
- [x] Backtest: 18 cycles, 433 observations; in-sample and walk-forward error
- [x] Robustness across reporting months (this is what showed the estimate is not a reliable improvement)
- [x] Covenant replay from February 2022
- [x] Full pass-through outer bound in the memo

### Stage 3: sponsor track record
- [x] CalPERS ingest, tie-out to page column sums, quality checks
- [x] Fund-name-to-manager map (229 of 485 funds; 26 by inference, flagged)
- [x] Capital-returned rank within vintage year; rating rule; vintage table
- [x] Overlay on the collateral pool; coverage measured (17% of eligible value has a rated sponsor)

### Stage 4: live refresh and monitoring
- [x] Live plugs: FCA NSM, CalPERS, Yahoo chart, Tiingo, FRED
- [x] `navmon refresh`, `update`, `check-sources`, `verify-live`
- [x] Failure handling: a failed source is reported and never overwrites good data
- [x] Change log between reports; watchlist; track-record snapshot archive
- [x] First live run, 2026-10-07 (Windows, Python 3.14): `check-sources` passed on FCA NSM, CalPERS, Yahoo and
      FRED; `refresh` fetched 55 reports, 485 funds, 9 price series, 2,598 rate observations
- [x] `verify-live`: 55 of 55 holdings tables, 485 of 485 funds and 774 of 774 closes agree with the shipped
      sample. It found one error, in the sample: a superscript footnote digit captured as part of a company
      name (2023-09-30). Corrected; recorded in `data/sample/manifest.json`
- [x] `navmon run` on the freshly fetched data gives the same verdict, loan and conditions as the sample
- [ ] **Not yet seen:** a second `navmon update` after a new report is published (next NBPE report is due late October)
- [ ] **Not exercised:** Tiingo plug (needs `TIINGO_API_KEY`)
- [ ] **Not run:** scheduled refresh workflow on GitHub Actions (left manual-only)

### Stage 5: packaging
- [x] 114 tests, CI workflow, `.gitattributes` so hashes survive Windows checkouts
- [x] README, commands, sources, data dictionary, model spec, decisions, limitations, changelog
- [x] Public on GitHub; CI green on version 0.1.0 (author's report, 2026-10-07)

### Stage 6: exit-pace calibration (version 0.2.0)
- [x] Found where realisations are reported: sentences in the same monthly NAV announcements
- [x] Reader for cash received (year to date, month, previous year); announced, pending and pro forma never read
- [x] Sample extended: 47 of 55 reports state a figure; three readings agree on all 55
- [x] Reconciliation: month against year to date (one exception, reported), December against restated totals
- [x] Calibration: 12 months 15.9%, 24 months 11.7%, all months 12.1%; base case by rule (`lowest`)
- [x] Full re-run with no rule changed: recommendation moved from 20% ($184.6m) to 15% ($138.4m)
- [x] The former 15% assumption kept as a labelled sensitivity in the memo and in `runoff_sensitivity.csv`
- [ ] **Not yet run live:** `navmon refresh` then `navmon verify-live` with the new columns
- [ ] fund-finance-lab release tag (optional; command in `COMMANDS.md`)
- [ ] Interview prep document: not written. It is personal and must stay outside this repository

### Not built, by decision
- Private debt (SEC BDC data sets are the route; `decisions.md` D-02)
- HVPE and Pantheon ingestion
- A second investor's track-record table (CalSTRS, Oregon, Washington State publish similar tables)
- Exit pace for the eligible names only (the reports name the companies sold, not the cash from each)
- Automatic alias detection for renamed companies (aliases are hand-entered in the vehicle config)
- Own-ticker pricing for quoted holdings (they use the sector proxy)
- A dashboard

## What can and cannot be claimed (version 0.2.0)

| Statement | Tag |
|---|---|
| Runs a NAV-loan sizing and stress model on a real published PE portfolio of 30 holdings over 55 monthly reports | Demonstrated |
| Screens 485 funds from a public pension disclosure and rates managers on capital returned within vintage year | Demonstrated, for one investor's active funds |
| Backtests a mark roll-forward over 18 valuation cycles and reports that it is not a reliable improvement | Demonstrated |
| Reconciles every input table to the publisher's totals and carries exceptions into the memo | Demonstrated |
| Calibrates the exit pace from cash received in 55 monthly reports (11.7% to 15.9% a year by window) and sizes the loan on it | Demonstrated on the captured sample |
| Proposes 15% opening LTV, $138.4m, with three conditions | Demonstrated; illustrative, on assumed covenants, margin and sweep |
| "$185m at 20% LTV" | No longer the result. It is what the same rules give on the former 15% assumption, shown as a sensitivity |
| The live parser reads cash received from the live pages | Inferred from tests on real HTML from seven reports, until `verify-live` has run with the new columns |
| Fetches from four live public sources and cross-checks the parse against an independent capture | Demonstrated once, 2026-10-07, for holdings, track records and prices |
| Re-runs when new data is published | Inferred until `navmon update` has picked up a newly published report. "Automatically" is unsupported until the scheduled workflow has run |
| Compatible with Bloomberg or Preqin | Unsupported. Say "source-agnostic; a new source is one class" |
| Manager due diligence | Unsupported. It is quantitative screening |
| Underwrites NAV loans | Unsupported as stated. It runs an illustrative underwriting on public data |
