# Sources

## What professionals use, and the free stand-in here

| Need | Professional source | Free source used | Checked on 2026-10-07 |
|---|---|---|---|
| Holdings and fair values | The borrower's quarterly reports and data room | A listed vehicle's monthly NAV announcements on the FCA National Storage Mechanism | 55 monthly NBPE reports read; request and response shapes captured |
| Manager track records | Preqin, PitchBook, MSCI Burgiss | CalPERS Private Equity Program fund performance table | 485 rows read; tied to five column sums on the page |
| Prices | Bloomberg, LSEG, FactSet, S&P Capital IQ | Yahoo Finance chart endpoint (unofficial) | Real response captured for nine symbols |
| Reference rates | The same terminals | FRED CSV download (SOFR, SONIA) | Real response captured |
| Realisation proceeds | The borrower's cash flow reporting and distribution notices | Statements of cash received in the same monthly NAV announcements | 55 reports read; 47 state a figure |
| Lending terms | The lender's own credit policy | Published rating-agency commentary, as summarised by Sidley (Aug 2025): initial LTV 10% to 30%, maximum about 40% | Read in summary only; the agencies' full criteria were not read |

Tried and dropped: **Stooq**. Its CSV download answered "Access denied" on 2026-10-07.

A NAV lender's core input is not a data vendor at all. It is the borrower's own reporting. That is why the
file plug matters more than any vendor plug: a fund report saved in the layout in `data_dictionary.md` runs
through the same analysis.

## Plugs

| Socket | `plug:` name | Class | Network | Tested against |
|---|---|---|---|---|
| Holdings | `file` | `sources.files.FileHoldings` | no | shipped sample |
| Holdings | `fca_nsm` | `sources.fca_nsm.FcaNsmHoldings` | yes | real announcement excerpt and trimmed real search response |
| Track record | `file` | `sources.files.FileTrackRecord` | no | shipped sample |
| Track record | `calpers_html` | `sources.calpers.CalpersTrackRecord` | yes | real page excerpt (15 of 485 rows, real markup) |
| Prices | `file` | `sources.files.FilePrices` | no | shipped sample |
| Prices | `yahoo_chart` | `sources.market.YahooChartPrices` | yes | real response |
| Prices | `tiingo` | `sources.market.TiingoPrices` | yes, needs `TIINGO_API_KEY` | **synthetic payload only** |
| Rates | `file` | `sources.files.FileRates` | no | shipped sample |
| Rates | `fred_csv` | `sources.market.FredRates` | yes | real rows |

The first live run was on 2026-10-07 from a Windows machine: FCA NSM, CalPERS, Yahoo and FRED all
answered. Tiingo has not been run.

## Adding a plug (for example a licensed feed)

1. Write a class with the socket's one method (`sources/base.py`). For prices that is
   `history(symbol, start, end) -> list[(date, adjusted close, close)]`.
2. Add its name to the tuple and the factory function in `sources/__init__.py`.
3. Set `plug: your_name` in the config.
4. Add a test that feeds it a recorded response.

Nothing else changes, because the analysis reads normalised files written by `navmon refresh`. Until a plug
has been run against the real service, describe the tool as source-agnostic, not as compatible with that vendor.

## How the shipped sample was captured

The build environment's shell could not reach the publishers' sites. The pages were opened in a browser on
2026-10-07, read with a script running in the page, and the script's output was written to the sample files by
program. No figure was typed by hand. Checks:

- **CalPERS**: row count, the sums of vintage year, commitment, cash in, cash out and total value, and the
  number of footnoted rows were computed on the live page and are stored in `data/sample/manifest.json`.
  `tests/test_sample_data.py` checks the file against them. Every published multiple also recomputes from
  value and cash in.
- **NBPE**: each monthly table is checked against the publisher's own total row. 52 of 55 tie within 0.5.
  The reports for 31 March, 30 April and 31 August 2023 do not: their rows sum to 16.8, 17.8 and 19.0 more
  than the stated total. Those are reported as findings and left as published.
- **Prices and rates**: no independent tie-out exists. `navmon verify-live` compares closes with a fresh fetch.
- **NBPE cash received** (added in version 0.2.0): every line of each report that mentions realisations,
  proceeds or exits was captured as text (`tests/fixtures/nbpe_realisation_lines.json`). Three readings agree
  on all 55 reports: the Python reader on those lines; the same wordings run in the browser over each report's
  full text, which also confirmed that no sentence outside the captured lines matches; and a reading by eye
  recorded in `tests/test_realisations.py`. Tie-outs on the publisher's own numbers: the December figures for
  2023, 2024 and 2025 (171, 179, 180) equal the totals restated in the following annual results
  announcements; where a report states both the month and the year to date, they tie to the previous report
  in 10 of 11 cases (one of them within the publisher's $1m rounding), and the eleventh (31 May 2025: 53 + 8
  against a stated 66) is reported as finding R02. One
  outside check on the denominator: the 31 May 2024 report calls $122m "approximately 9% of opening portfolio
  value"; against this tool's portfolio value for 31 December 2023 it is 9.2%.
- The live parser's reading of cash received from the live pages has not been compared with the sample yet.
  It is tested on real HTML from seven reports, and a browser script that splits each page into lines by the
  parser's rules (dropping superscripts) found the same figures in the full HTML of all 56 announcements on
  2026-10-07. That script is a stand-in, not the parser. `navmon refresh` then `navmon verify-live` compares
  all 55 with the parser itself.

`navmon verify-live` repeats the comparison with the Python parsers. On 2026-10-07 the two independent readers
agreed on all 55 holdings tables, all 485 funds and all 774 closes, with one exception that was the sample's
error: the 30 September 2023 table prints "Business Services Company" with a superscript footnote "4", and
the browser capture had read the digit as part of the name. The live parser keeps superscripts apart. The
sample row was corrected and the correction is recorded in `data/sample/manifest.json`.

## Observations about the sources

- One announcement matched by the headline filter has no holdings table (13 January 2022, a dividend
  announcement). The parser skips it and reports finding H00; that is expected.
- The CalPERS page prints its header row twice (as a table footer). The parser skips it.
- Its footnote text says funds of vintage 2021 or later are "not meaningful", but the marker appears only on
  vintages 2022 to 2026, and 178 of the 261 marked rows still show an IRR.
- Four Permira fund names end in a digit that looks like a footnote number typed into the name.
- The NBPE announcements write their table header with ordinary cells, not header cells, so the table is found
  by its column headings. One heading has had three spellings: "Fair Value" to September 2022, "Fair Value($m)"
  to December 2022, "Fair Value ($m)" since.
- NBPE renamed several companies over the period and relabelled sectors in October 2022. The maps in
  `configs/vehicle_nbpe.yaml` record each one.
- NBPE's realisation reporting changes shape. Until early 2022 the headline figure is "announced"
  realisations, which include deals not yet paid; cash received sits in a footnote from May 2022 and moves
  into the main text during 2023. From May 2026 the reports give the month's cash and a total of announced
  realisations, but no cash year to date. The 31 October 2025 report gives "$64 million of realisations in
  October", of which $29m is described as cash and $34m as deals closed; the next report's cash total (157)
  shows that not all of it had been received, so the October figure is not read.

## Use and redistribution

- The FCA archive and the CalPERS page are official public disclosures. The normalised figures in
  `data/sample/` are facts taken from them, with each source URL recorded.
- Raw downloads are cached in `data/raw/`, which is not committed. The commit carries the manifest: URL, time,
  size and sha256 of everything fetched.
- News aggregators that republish the same announcements restrict redistribution. This tool does not use them.
- Yahoo's endpoint has no licence for redistribution or commercial use. Treat `prices.csv` as a personal
  research sample.
