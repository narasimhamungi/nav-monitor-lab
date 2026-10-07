"""End to end on the shipped real data, offline."""
import csv
import json
import shutil
from datetime import date

import pytest

from conftest import ROOT, SAMPLE, fixture_text
from navmonitorlab import cli, config, pipeline, refresh, report
from navmonitorlab.net import Fetcher
from navmonitorlab.sources.files import FileHoldings, FileTrackRecord, save_snapshots, save_track_record
from test_sources_real_pages import FakeWeb


def rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def run(tmp_path_factory, monkeypatch_module):
    out = tmp_path_factory.mktemp("out")
    monkeypatch_module.chdir(ROOT)
    assert cli.main(["run", "--data", "data/sample", "--out", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def test_cli_run_writes_every_output(run):
    names = {p.name for p in run.iterdir()}
    assert {"memo.md", "collateral.csv", "sizing_candidates.csv", "stress_scenarios.csv", "runoff.csv", "roll_forward.csv", "backtest_periods.csv",
            "covenant_replay_summary.csv", "changes.csv", "findings.csv", "sponsor_overlay.csv", "track_record_families.csv",
            "recommendation.json", "run_manifest.json", "nav_monitor.xlsx"} <= names
    man = json.loads((run / "run_manifest.json").read_text())
    assert man["snapshot_as_of"] == "2026-08-31" and man["prices_to"] == "2026-10-06" and len(man["inputs_sha256"]) == 5
    assert man["inputs_sha256"] == {k: v["sha256"] for k, v in json.loads((SAMPLE / "manifest.json").read_text())["files"].items()}


def test_same_inputs_give_byte_identical_outputs(run, tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    cli.main(["run", "--data", "data/sample", "--out", str(tmp_path), "--no-excel"])
    for p in run.iterdir():
        if p.suffix in (".md", ".csv") or p.name == "recommendation.json":
            assert p.read_bytes() == (tmp_path / p.name).read_bytes(), p.name


def test_every_headline_figure_in_the_memo_is_in_a_named_output_file(run):
    memo = (run / "memo.md").read_text(encoding="utf-8")
    rec = json.loads((run / "recommendation.json").read_text())
    prop = rec["proposed"]
    cands = {float(r["opening_ltv"]): r for r in rows(run / "sizing_candidates.csv")}
    c = cands[prop["opening_ltv"]]
    summ = {r["item"]: r["value"] for r in rows(run / "pool_summary.csv")}
    assert f"**{rec['verdict']}.** Opening LTV {prop['opening_ltv']:.0%}: a loan of {float(c['loan']):,.1f}" in memo
    assert f"against eligible NAV of {float(summ['eligible_nav_after_limits']):,.1f}" in memo
    assert f"Eligible: {int(float(summ['eligible_names']))} names, {float(summ['eligible_fv']):,.1f}" in memo
    assert f"{float(summ['estimated_eligible_nav_after_limits']):,.1f} estimated at" in memo
    assert f"must realise {float(c['breakeven_exit_pace']):.1%} a year" in memo
    for r in rows(run / "stress_scenarios.csv"):
        if float(r["opening_ltv"]) == prop["opening_ltv"]:
            assert f"| {r['scenario']} | {float(r['pool_fall']):.1%} | {float(r['ltv']):.1%} | {r['status']} |" in memo
    bt = {r["item"]: r["value"] for r in rows(run / "backtest_summary.csv")}
    assert f"{float(bt['mae_walk_forward']):.2%}, against {float(bt['mae_no_adjustment_same_periods']):.2%} for stale marks" in memo
    assert f"{int(float(bt['n_periods']))} valuation cycles, {int(float(bt['n_observations']))} company observations" in memo
    for r in rows(run / "covenant_replay_summary.csv"):
        assert f"| {float(r['opening_ltv']):.0%} | {float(r['peak_ltv_reported']):.1%} ({r['peak_date_reported']})" in memo
    top = [r for r in rows(run / "collateral.csv") if r["eligible"] == "True"][0]
    assert f"| {top['company']} | {top['sponsor']} | {top['sector']} | {float(top['fair_value']):,.1f} |" in memo
    for f in rec["flags"]:
        assert f["observed"] in memo
    assert report.DISCLAIMER in memo and "estimate, not a valuation" in memo.lower()


def test_real_run_result(cfg):
    r = pipeline.analyse(cfg, SAMPLE)
    assert r["verdict"] == "Proceed with conditions" and r["proposed"]["opening_ltv"] == 0.20
    assert {f.code for f in r["flags"] if f.severity == "condition"} == {"P13", "P15", "P18"}
    assert r["finding_counts"].get("error", 0) == 0 and r["unreconciled_all"] == ["2023-03-31", "2023-04-30", "2023-08-31"]
    assert r["base_rate"] == 3.89 and r["all_in_rate"] == pytest.approx(10.39) and round(r["discount"]["discount"], 3) == 0.276


def test_an_earlier_report_can_be_analysed_and_compared(cfg):
    r = pipeline.analyse(cfg, SAMPLE, as_of=date(2026, 5, 31), compare_to=date(2026, 4, 30))
    assert r["snapshot"].as_of == date(2026, 5, 31) and r["history_n"] == 52
    osaic = next(x for x in r["changes"]["rows"] if x["company"] == "Osaic")
    assert (osaic["fv_prev"], osaic["fv_cur"]) == (69.8, 42.4) and any(m["company"] == "Osaic" for m in r["changes"]["movers"])
    dup = [f for f in r["findings"] if f.code == "Q04" and "2026-05-31" in f.scope]
    assert dup and "Undisclosed Technology Company*" in dup[0].observed
    with pytest.raises(ValueError, match="no snapshot dated"):
        pipeline.analyse(cfg, SAMPLE, as_of=date(2026, 5, 30))


def test_without_market_data_the_memo_says_so_and_adds_a_condition(cfg, tmp_path):
    for n in ("holdings_nbpe.csv", "snapshots_nbpe.csv", "track_record_calpers.csv"):
        shutil.copyfile(SAMPLE / n, tmp_path / n)
    r = pipeline.analyse(cfg, tmp_path)
    assert not r["roll_forward"]["ran"] and r["backtest"] is None and r["all_in_rate"] == 6.5
    assert "P19" in {f.code for f in r["flags"]} and any(f.code == "S01" for f in r["findings"])
    memo = report.build_memo(r)
    assert "No market data in this run." in memo and "Not run: no usable price history" in memo
    assert len(r["scenario_rows"][0.2]) == 4            # the market-history scenario is skipped, the configured ones still run


def test_refresh_through_fake_web_then_verify(cfg, tmp_path):
    live = tmp_path / "live"
    rep = refresh.refresh(cfg, live, fetcher=Fetcher(transport=FakeWeb(), cache_dir=tmp_path / "raw"), today=date(2026, 10, 7))
    assert {k: v["status"] for k, v in rep["steps"].items()} == {"holdings": "OK", "track": "OK", "prices": "OK", "rates": "OK"}
    assert rep["steps"]["holdings"]["latest"] == "2026-04-30" and rep["steps"]["track"]["funds"] == 15
    man = json.loads((live / "manifest.json").read_text())
    assert len(man["files_sha256"]) == 5 and all(len(x["sha256"]) == 64 for x in man["fetches"])
    assert len(list((tmp_path / "raw").iterdir())) >= 4          # raw downloads are cached
    snaps = FileHoldings(live / "holdings_nbpe.csv", live / "snapshots_nbpe.csv").load()
    assert len(snaps) == 1 and snaps[0].stated_total_fv == 1014.8
    v = refresh.verify_live(cfg, live, SAMPLE)
    assert v["holdings"]["overlapping_snapshots"] == 1 and v["holdings"]["mismatches"] == []
    assert v["track_record"]["same_as_of"] and v["track_record"]["funds_live"] == 15           # the excerpt has 15 of the 485 funds
    # the stand-in web serves XLK's real response for every symbol, so only XLK can agree with the sample
    assert v["prices"]["compared_closes"] > 0 and all(e["symbol"] != "XLK" for e in v["prices"]["examples"])


def test_verify_live_detects_a_changed_number(cfg, tmp_path):
    live = tmp_path / "live"
    shutil.copytree(SAMPLE, live)
    assert refresh.verify_live(cfg, live, SAMPLE)["agree"]
    snaps = FileHoldings(live / "holdings_nbpe.csv", live / "snapshots_nbpe.csv").load()
    h = snaps[-1].holdings[0]
    snaps[-1].holdings[0] = type(h)(h.company, h.vintage, h.sponsor, h.sector, h.fair_value + 1.0, h.pct_of_fv)
    save_snapshots(snaps, live / "holdings_nbpe.csv", live / "snapshots_nbpe.csv")
    v = refresh.verify_live(cfg, live, SAMPLE)
    assert not v["agree"] and v["holdings"]["mismatches"][0]["as_of"] == "2026-08-31"


def test_a_failed_source_is_reported_and_never_overwrites_good_data(cfg, tmp_path):
    live = tmp_path / "live"
    web = FakeWeb(fail=("calpers.ca.gov", "finance.yahoo.com"))
    rep = refresh.refresh(cfg, live, fetcher=Fetcher(transport=web), sample_dir=SAMPLE, today=date(2026, 10, 7))
    assert rep["steps"]["track"]["status"] == "FAILED" and rep["steps"]["prices"]["status"] == "FAILED" and rep["steps"]["rates"]["status"] == "OK"
    assert set(rep["seeded_from_sample"]) == {"track_record_calpers.csv", "prices.csv"}
    assert (live / "track_record_calpers.csv").read_bytes() == (SAMPLE / "track_record_calpers.csv").read_bytes()
    before = (live / "track_record_calpers.csv").read_bytes()
    rep2 = refresh.refresh(cfg, live, fetcher=Fetcher(transport=web), sample_dir=SAMPLE, today=date(2026, 10, 8))
    assert rep2["steps"]["track"]["kept_existing"] and (live / "track_record_calpers.csv").read_bytes() == before


def test_file_round_trips(snaps, track, tmp_path):
    save_snapshots(snaps, tmp_path / "h.csv", tmp_path / "s.csv")
    again = FileHoldings(tmp_path / "h.csv", tmp_path / "s.csv").load()
    assert [(s.as_of, s.holdings, s.valuation_mix, s.stated_total_fv, s.cash_m) for s in again] == \
           [(s.as_of, s.holdings, s.valuation_mix, s.stated_total_fv, s.cash_m) for s in snaps]
    save_track_record(track, tmp_path / "t.csv")
    assert FileTrackRecord(tmp_path / "t.csv").load().funds == track.funds


def test_check_sources_reports_pass_and_fail_per_source(cfg):
    out = {r["source"]: r for r in refresh.check_sources(cfg, Fetcher(transport=FakeWeb(fail=("fred.stlouisfed.org",))), today=date(2026, 10, 7))}
    assert out["holdings: fca_nsm"]["status"] == "PASS" and "30 holdings" in out["holdings: fca_nsm"]["detail"]
    assert out["track record: calpers_html"]["status"] == "PASS" and out["prices: yahoo_chart"]["status"] == "PASS"
    assert out["rates: fred_csv"]["status"] == "FAIL"


def test_unknown_plug_name_is_a_clear_error(cfg):
    from navmonitorlab.sources import price_source
    with pytest.raises(ValueError, match="unknown price plug 'bloomberg'; available: file, yahoo_chart, tiingo"):
        price_source({"plug": "bloomberg"})


def test_cli_update_refreshes_then_runs(tmp_path, monkeypatch, capsys):
    """`navmon update` end to end, with the network replaced by the captured payloads."""
    from navmonitorlab import net
    web = FakeWeb()
    monkeypatch.setattr(net.Fetcher, "_urllib", lambda self, url, data, headers: web(url, data, headers))
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    monkeypatch.chdir(ROOT)
    live, out = tmp_path / "live", tmp_path / "out"
    rc = cli.main(["update", "--data", str(live), "--cache", str(tmp_path / "raw"), "--out", str(out), "--no-excel"])
    printed = capsys.readouterr().out
    assert rc == 0 and "holdings  OK" in printed and "Verdict:" in printed
    assert (out / "memo.md").exists() and "Holdings as of 2026-04-30" in (out / "memo.md").read_text(encoding="utf-8")
    assert cli.main(["run", "--data", str(tmp_path / "nowhere"), "--out", str(out)]) == 2      # a missing data directory is a clean error


def test_cli_check_sources_and_verify_live_exit_codes(tmp_path, monkeypatch, capsys):
    from navmonitorlab import net
    web = FakeWeb()
    monkeypatch.setattr(net.Fetcher, "_urllib", lambda self, url, data, headers: web(url, data, headers))
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    monkeypatch.chdir(ROOT)
    assert cli.main(["check-sources"]) == 0                     # Tiingo fails without a key and is not counted against the run
    text = capsys.readouterr().out
    assert text.count("PASS") == 4 and "FAIL  prices: tiingo" in text
    assert cli.main(["verify-live", "--live", "data/sample", "--sample", "data/sample"]) == 0
