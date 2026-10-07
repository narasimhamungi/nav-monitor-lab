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
- Exits are a constant share of pool value each quarter. Real exits are lumpy and name-specific.
- **The 15% base exit pace is an assumption and looks optimistic.** NBPE's April 2026 announcement reports $28m
  of realisations in the first four months of 2026. Against a portfolio of about $1.26bn that is roughly 7% a
  year. At 10% the proposed loan leaves 56.1 unpaid at maturity; at 5%, 133.8. Realisations are not yet parsed
  from the announcements, so the pace is not calibrated to the vehicle.
- One sweep percentage below the trigger and 100% above it. No scheduled amortisation, fees, hedging or
  maturity extension.
- The covenant replay holds the loan constant with no repayments, which overstates LTV as holdings are sold.

## Data and operations
- Monthly holdings, quarterly track records with about a two-quarter lag, daily prices and rates. Not a live feed.
- Live fetching has run once (2026-10-07). It has not yet picked up a newly published report, and the
  scheduled workflow has never run.
- The Yahoo chart endpoint is unofficial and unlicensed. It can change or block without notice.
- A change in a publisher's page layout stops that source with an error; it does not silently return stale data.
- The Excel file is a values export, not a formula model.
