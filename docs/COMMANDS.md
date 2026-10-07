# Commands

PowerShell, from the repository root. Lines starting `#` are comments.

## 1. Unpack and install (once)

```powershell
# Unpack wherever you keep projects; this example uses N:\AAA Projects
Expand-Archive -Force "$HOME\Downloads\nav-monitor-lab.zip" "N:\AAA Projects"
cd "N:\AAA Projects\nav-monitor-lab"

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[test]"
```

`pip install` fetches fund-finance-lab from GitHub at the pinned commit, so `git` must be on the PATH.
If PowerShell refuses to run `Activate.ps1`, run `Set-ExecutionPolicy -Scope Process RemoteSigned` first.

## 2. Check it works offline

```powershell
pytest -q                                              # expect: 114 passed
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
  Send me the mismatch block.
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

## 5. Put it on GitHub

```powershell
git init -b main
git add .
git status                      # check that .env, .venv and data/raw are NOT listed
git commit -m "nav-monitor-lab v0.1.0: NAV-loan underwriting and monitoring on published PE data"
gh repo create narasimhamungi/nav-monitor-lab --public --source . --push
```

CI runs on the push. To try the scheduled refresh: GitHub > Actions > Refresh > Run workflow.

## 6. Optional: tag fund-finance-lab so the pin is a version, not a commit

```powershell
cd "N:\AAA Projects\Fitch\fund finance lab"
git tag -a v0.4.0 d771874 -m "v0.4.0"
git push origin v0.4.0
```

Then in this repository's `pyproject.toml` replace `@d771874b03d5629af1f3835da3c0e9e846b93264` with `@v0.4.0`
and run `pip install -e ".[test]"` again.

## 7. Analyse a different vehicle or your own file

- Another listed vehicle on the FCA archive with a holdings table: copy `configs/vehicle_nbpe.yaml`, change the
  LEI, headline filter and column headings, then `navmon update --vehicle vehicle_other.yaml`.
- A file from any other source: save it in the layout in `docs/data_dictionary.md`, point `files:` at it, and
  run `navmon run --data <folder>`.
