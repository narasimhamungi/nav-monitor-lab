from datetime import date

import pytest

from navmonitorlab import backtest, rollforward
from navmonitorlab.collateral import PoolAsset
from navmonitorlab.schema import Holding, Snapshot
from navmonitorlab.sources import PriceBook

MARKET = {"sector_proxy": {"Tech": "TEC", "Fin": "FIN"}, "default_proxy": "MKT",
          "roll_forward": {"pass_through": 0.5, "listed_pass_through": 1.0, "max_price_gap_days": 10},
          "backtest": {"horizon_months": 3, "min_periods_to_fit": 2, "max_abs_move": 0.5, "replay_opening_ltvs": [0.2]}}
Q = [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)]


def book(levels: dict[str, list[float]], dates=Q) -> PriceBook:
    b = PriceBook()
    for sym, vals in levels.items():
        b.add(sym, [(d, v, v) for d, v in zip(dates, vals)])
    return b


def test_private_and_quoted_holdings_roll_forward_differently():
    b = book({"TEC": [100, 100, 100, 100, 100, 120], "FIN": [50, 50, 50, 50, 55, 44]}, Q)
    b.add("TEC", b.rows("TEC") + [(date(2026, 8, 31), 132, 132)])
    b.add("FIN", b.rows("FIN") + [(date(2026, 8, 31), 44, 44)])
    snap = Snapshot("V", date(2026, 6, 30), None, "", "USD", "m", [], valuation_mix=[(date(2026, 6, 30), 0.1), (date(2026, 3, 31), 0.9)])
    pool = [PoolAsset("P", "P", "GP", "Tech", 2020, 100.0, False, True, ""), PoolAsset("L", "L (NYSE: L)", "GP", "Tech", 2020, 50.0, True, True, ""),
            PoolAsset("F", "F", "GP", "Fin", 2020, 80.0, False, True, "")]
    r = rollforward.roll_forward(snap, pool, b, MARKET, pass_through=0.5)
    by = {x["key"]: x for x in r["rows"]}
    assert r["ran"] and r["to"] == date(2026, 8, 31)
    assert by["P"]["proxy_return"] == pytest.approx(0.32) and by["P"]["estimated_fv"] == pytest.approx(100 * (1 + 0.5 * 0.32))   # from the March mark
    assert by["L"]["proxy_return"] == pytest.approx(0.10) and by["L"]["estimated_fv"] == pytest.approx(55.0)                 # from the report date, one for one
    assert by["F"]["estimated_fv"] == pytest.approx(80 * (1 + 0.5 * (44 / 55 - 1)))
    assert r["weighted_private_mark_age_days"] == (date(2026, 8, 31) - date(2026, 3, 31)).days and r["days_since_report"] == 62


def test_missing_proxy_is_carried_at_reported_value_with_a_finding():
    snap = Snapshot("V", date(2026, 6, 30), None, "", "USD", "m", [], valuation_mix=[(date(2026, 3, 31), 1.0)])
    pool = [PoolAsset("P", "P", "GP", "Tech", 2020, 100.0, False, True, ""), PoolAsset("O", "O", "GP", "Other", 2020, 10.0, False, True, "")]
    r = rollforward.roll_forward(snap, pool, book({"TEC": [100, 100, 100, 100, 100, 110]}), MARKET, pass_through=1.0)
    by = {x["key"]: x for x in r["rows"]}
    assert by["O"]["estimated_fv"] == 10.0 and by["P"]["estimated_fv"] == pytest.approx(110.0)
    assert {"M01", "M03", "M04"} <= {f.code for f in r["findings"]}


def test_stale_prices_raise_instead_of_passing_as_current():
    b = book({"TEC": [100, 100, 100, 100, 100, 110]})
    with pytest.raises(KeyError, match="more than 10 days"):
        b.asof("TEC", date(2026, 8, 31))
    with pytest.raises(KeyError, match="no price on or before"):
        b.asof("TEC", date(2024, 1, 1))
    snap = Snapshot("V", date(2026, 9, 30), None, "", "USD", "m", [], valuation_mix=[(date(2026, 6, 30), 1.0)])
    r = rollforward.roll_forward(snap, [PoolAsset("P", "P", "GP", "Tech", 2020, 100.0, False, True, "")], b, MARKET, pass_through=1.0)
    assert not r["ran"] and r["findings"][0].code == "M02"


def test_discount_to_nav():
    b = PriceBook(); b.add("V.L", [(date(2026, 6, 30), 1500, 1500), (date(2026, 8, 28), 1400, 1400)])
    snap = Snapshot("V", date(2026, 6, 30), None, "", "USD", "m", [], nav_per_share_gbp=20.0)
    d = rollforward.discount_to_nav(snap, b, {"symbol": "V.L", "price_divisor": 100, "nav_field": "nav_per_share_gbp"})
    assert d["discount"] == pytest.approx(0.30) and d["discount_at_report_date"] == pytest.approx(0.25) and d["price_date"] == "2026-08-28"
    assert rollforward.discount_to_nav(snap, b, None) is None


def synthetic_history(beta: float):
    """Six quarterly reports whose private marks move by exactly beta x the sector move one quarter earlier."""
    tec = [100, 110, 99, 118.8, 106.92, 128.304]
    fin = [50, 45, 49.5, 47.025, 51.7275, 46.55475]
    snaps, a, f = [], 100.0, 60.0
    months = [date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)]
    for i, d in enumerate(months):                       # report at quarter i+1 carries marks struck at quarter i
        if i > 0:
            a *= 1 + beta * (tec[i] / tec[i - 1] - 1)
            f *= 1 + beta * (fin[i] / fin[i - 1] - 1)
        snaps.append(Snapshot("V", d, None, "", "USD", "m", [
            Holding("Acme", 2020, "GP", "Tech", round(a, 6), None), Holding("Bank", 2020, "GP", "Fin", round(f, 6), None),
            Holding("Quoted (NYSE: Q)", 2020, "GP", "Tech", 10.0, None), Holding("Hidden*", 2020, "Not Disclosed", "Tech", 5.0, None)],
            valuation_mix=[(d, 0.1), (Q[i], 0.9)]))
    return snaps, book({"TEC": tec, "FIN": fin})


def test_backtest_recovers_a_known_pass_through():
    snaps, b = synthetic_history(0.3)
    obs, skipped = backtest.observations(snaps, b, {}, MARKET)
    assert len(obs) == 8 and {s["reason"][:6] for s in skipped} == {"quoted", "undisc"}
    acc = backtest.accuracy(obs, min_periods_to_fit=2)
    assert acc["beta_in_sample"] == pytest.approx(0.3, abs=1e-6) and acc["n_periods"] == 4
    assert acc["mae_fitted_in_sample"] == pytest.approx(0.0, abs=1e-6) and acc["mae_walk_forward"] == pytest.approx(0.0, abs=1e-6)
    assert acc["mae_full_pass_through"] > acc["mae_no_adjustment"] > 0 and acc["n_walk_forward"] == 2


def test_large_moves_are_left_out_and_counted():
    snaps, b = synthetic_history(0.3)
    snaps[-1].holdings[0] = Holding("Acme", 2020, "GP", "Tech", snaps[-2].holdings[0].fair_value * 2, None)
    obs, skipped = backtest.observations(snaps, b, {}, MARKET)
    assert len(obs) == 7 and any("exceeds the size limit" in s["reason"] and s["company"] == "Acme" for s in skipped)


def test_real_history_backtest_headline(snaps, prices, cfg):
    acc = backtest.run(snaps, prices, cfg)["accuracy"]
    assert acc["n_periods"] == 18 and acc["n_observations"] == 433 and acc["n_walk_forward"] == 14
    assert 0.10 < acc["beta_in_sample"] < 0.16
    assert acc["mae_walk_forward"] < acc["mae_no_adjustment_same_periods"] < acc["mae_full_pass_through_same_periods"]
    assert acc["mae_full_pass_through"] > 3 * acc["mae_no_adjustment"]          # passing listed moves through in full is the worst option


def test_covenant_replay_on_real_history(snaps, prices, cfg):
    rep = backtest.covenant_replay(snaps, prices, cfg, pass_through=0.13)
    s = {x["opening_ltv"]: x for x in rep["summary"]}
    assert len(rep["rows"]) == 55 * 3 and s[0.2]["first_reported_sweep"] == "" and s[0.2]["first_full_breach"] == ""
    assert s[0.25]["first_full_sweep"] == "2022-06-30" and s[0.25]["first_reported_sweep"] == ""
    assert s[0.25]["peak_ltv_reported"] < s[0.25]["peak_ltv_full"]


def test_robustness_repeats_the_test_on_every_set_of_reporting_months(snaps, prices, cfg):
    bt = backtest.run(snaps, prices, cfg)
    rob = bt["robustness"]
    assert [r["chain_ends"] for r in rob] == ["2026-08-31", "2026-07-31", "2026-06-30"]
    assert all(r["mae_full_pass_through"] > 2.5 * r["mae_no_adjustment"] for r in rob)      # robust: full pass-through is always worst
    assert all(0.05 < r["beta_in_sample"] < 0.20 for r in rob)                              # robust: the factor is small
    assert [r["estimate_beats_stale_marks"] for r in rob] == [True, True, False]             # NOT robust: the estimate's edge
    assert bt["verdict"].startswith("the estimate beat carrying stale marks on 2 of 3") and "not a reliable improvement" in bt["verdict"]


def test_backtest_verdict_wording_is_chosen_by_counting():
    row = lambda beats: {"mae_walk_forward": 0.01, "estimate_beats_stale_marks": beats}
    assert "on every set" in backtest.verdict([row(True), row(True)])
    assert "did not beat" in backtest.verdict([row(False), row(False)])
    assert "1 of 2" in backtest.verdict([row(True), row(False)])
    assert "too little history" in backtest.verdict([{"mae_walk_forward": None, "estimate_beats_stale_marks": False}])
