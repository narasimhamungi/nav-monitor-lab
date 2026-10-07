# Decisions log

| ID | Decision | Why | Alternative rejected |
|---|---|---|---|
| D-01 | Collateral source is NBPE, not HVPE or Pantheon | NBPE publishes 30 holdings with fair values each month, about 80% of its portfolio. HVPE's monthly update has no holdings; PIN's lists five names by percentage | Sizing a loan against a handful of names worth under 10% of a fund of funds |
| D-02 | Private debt is out of scope | CalPERS shows "N/M" on 60 of 66 private debt lines and 0.1% on the rest | Ranking managers on numbers the publisher calls not meaningful. Route if wanted: SEC BDC data sets, which give loan-level schedules of investments |
| D-03 | Headline sponsor measure is capital returned (DPI) ranked within vintage year, not IRR | A lender is repaid from distributions; the publisher itself warns against interim IRRs; ranking within a vintage stops young funds being marked down for being young | Absolute DPI thresholds, which an early version used and which marked 2018 to 2020 funds down for their age |
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
| D-18 | Renamed from nav-diligence-lab to nav-monitor-lab | It underwrites and monitors. It does not do manager due diligence, and the name should not claim it | Keeping a name that oversells |

## Open questions

- Should the pool include holdings at a haircut once names are obtained under NDA? Needs a real data room.
- Is a second investor's table worth adding to raise sponsor coverage above 17%? CalSTRS, Oregon and Washington
  State publish comparable tables; none has been checked.
- The field names follow a schedule of investments. They have not been mapped to the ILPA reporting template.
