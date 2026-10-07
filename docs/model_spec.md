# Model specification

Every formula the tool uses, in the order the pipeline applies them. Thresholds are in `configs/`.

## C. Collateral

**C-1 Pool.** Every holding in the published table. A holding is ineligible if its name or sponsor is not
disclosed, it is named in `exclude_names`, or its value is below `min_fair_value`. Holdings outside the
published table are not in the pool.

**C-2 Eligible NAV.** fund-finance-lab `nav_facility.eligible_nav`, unchanged:
1. each eligible holding counts up to `single_asset_cap` x the eligible holdings' total;
2. the `top_n` largest capped values count for at most `top_n_share` of the step-1 total.

**C-3 Concentration.** Shares of the largest 1, 5 and 10 holdings; Herfindahl index H = sum of squared shares;
effective names = 1 / H.

## S. Sizing and stress

**S-1 Loan.** loan = opening LTV x eligible NAV, for each LTV in `opening_ltv_grid`.

**S-2 Uniform drawdown and largest-name loss.** fund-finance-lab `uniform_stress` and `single_name_stress`.
Fall to breach = 1 - loan / (breach LTV x eligible NAV).

**S-3 Sector scenarios.** Each eligible holding's value is multiplied by (1 - shock for its sector); eligible
NAV, LTV and status are then recomputed with C-2. A market-history scenario sets each sector's shock to
pass-through x the largest peak-to-trough fall of that sector's proxy inside the window, on the price
observations available.

**S-4 Repayment from exits.** Quarterly, for tenor x 4 quarters, starting from eligible NAV N and loan L:
- N grows by (1 + g)^(1/4);
- LTV at the start of the quarter s = L / N;
- proceeds X = N x pace x m / 4, where pace is the base exit pace from section E and m is the drought
  multiplier while it applies, else 1; N falls by X;
- interest I = L x (base rate + margin) / 4; proceeds pay it first; any unpaid part is added to L;
- principal repaid = min(L, (X - interest paid) x sweep share), where the sweep share is `sweep_share_above_trigger`
  if s is at or above the sweep LTV and `sweep_share_below_trigger` otherwise.
A day-one markdown multiplies the starting N by (1 - markdown). Breakeven pace is the lowest pace, rounded up
to 0.1 of a point, at which the balance at maturity is zero.

## E. Exit pace

**E-1 What is read.** From each monthly report, three figures where the report states them: cash received
from realisations from 1 January to the report date (year to date), cash received in the report month, and
cash received in the whole previous calendar year. A sentence counts only if it matches one of the wordings in
`configs/vehicle_<name>.yaml` (`live.realisations`) and is dated to the report: a "through <date>" must be the
report date, a named month the report month, a named year the report year. Announced, pending, expected and
pro forma amounts match no wording and are never read. Two different figures for the same thing in one report
are a conflict; neither is used.

**E-2 Running total.** Per report: the stated year-to-date figure; or, if only the month is stated, the
previous report's year-to-date figure plus the month (marked "derived"); otherwise unknown. No gap is filled
by interpolation. A year's total is its December year-to-date figure, or failing that the figure restated in
a later report. The running total since 1 January of the first year is the sum of completed years plus the
current year to date; it is undefined after a year with no total.

**E-3 Reconciliation.** Reported as findings and never corrected: previous year-to-date plus the month's cash
differs from the stated year-to-date by more than `tie_tolerance` (R02); year to date falls within a year
(R03); a December figure differs from the same year's total restated later (R04); a year has no total (R07).
Reports with no figure are listed (R01).

**E-4 Pace.** For a window from month-end t0 to month-end t1:

    pace = (running total at t1 - running total at t0) / average portfolio fair value x 12 / months

- t1 is the latest report, at or before the report being analysed, with a known running total.
- A window of W months starts W months before t1. "all" starts on 31 December before the first year in the
  data, where the running total is zero by definition.
- Portfolio fair value is the whole portfolio's, implied by each report's holdings table (stated total / stated
  share of the portfolio). It is not NAV and not the eligible pool. The average is taken over the month-end
  reports from t0 to the month before t1.
- A window is not computed if the running total is unknown at t0, or if it is shorter than `min_months`.

**E-5 Base case.** Chosen from the computed windows by `base_rule` in `configs/facility.yaml`: `lowest`,
`highest`, `median`, or a named window. If no window can be computed, or calibration is switched off, the base
pace is `exit_pace_per_year` and the memo labels it an assumption (flag P20, condition).

**E-6 Sensitivity.** Every repayment case is also run at `exit_pace_per_year`, the former assumption, and the
sizing tests are applied to those results in the same way. The memo shows both side by side.

Assumptions in E: the whole portfolio's pace applies to the eligible pool; the past pace applies to the loan's
life; cash received from all sources (sales, part-sales, quoted shares, refinancings) is available for repayment.

## R. Roll-forward

**R-1 Proxy.** Each sector label maps to a listed fund in `configs/market.yaml`; unmapped sectors use the default.

**R-2 Valuation dates.** The publisher gives valuation dates for the whole portfolio, not per holding.
Assumption: the bucket dated at the report date is the quoted holdings; the earlier buckets are the private
marks, with weights w_i rescaled to sum to 1.

**R-3 Estimate.** With P(d) the proxy's adjusted close on or before d (no more than `max_price_gap_days` earlier):
- private holding: estimate = reported x (1 + beta x sum_i w_i x (P(T) / P(d_i) - 1));
- quoted holding: estimate = reported x (1 + listed_pass_through x (P(T) / P(report date) - 1)).
T is the latest date every needed proxy has a price. beta is the fitted pass-through from B-2 when the
backtest has run, otherwise the configured assumption. The memo also shows beta = 1 as an outer bound.

**R-4 Discount to NAV.** 1 - share price / NAV per share, using the unadjusted close.

## B. Backtest

**B-1 Observations.** Reports `horizon_months` apart, chained back from the latest without overlap. For each
private, disclosed company in both reports: actual = FV1 / FV0 - 1. Proxy move = I(t1) / I(t0) - 1, where
I(t) = sum_i w_i(t) x P(d_i(t)) over that report's private valuation dates. Left out and counted: quoted
holdings, undisclosed names, and moves beyond `max_abs_move`.

**B-2 Pass-through.** Least squares through the origin weighted by starting fair value:
beta = sum(FV0 x proxy x actual) / sum(FV0 x proxy^2).

**B-3 Error.** For each period, on the matched holdings: actual pool move minus beta x value-weighted proxy
move. Reported as the mean absolute error for beta = 0 (carry stale marks), beta = 1, the in-sample beta, and
a walk-forward beta fitted only on earlier periods (after `min_periods_to_fit` periods).

**B-4 Robustness.** B-1 to B-3 repeated with the chain anchored one and two months earlier. The memo's
statement about the estimate is chosen by counting how many of those the walk-forward estimate won.

**B-5 Covenant replay.** Loan fixed at opening LTV x eligible NAV at the first report, never repaid. At each
later report: LTV on reported eligible NAV, on eligible NAV estimated to that report's own date with the
fitted beta, and with beta = 1.

## T. Track record

**T-1 Fund metrics.** DPI, RVPI, TVPI, age, and rank within vintage year (see `data_dictionary.md`).

**T-2 Manager rating.** Over a manager's seasoned funds that have a vintage peer group:
- insufficient: fewer than `min_seasoned_funds`;
- weak: two or more mature funds whose pooled DPI is below `weak.pooled_mature_dpi_max`, or median DPI rank
  below `weak.median_dpi_rank_max`;
- strong: median DPI rank at or above `strong.median_dpi_rank_min` and, where mature funds exist, pooled
  mature DPI at or above `strong.pooled_mature_dpi_min`;
- adequate: otherwise.
Pooled DPI = sum of cash out / sum of cash in.

**T-3 Overlay.** A holding's sponsor label is split on `/`; each part is looked up in `configs/gp_map.yaml`.
The rating carried is the weakest among the mapped managers that have one. Coverage = share of eligible value
whose sponsor is rated strong, adequate or weak.

## D. Recommendation

**D-1 Candidate tests.** An opening LTV passes if: fall to breach is at least `min_cushion_to_breach`; no
sector scenario breaches; writing off the largest names does not breach; the base repayment case repays by
maturity without breach; the drought case does not breach; the estimated LTV is under the sweep level.

**D-2 Proposed loan.** The highest opening LTV that passes every test.

**D-3 Flags.** One per policy rule in `configs/facility.yaml`, with the observed value. Blocker: data errors,
too few names, no passing candidate. Condition: a policy threshold is crossed. Note: information only.
P18 is a condition when the proposed loan's breakeven pace is above `max_breakeven_share_of_base_pace` x the
base exit pace. P20 records how the base pace was set. P21 is a condition when the last report stating cash
received is more than `max_calibration_lag_months` before the report date.

**D-4 Verdict.** Decline if any blocker; proceed with conditions if any condition; otherwise proceed.
