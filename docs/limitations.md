# Limitations

## What this is not
- **Not an underwriting of a real facility.** No fund agreement, facility agreement, covenant package, company
  financials, valuation report or management meeting was seen. Loan terms are assumptions.
- **Not a rating, a valuation or advice**, and not any rating agency's methodology.
- **Not manager due diligence.** The sponsor section is a quantitative screen of one investor's public table.

## Collateral
- The pool is a listed vehicle's published top 30 holdings (about 80% of its portfolio). The rest is not
  disclosed and gets no credit.
- The vehicle is a co-investment company with its own credit facility. A new lender's ranking against that
  facility is not modelled; the model assumes a first-ranking claim on the holdings.
- Fair values are the publisher's. Most are one or two quarter-ends old at the report date.
- Company identity across months relies on hand-entered aliases in the vehicle config. A rename that is not in
  the map shows as one company leaving and another entering. Undisclosed names are never matched across months.
- Concentration is a single-name cap and a top-N limit only. No sector, geography or vintage limits.

## Sponsor track records
- One investor (CalPERS), active partnerships only. Exited funds are absent, so the sample leans towards
  managers the investor kept.
- Values are interim. The publisher marks 261 of 485 rows "not meaningful".
- The peer group for ranks is whatever that investor holds in the same vintage year, including venture funds
  and co-investment vehicles. It is not a market benchmark.
- The fund-name-to-manager map covers 229 of 485 funds and about 35% of remaining value. 26 mappings are
  inferred from naming conventions, not stated in the table. Many of the largest lines are custom accounts
  with no manager in the name.
- On the shipped data only 17% of eligible collateral value has a rated sponsor.
- Rating thresholds are this tool's own.

## Market layer
- The roll-forward is an estimate from US sector ETFs applied to a portfolio the publisher describes as 77%
  North America and 23% Europe (April 2026 report). Business services has no sector fund and uses industrials.
- A published fair-value change also contains follow-on investments, part-realisations and currency moves.
  The backtest cannot separate them; it leaves out moves beyond 50% and counts them.
- The valuation-date breakdown is published for the whole portfolio, not per holding. The model assumes the
  bucket dated at the report date is the quoted holdings and spreads the rest across private holdings.
- The fitted pass-through is small (0.09 to 0.13 depending on the reporting months used) and the estimate
  beat stale marks on two of three sets of months. It is a direction check, not a number to lend against.
- 18 quarterly cycles is a short history and contains one rate cycle.
- The shipped price sample is month-end closes plus the last 25 trading days. `navmon refresh` fetches daily
  history.
- The discount to NAV reflects fees, leverage and liquidity as well as doubt about marks.

## Repayment model
- Exits are a constant share of pool value each quarter. Real exits are lumpy and name-specific: monthly cash
  received in the data runs from 0 to 53.
- **The exit pace is calibrated on the past and on the whole portfolio.** It is cash received from realisations
  divided by the fair value of the whole portfolio. The model applies it to the eligible pool (27 named
  holdings) and to the next four years. Both steps are assumptions. Cash received includes sales of quoted
  shares, the run-off of older income investments, part-sales and refinancing proceeds, and holdings outside
  the published top 30.
- The vehicle keeps making new investments, so its portfolio always contains young holdings that are not ready
  to sell. The model's pool is fixed and ages. The measured pace is not corrected for that.
- The pace depends on the window: 15.9% over 12 months, 11.7% over 24, 12.1% since January 2022. The base case
  takes the lowest. Only the 12-month window supports the 20% loan that version 0.1.0 proposed.
- Version 0.1.0 of this file said the 15% assumption "looks optimistic" because the first four months of 2026
  brought in $28m, about 7% a year. Four months was too short to judge: the next three months brought $61m.
- 8 of 55 reports state no cash received, including the latest (31 August 2026), so the windows end one month
  before the holdings. Since April 2026 the publisher has stated the month's cash but not the year to date; the
  running total for those months is the last stated total plus the monthly figures.
- Before mid-2022 the publisher reported announced realisations, which include deals not yet paid. Those are
  not read. The first usable cash figure is May 2022, and the 2022 total (120) is not restated anywhere else.
- Accepted wordings are a list in the vehicle config. A new wording is skipped, and shows up as a report with
  no figure (finding R01), until a line is added for it.
- One sweep percentage below the trigger and 100% above it. No scheduled amortisation, fees, hedging or
  maturity extension.
- The covenant replay holds the loan constant with no repayments, which overstates LTV as holdings are sold.

## Data and operations
- Monthly holdings, quarterly track records with about a two-quarter lag, daily prices and rates. Not a live feed.
- Live fetching has run once (2026-10-07), before the cash-received columns existed. It has not yet picked up
  a newly published report, the live parser has not yet read cash received from the live pages, and the
  scheduled workflow has never run.
- The Yahoo chart endpoint is unofficial and unlicensed. It can change or block without notice.
- A change in a publisher's page layout stops that source with an error; it does not silently return stale data.
- The Excel file is a values export, not a formula model.
