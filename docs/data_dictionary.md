# Data dictionary

## Input files (the file plug's layout; also what `navmon refresh` writes)

All files are UTF-8 CSV with a header row. A data directory holds one of each.

### `holdings_<vehicle>.csv` : one row per holding per report
| Column | Meaning |
|---|---|
| `vehicle` | Short name of the fund or vehicle; must match `snapshots` |
| `as_of` | Report date, `YYYY-MM-DD` |
| `company` | Company name exactly as published |
| `vintage` | Year of investment; may be blank |
| `sponsor` | Lead sponsor (manager) as published; several are separated by `/` |
| `sector` | Sector label as published |
| `fair_value` | Fair value in the snapshot's unit and currency |
| `pct_of_fv` | Share of the vehicle's whole portfolio, as a fraction (0.062 = 6.2%); may be blank |

### `snapshots_<vehicle>.csv` : one row per report
| Column | Meaning |
|---|---|
| `vehicle`, `as_of` | Key |
| `published` | Date the report was released |
| `source_url` | Where it was read from |
| `headline` | The announcement's title |
| `currency`, `unit` | For example `USD`, `millions` |
| `stated_total_fv` | The publisher's own total for the listed holdings |
| `stated_total_pct` | The listed holdings' stated share of the whole portfolio, as a fraction |
| `nav_per_share_usd`, `nav_per_share_gbp` | As published; blank if not applicable |
| `valuation_mix` | `date:share` pairs separated by `;`, for example `2026-08-31:0.08;2026-06-30:0.92` |
| `investment_level_pct` | Investments as a percentage of NAV, where published |
| `cash_m`, `undrawn_credit_m` | The vehicle's cash and undrawn credit line, where published separately |

### `track_record_<lp>.csv` : one row per fund
| Column | Meaning |
|---|---|
| `lp`, `program`, `as_of` | The investor, its programme and the table's date |
| `fund` | Fund name as published |
| `vintage` | The investor's first cash flow year |
| `committed`, `cash_in`, `cash_out` | In currency units |
| `total_value` | Cash out plus remaining value |
| `net_irr` | As published, for example `41.3%` or `N/M` |
| `multiple` | As published, for example `1.4x` or `N/M` |
| `footnote` | The footnote marker on the row, if any |

### `prices.csv` : `date, symbol, adj_close, close, currency`
### `rates.csv` : `date, series, value_pct`

## Derived measures

| Measure | Definition |
|---|---|
| DPI | cash out / cash in |
| RVPI | (total value - cash out) / cash in |
| TVPI | total value / cash in |
| Age | table year - vintage year |
| Cohort rank | Position within funds of the same vintage year in the same table: share strictly below plus half of ties, 0 to 1. Needs at least `cohort_min_funds` funds |
| Seasoned / mature | Age at least `seasoned_age_years` / `mature_age_years` |
| Eligible NAV | fund-finance-lab's eligible NAV: eligible holdings after the single-name cap and top-N limit |
| LTV | loan / eligible NAV |
| Effective names | 1 / Herfindahl index of the eligible holdings |
| Weighted mark age | Days between each valuation date and the reference date, weighted by share of portfolio |

## Output files (one run, one folder)

| File | Contents |
|---|---|
| `memo.md` | The memo. Each section names the files its figures come from |
| `recommendation.json` | Verdict, proposed terms, every flag with rule and observation, the test results for each opening LTV |
| `collateral.csv` | Every published holding: eligible or not and why, share, sponsor rating, proxy, estimated value |
| `pool_summary.csv` | Pool totals, concentration, sector shares, eligible NAV as reported and estimated |
| `sponsor_overlay.csv` | Each holding's sponsor joined to its track record |
| `track_record_funds.csv`, `_families.csv`, `_vintages.csv` | Fund metrics, manager ratings, medians by vintage year |
| `sizing_candidates.csv` | One row per opening LTV: loan, cushion, tests passed or failed, breakeven exit pace |
| `stress_uniform.csv`, `stress_single_name.csv`, `stress_scenarios.csv` | The three stress families |
| `runoff.csv`, `runoff_pace_grid.csv` | Quarter-by-quarter repayment paths; sensitivity to exit pace |
| `roll_forward.csv` | Per holding: proxy, return since its marks, estimated value |
| `backtest_periods.csv`, `_observations.csv`, `_skipped.csv`, `_summary.csv`, `_robustness.csv` | The accuracy test and what was left out |
| `covenant_replay.csv`, `_summary.csv` | LTV at every past report for a loan fixed at the first |
| `changes.csv`, `changes_sectors.csv` | Company-level and sector-level changes since the comparison report |
| `findings.csv` | Every data-quality finding: severity, code, scope, message, observed, threshold |
| `run_manifest.json` | Versions, data dates and sha256 of every input, config and output |
| `nav_monitor.xlsx` | The tables above as sheets, values only |

## Finding and flag codes

| Prefix | Area | Examples |
|---|---|---|
| `Q` | Holdings tables | Q01 rows do not sum to the total; Q03 a row implies a different portfolio size; Q04 duplicate name; Q10 to Q12 a company's vintage, sector or sponsor label changed |
| `T` | Track record | T01 multiple does not recompute; T04 extreme IRR; T05 value below cash out; T06 no cash in; T07 cash in far above commitment; T09 active funds only |
| `H` | Live holdings parser | H00 no table found; H01 row skipped; H03 two reports with the same date |
| `M`, `S` | Market data and scenarios | M01 no prices for a proxy; M02 prices end before the report; S01 scenario skipped |
| `P` | Policy flags in the recommendation | P13 sponsor coverage; P15 vehicle borrowing; P18 repayment depends on exit pace |
