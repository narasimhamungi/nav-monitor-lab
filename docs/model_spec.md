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
- proceeds X = N x pace x m / 4, where m is the drought multiplier while it applies, else 1; N falls by X;
- interest I = L x (base rate + margin) / 4; proceeds pay it first; any unpaid part is added to L;
- principal repaid = min(L, (X - interest paid) x sweep share), where the sweep share is `sweep_share_above_trigger`
  if s is at or above the sweep LTV and `sweep_share_below_trigger` otherwise.
A day-one markdown multiplies the starting N by (1 - markdown). Breakeven pace is the lowest pace, rounded up
to 0.1 of a point, at which the balance at maturity is zero.

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

**D-4 Verdict.** Decline if any blocker; proceed with conditions if any condition; otherwise proceed.
