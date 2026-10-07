# NAV facility memo: NB Private Equity Partners Limited (NBPE)

*Illustrative analysis on public data. The loan terms are this tool's assumptions, not observed market terms. Not a rating, not a valuation, not advice.*

**Figures in USD millions unless stated.** Holdings as of 2026-08-31 (published 2026-09-23); 55 monthly reports from 2022-02-28. Sponsor records: CalPERS Private Equity, as of 2026-03-31. Prices to 2026-10-06. Base rate SOFR 3.89% on 2026-10-05.

## 1. Recommendation

**Proceed with conditions.** Opening LTV 15%: a loan of 138.4 against eligible NAV of 922.9 (72.3% of the vehicle's 1,277 portfolio).

| Term | Proposed | Basis |
|---|---|---|
| Opening LTV / loan | 15% / 138.4 | highest grid point that passes every test in sections 4 to 6 |
| Cash sweep / breach / cure-to | 30% / 40% / 25% | breach level from published agency commentary (initial 10-30%, maximum about 40%); sweep and cure are assumptions |
| Single-name cap / top-5 limit / minimum names | 7.5% / 30% / 15 | assumptions |
| Indicative all-in rate | 10.39% | SOFR 3.89% + 6.5% margin (margin is an assumption) |
| Tenor | 4 years | assumption |
| Excluded from the pool | 3 names, 93.1 | names or sponsors the publisher does not disclose |

**Conditions**

- **Sponsor track record available for too little of the pool** (P13). Observed: 17% of eligible value has a rated sponsor. Policy: at least 25%. Action: Request sponsor track records directly; public investor data does not cover these managers.
- **The vehicle is itself drawing on borrowings** (P15). Observed: investment level 115%; undrawn credit line $135m; cash $7m. Policy: at most 110%. Action: Confirm ranking against the vehicle's existing credit facility; this model assumes a first-ranking claim.
- **Repayment depends on the pace of exits** (P18). Observed: needs 10.0% of the pool realised a year to repay by maturity; base case uses 11.7% (calibrated from reported realisations). Policy: breakeven at most 80% of the base pace (9.4%). Action: Add scheduled amortisation or a maturity extension test; do not rely on exits alone.

**Notes**

- Undisclosed holdings excluded from the pool (P10): 8.9% of published fair value.
- Concentration limits reduce the borrowing base (P17): 35.2 excluded by the single-name cap and top-5 limit.
- Exit pace calibrated from the vehicle's reported realisations (P20): 11.7% a year, the lowest of the windows to 2026-07-31 (12 months 15.9%; 24 months 11.7%; all 12.1%); the former assumption was 15%.

**Why not 20%:** repayment from exits (base pace) fails (32.7 outstanding at maturity; peak LTV 20.0%).

## 2. Collateral pool (`collateral.csv`, `pool_summary.csv`)

- Published: 30 holdings worth 1,051.2; the publisher states 1,051.0, 82.3% of the portfolio. Holdings outside the published table get no credit.
- Eligible: 27 names, 958.1. Concentration limits remove a further 35.2, leaving eligible NAV of 922.9.
- Concentration: largest name 8.2%, top five 33.4%, top ten 54.4% of eligible value; equivalent to 22.3 equal-sized names. Quoted holdings are 6.4%.
- Sectors: Industrials 27%, Financial Services 16%, Consumer 16%, Business Services 15%, Technology / IT 12%, Healthcare 8%, Communications / Media 3%, Transportation 2%.
- Age of marks: 8% at 2026-08-31, 92% at 2026-06-30. Average age 57 days at the report date, 98 days for the private marks as of 2026-10-06.
- Vehicle liquidity as published: cash 7, undrawn credit line 135, investment level 115%.

| Largest eligible holdings | Lead sponsor | Sector | Fair value | Share | Sponsor record | Est. today |
|---|---|---|---|---|---|---|
| Action | 3i | Consumer | 78.4 | 8.2% | no record | 77.9 |
| Solenis | Platinum Equity | Industrials | 72.6 | 7.6% | no record | 71.9 |
| OneMonroe | AEA Investors | Industrials | 66.1 | 6.9% | no record | 65.5 |
| FDH Aero | Audax Group | Industrials | 56.1 | 5.9% | no record | 55.6 |
| True Potential | Cinven | Financial Services | 47.2 | 4.9% | no record | 47.3 |
| Mariner | Leonard Green & Partners | Financial Services | 46.3 | 4.8% | strong | 46.4 |
| Osaic | Reverence Capital | Financial Services | 41.5 | 4.3% | no record | 41.6 |
| BeyondTrust | Francisco Partners | Technology / IT | 39.1 | 4.1% | strong | 39.4 |
| Ryan | Ares / Onex | Business Services | 37.5 | 3.9% | strong | 37.2 |
| Constellation Automotive | TDR Capital | Business Services | 36.5 | 3.8% | no record | 36.2 |

## 3. Sponsor track record (`sponsor_overlay.csv`, `track_record_families.csv`)

Source: CalPERS's table of 485 active partnerships. The fund-name-to-manager map covers 229 funds (35% of remaining value); 26 of those are mapped by inference. Ratings compare how fast a manager has returned capital with other funds of the same vintage year in this one investor's book.

Of eligible value: 17% has a rated sponsor (15% strong, 2% adequate, 0% weak); 13% has a sponsor with too short a record; 70% has a sponsor with no funds in the table.

| Holding | Sponsor | Fair value | Rating | Older funds' DPI | Capital-returned rank | Map basis |
|---|---|---|---|---|---|---|
| Mariner | Leonard Green & Partners | 46.3 | strong | 2.30x | 0.90 | inferred |
| BeyondTrust | Francisco Partners | 39.1 | strong | 2.24x | 0.85 | name |
| Ryan | Ares / Onex | 37.5 | strong | 1.37x | 0.75 | name |
| Auctane | Thoma Bravo | 34.9 | insufficient | n/a | 0.84 | name |
| Benecon | TA Associates | 31.6 | insufficient | n/a | 0.42 | inferred |
| Staples | Sycamore Partners | 31.0 | insufficient | n/a | n/a | name |
| Engineering | Renaissance Partners / Bain Capital | 26.8 | insufficient | n/a | n/a | name |
| Kroll | Further Global / Stone Point | 21.5 | strong | 1.57x | 0.76 | name |
| Qpark | KKR | 17.3 | adequate | 1.37x | 0.55 | name |

## 4. Stress (`stress_uniform.csv`, `stress_scenarios.csv`, `stress_single_name.csv`)

LTV after a uniform fall in the pool, by opening LTV:

| Opening LTV | Loan | Today | -10% | -20% | -30% | -40% | -50% | -60% | Fall to breach |
|---|---|---|---|---|---|---|---|---|---|
| 10% | 92.3 | 10.0% | 11.1% | 12.5% | 14.3% | 16.7% | 20.0% | 25.0% | 75.0% |
| 15% * | 138.4 | 15.0% | 16.7% | 18.7% | 21.4% | 25.0% | 30.0% (sweep) | 37.5% (sweep) | 62.5% |
| 20% | 184.6 | 20.0% | 22.2% | 25.0% | 28.6% | 33.3% (sweep) | 40.0% (BREACH) | 50.0% (BREACH) | 50.0% |
| 25% | 230.7 | 25.0% | 27.8% | 31.2% (sweep) | 35.7% (sweep) | 41.7% (BREACH) | 50.0% (BREACH) | 62.5% (BREACH) | 37.5% |

Sector scenarios on the proposed loan (15% opening LTV, marked * above):

| Scenario | Pool falls | LTV | Status | Write-downs |
|---|---|---|---|---|
| Broad market -25% | 25.0% | 20.0% | ok | every sector -25% |
| Technology de-rating | 14.2% | 17.8% | ok | Technology / IT -40%; Communications / Media -30%; all other sectors -10% |
| Consumer and industrial recession | 24.1% | 19.3% | ok | Consumer -35%; Industrials -30%; Transportation -30%; Business Services -25%; all other sectors -15% |
| Financials shock | 14.9% | 17.9% | ok | Financial Services -40%; all other sectors -10% |
| Worst listed sector fall in the price history (2021-12-31 to 2022-12-31) | 24.5% | 19.8% | ok | Communications / Media -38%; Consumer -36%; Technology / IT -31%; Transportation -28%; Financial Services -21%; Business Services -21%; Industrials -21%; Healthcare -13% |

Largest names written off in full: 1 (Action added) LTV 16.2%, ok; 2 (Solenis added) LTV 17.5%, ok; 3 (OneMonroe added) LTV 18.9%, ok.

## 5. Repayment from exits (`realisations.csv`, `exit_pace_calibration.csv`, `runoff.csv`, `runoff_pace_grid.csv`, `runoff_sensitivity.csv`)

**Exit pace: 11.7% a year, calibrated from the vehicle's own reports.** Pace = cash received from realisations over a window, divided by the average portfolio fair value over the same months, annualised. The denominator is the fair value of the whole portfolio, not NAV and not the eligible pool; the model applies that pace to the eligible pool (assumption). Only cash the publisher says it received is counted; announced, pending and pro forma amounts are not.

| Window | Months | Cash received | Average portfolio value | Pace a year |
|---|---|---|---|---|
| 12 months to 2026-07-31 | 12 | 198 | 1,247 | 15.9% |
| 24 months to 2026-07-31 * | 24 | 295 | 1,260 | 11.7% |
| all, from 2022-01-01 to 2026-07-31 | 55 | 739 | 1,329 | 12.1% |

- Base case (*): the lowest of the windows, a rule set in `configs/facility.yaml`. The former assumption was 15%.
- Cash received by calendar year: 2022 120; 2023 171; 2024 179; 2025 180; 2026 89 to 2026-07-31.
- Not stated: 8 of 55 reports give no figure for cash received (2022-02-28, 2022-03-31, 2022-04-30, 2023-01-31, 2023-02-28, 2025-10-31, 2026-03-31, 2026-08-31). The running total picks up at the next report that does.
- The latest report (2026-08-31) is one of them, so the windows end at 2026-07-31, where the running total is the last stated year-to-date figure plus the monthly figures since.
- The publisher's own figures do not tie in 1 place: NBPE 2025-05-31: 53 + 8 = 61 vs stated 66 (difference +5). Reported as found; the stated year-to-date figure is used.

The loan is repaid from sale proceeds: 11.7% of the pool realised a year (calibrated base case), 50% of proceeds after interest applied to principal (assumption), all of it once LTV reaches the sweep level.

| Case | Repaid | Outstanding at maturity | Peak LTV | Interest added to the loan |
|---|---|---|---|---|
| Base pace | quarter 14 | 0.0 | 15.0% | 0.0 |
| Exits at 25% of pace for 8 quarters | not by maturity | 43.1 | 15.0% | 0.0 |
| Same drought plus a 25% markdown on day one | not by maturity | 74.9 | 20.3% | 0.0 |

Breakeven: the pool must realise 10.0% a year for the loan to be repaid by maturity. By pace: 5% leaves 77.0; 10% leaves 0.0; 15% leaves 0.0; 20% leaves 0.0; 25% leaves 0.0.

Sensitivity: the same rules on the former assumption of 15% a year, beside the base case. Outstanding at maturity, base repayment case:

| Opening LTV | Loan | Base case 11.7% | Former assumption 15% | Breakeven pace |
|---|---|---|---|---|
| 10% | 92.3 | repaid in quarter 8 | repaid in quarter 7 | 6.3% |
| 15% | 138.4 | repaid in quarter 14 | repaid in quarter 11 | 10.0% |
| 20% | 184.6 | 32.7 outstanding (fails a test) | repaid in quarter 16 | 14.3% |
| 25% | 230.7 | 89.5 outstanding (fails a test) | 48.2 outstanding (fails a test) | 19.5% |

Proposed loan: 15% (138.4) on the base case; 20% (184.6) on the former assumption.

## 6. Market layer (`roll_forward.csv`, `backtest_periods.csv`, `covenant_replay_summary.csv`)

- **Rolled-forward estimate, not a valuation.** Private marks are moved by 0.13 of their listed sector proxy's return since the valuation dates (fitted on 18 past valuation cycles of this vehicle); quoted holdings move one-for-one from the report date.
- Eligible holdings move -0.4% on the estimate. Eligible NAV after concentration limits: 922.9 as reported, 920.8 estimated at 2026-10-06 (-0.2%). LTV on the proposed loan: 15.0% reported, 15.0% estimated.
- Outer bound: if private marks had moved one-for-one with their listed proxies, eligible holdings would have moved -2.0% and eligible NAV 915.4 (-0.8%; the concentration limits absorb part of a fall in the largest names) and LTV 15.1%.
- The market's own haircut: NBPE.L closed at 15.02 on 2026-10-05 against NAV per share of 20.75 at 2026-08-31, a discount of 27.6%. The proposed loan breaches only if the pool falls 62.5%. A discount also reflects fees, borrowing and liquidity, so it is context only.
- Backtest on this vehicle's own history: 18 valuation cycles, 433 company observations. Average error in the quarterly move of the matched holdings: 1.66% carrying stale marks, 5.77% passing the listed move through in full, 1.31% with the fitted factor of 0.13 (in-sample).
- Out of sample (14 cycles, factor fitted on earlier cycles only): 1.48%, against 1.75% for stale marks and 5.56% for full pass-through on the same cycles. Correlation with the proxy is 0.59 at portfolio level and 0.09 company by company.
- Robustness (`backtest_robustness.csv`): repeated on 3 different sets of reporting months, the fitted factor ranges from 0.09 to 0.13 and the estimate beat carrying stale marks on 2 of 3 sets of reporting months, so it is not a reliable improvement at this horizon. Full pass-through was the worst option every time (error 5.2% to 6.1%). Read the estimate as a direction check on the pool, not as a number to lend against.

Covenant replay: a loan fixed at the 2022-02-28 report and never repaid, tracked to 2026-08-31:

| Opening LTV | Peak LTV, reported | Peak LTV, estimated | Peak LTV, full pass-through | First sweep (full pass-through) | Any breach |
|---|---|---|---|---|---|
| 15% | 15.7% (2022-09-30) | 15.8% | 18.2% (2022-06-30) | none | none |
| 20% | 21.0% (2022-09-30) | 21.0% | 24.3% (2022-06-30) | none | none |
| 25% | 26.2% (2022-09-30) | 26.3% | 30.4% (2022-06-30) | 2022-06-30 | none |

## 7. Changes since the previous report (`changes.csv`, `changes_sectors.csv`)

From 2026-07-31 to 2026-08-31:

- Published holdings 1,025.1 to 1,051.2; names held in both months moved 2.5%. NAV per share 27.66 to 28.13.
- Entered: none. Left: none.
- Moves of 15% or more: Technology Company #1 (undisclosed, matched by label) 14.9 to 26.4 (+77.2%); AutoStore 26.1 to 36.2 (+38.7%); Infra Group 13.8 to 16.5 (+19.6%).
- Watchlist: Action +1.0%; Solenis +0.0%; OneMonroe +0.0%; Osaic +2.7%.
- Top five share of published value 31.1% to 30.5%.
- Vehicle liquidity: cash 12 to 7; undrawn line 175 to 135; investment level 112 to 115.

## 8. Data-quality findings (`findings.csv`)

0 errors, 19 warnings, 20 notes. Nothing was corrected; these are reported as found.

- **Q01** (warn, 3): Holdings do not sum to the publisher's own total row. NBPE 2023-03-31: rows 939.9 vs stated 923.1 (difference +16.8); NBPE 2023-04-30: rows 957.4 vs stated 939.6 (difference +17.8); NBPE 2023-08-31: rows 962.6 vs stated 943.6 (difference +19.0)
- **Q02** (warn, 3): Holdings' percentages do not sum to the stated share of the portfolio. NBPE 2023-03-31: rows 67.4% vs stated 66.1%; NBPE 2023-04-30: rows 68.4% vs stated 67.1%; NBPE 2023-08-31: rows 68.3% vs stated 66.9%
- **R02** (warn, 1): Cash received does not tie: previous year-to-date plus this month's cash is not this report's year-to-date. NBPE 2025-05-31: 53 + 8 = 61 vs stated 66 (difference +5)
- **T04** (warn, 8): Extreme net IRR; typical of a very young fund and not a track record. Forbion Growth Opportunities Fund II Cooperatief U.A.: 700.9%, vintage 2023; JSC Capital Partners, L.P.: 101.3%, vintage 2024; LS Investments C, L.P.: 137.7%, vintage 2024 ...
- **T06** (warn, 1): No cash paid in; multiples are undefined. NM Pacific Parallel Series, L.P. (Series B): cash in 0, value 5,165,367
- **T07** (warn, 3): Cash paid in is a multiple of the stated commitment; the commitment figure is not comparable (recycling, or a partial figure). Blackstone Capital Partners V L.P.: cash in 794,822,847 vs committed 38,400,000 (20.7x); CVC Capital Partners VIII (A) L.P.: cash in 766,911,601 vs committed 99,010,624 (7.7x); Green Equity Investors VIII, L.P.: cash in 571,429,840 vs committed 119,970,601 (4.8x)

## 9. Limits

- The collateral is a listed vehicle's published top holdings, not a private fund asking for a loan. No fund documents, covenants in place, company financials or valuation reports were seen.
- The vehicle has its own credit facility; ranking against it is not modelled.
- Sponsor records come from one investor (CalPERS), active funds only, with interim values. That is a biased sample, not a market benchmark.
- The roll-forward is an estimate from listed sector funds. Published fair-value changes also contain follow-on investments, part-realisations and currency moves, which the backtest cannot separate.
- Thresholds, margins, sweep shares and concentration limits are assumptions set in `configs/facility.yaml`. The exit pace is the whole portfolio's, from the publisher's statements of cash received; applying it to the eligible pool, and to the next four years, is an assumption.
- Full list: `docs/limitations.md`.
