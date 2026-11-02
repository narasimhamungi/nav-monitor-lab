# Commands

PowerShell, from the repository root. Lines starting `#` are comments.

## 1. Install (once)

```powershell
git clone https://github.com/narasimhamungi/nav-monitor-lab.git
cd nav-monitor-lab

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[test]"
```

`pip install` fetches fund-finance-lab from GitHub at the pinned commit, so `git` must be on the PATH.
If PowerShell refuses to run `Activate.ps1`, run `Set-ExecutionPolicy -Scope Process RemoteSigned` first.

## 2. Check it works offline

```powershell
pytest -q                                              # expect: 117 passed
navmon run --data data/sample --out outputs/check      # expect: "Verdict: Proceed with conditions | opening LTV 15%, loan 138.4"
                                                       #         "Exit pace: 11.7% a year, calibrated ... on the former 15% assumption: opening LTV 20%, loan 184.6"
fc.exe outputs\check\memo.md outputs\sample\memo.md    # expect: no differences
```

## 3. First live run

```powershell
navmon check-sources      # one small call per source; expect PASS on four lines, FAIL on Tiingo unless you set a key
navmon refresh            # about 75 requests, paced; takes a minute or two; writes data/live and data/raw
navmon verify-live        # compares the live parse with the shipped sample; expect "AGREE"
navmon run                # uses data/live now that it exists; writes outputs/latest
```

What to do with the results:
- `check-sources` shows a FAIL: the message says which source and why. The rest still work; `refresh` keeps
  going and falls back to the sample file for the failed source, and says so.
- `verify-live` shows differences in holdings: a parser is reading the page differently from the capture.
  The mismatch block names the table and rows.
- `verify-live` says the track record has a different as-of date: CalPERS has published a new quarter. That
  is expected over time, not an error.

## 4. Day to day

```powershell
navmon update                                   # refresh + run in one step
navmon update --only holdings,prices,rates      # skip the CalPERS page
navmon run --as-of 2026-05-31                   # analyse an earlier report
navmon run --as-of 2026-08-31 --compare-to 2026-02-28    # change log against a chosen month
navmon run --out outputs/2026-10 --no-excel
```

Optional Tiingo key (PowerShell, current session only), or put `TIINGO_API_KEY=...` in a `.env` file:

```powershell
$env:TIINGO_API_KEY = "your-key"
```

Then set `plug: tiingo` under `prices: live:` in `configs/market.yaml`.

## 5. Scheduled refresh

GitHub > Actions > Refresh > Run workflow runs `navmon update` on a GitHub-hosted runner. The schedule in
`.github/workflows/refresh.yml` is commented out until a manual run has succeeded (`docs/decisions.md`, D-17).

## 6. Analyse a different vehicle or your own file

- Another listed vehicle on the FCA archive with a holdings table: copy `configs/vehicle_nbpe.yaml`, change the
  LEI, headline filter and column headings, then `navmon update --vehicle vehicle_other.yaml`.
- A file from any other source: save it in the layout in `docs/data_dictionary.md`, point `files:` at it, and
  run `navmon run --data <folder>`.
