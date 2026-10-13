# Decisions log

| ID | Decision | Why | Alternative rejected |
|---|---|---|---|
| D-01 | Collateral source is NBPE, not HVPE or Pantheon | NBPE publishes 30 holdings with fair values each month, about 80% of its portfolio. HVPE's monthly update has no holdings; PIN's lists five names by percentage | Sizing a loan against a handful of names worth under 10% of a fund of funds |
| D-02 | Private debt is out of scope | CalPERS shows "N/M" on 60 of 66 private debt lines and 0.1% on the rest | Ranking managers on numbers the publisher calls not meaningful. Route if wanted: SEC BDC data sets, which give loan-level schedules of investments |
| D-03 | Headline sponsor measure is capital returned (DPI) ranked within vintage year, not IRR | A lender is repaid from distributions; the publisher itself warns against interim IRRs; ranking within a vintage stops young funds being marked down for being young | Absolute DPI thresholds, which mark 2018 to 2020 funds down for their age |
| D-04 | fund-finance-lab is a pinned dependency, not copied or modified | One model, one place. Pinned to commit `d771874` because the repository has no release tag | Copying `nav_facility.py` into this repository |
| D-05 | Sector scenarios and exit-based repayment live here, not in fund-finance-lab | They need sector labels and market data that fund-finance-lab does not have, and its public functions were enough to build on | Changing a published, tested repository to suit this one |
| D-06 | Analysis never touches the network; only `refresh` does | A memo must be reproducible from files with known hashes | Fetching inside the analysis |
| D-07 | Raw downloads are cached but not committed; normalised figures and the manifest are | Figures are facts with a recorded source; whole pages belong to their publishers | Committing raw HTML |
| D-08 | Findings are reported, never fixed | The three NBPE months that do not tie to their own totals are information a reader needs | Rescaling rows to match totals |
| D-09 | The recommendation is rules with thresholds in config, and no generated prose | Every sentence can be traced to a number and a rule a reader can change | A written opinion |
| D-10 | Undisclosed holdings are excluded from the pool | They cannot be diligenced from public data | Including them at a haircut invented for the purpose |
| D-11 | Holdings outside the published table get no credit | Nothing is known about them | Scaling the pool up to the whole portfolio |
| D-12 | The roll-forward's pass-through is fitted on the vehicle's own history, and the memo reports it is not a reliable improvement | An untested estimate would be a guess. Testing it on three sets of reporting months showed the edge over stale marks is not robust; full pass-through is robustly the worst option | Reporting only the single run on which the estimate looked good |
| D-13 | Sector ETFs stand in for sector indices | Index levels are licensed; ETF prices are not | Index data |
| D-14 | Stooq dropped | CSV downloads answered "Access denied" on 2026-10-07 | Building on a source that already refuses |
| D-15 | Standard library for HTTP and HTML; PyYAML and openpyxl are the only third-party packages | Fewer moving parts on a new Python version; fund-finance-lab has none either | requests, BeautifulSoup, pandas |
| D-16 | Company renames are handled by a hand-entered alias map | Five companies renamed in 55 months, each visible in the tables; a fuzzy matcher would be wrong silently | Automatic matching |
| D-17 | The scheduled workflow ships manual-only | Whether the sources answer GitHub's servers is untested | Shipping a schedule that may fail every morning |
| D-18 | Named nav-monitor-lab, not a "diligence" lab | It underwrites and monitors. It does not do manager due diligence, and the name should not claim it | A name that oversells |
| D-19 | The base exit pace is calibrated from cash the vehicle reports receiving, and the 15% assumption is kept only as a labelled sensitivity | Repayment from exits decided the headline loan, and it rested on a number chosen by hand. Pace = cash received / average portfolio fair value over the window, a year; the denominator is portfolio fair value because that is what the model applies the pace to. Windows of 12 and 24 months and all months are shown; the base case is the lowest, a rule set in `configs/facility.yaml` before the figures were computed. The recommendation moved from 20% ($184.6m) to 15% ($138.4m). No covenant, threshold or window was changed to hold the old result | Keeping 15% because the latest 12 months (15.9%) happen to support it; choosing the window after seeing the answer |
| D-20 | Only cash received is read; announced, pending and pro forma figures are never read; accepted wordings live in the vehicle config | A lender is repaid from cash. The publisher's "announced" totals include deals that had not paid, and its wording changes from year to year (21 accepted wordings are listed). A wording that is not on the list is skipped and reported, never guessed | Reading any dollar figure near the word "realisations"; one loose pattern |
| D-21 | A report's own figures are never used to fill another report's gap by interpolation | 8 of 55 reports state no cash received. The running total simply resumes at the next stated figure, and a window that would have to start in a gap is not computed | Spreading a later total evenly across missing months |

## Open questions

- Should the pool include holdings at a haircut once names are obtained under NDA? Needs a real data room.
- Is "lowest of the windows" the right base rule? It is conservative and it was fixed in advance, but a lender
  might prefer the long-run figure as base and the lowest as a stress. The rule is one word in the config.
- Should the exit pace be measured on the eligible names only? The reports name the companies behind most
  exits, but not the cash from each.
- Is a second investor's table worth adding to raise sponsor coverage above 17%? CalSTRS, Oregon and Washington
  State publish comparable tables; none has been checked.
- The field names follow a schedule of investments. They have not been mapped to the ILPA reporting template.
