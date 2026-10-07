import math
from datetime import date

import pytest
from fundfinancelab import nav_facility as nf

from navmonitorlab import collateral, sizing
from navmonitorlab.collateral import PoolAsset
from navmonitorlab.schema import Holding, Snapshot
from navmonitorlab.sources import PriceBook

COV = {"ltv_breach": 0.40, "ltv_sweep": 0.30, "ltv_target": 0.25, "single_asset_cap": 0.20, "top_n": 3, "top_n_share": 0.50, "min_assets": 5}
SIZ = {"opening_ltv_grid": [0.10, 0.20], "drawdown_grid": [0.0, 0.25, 0.50], "min_cushion_to_breach": 0.40, "single_name_loss": 1.0, "single_names": 2}


def pool(values, sectors=None):
    return [PoolAsset(f"N{i}", f"N{i}", "GP", (sectors or ["Tech"] * len(values))[i], 2020, v, False, True, "") for i, v in enumerate(values)]


POOL = pool([300, 200, 150, 120, 100, 80, 50], ["Tech", "Tech", "Fin", "Fin", "Ind", "Ind", "Ind"])


def test_pool_excludes_undisclosed_names_and_keeps_the_reason():
    s = Snapshot("V", date(2026, 6, 30), None, "", "USD", "m", [
        Holding("Open Co", 2020, "GP", "Tech", 50.0, 0.05), Holding("Business Services Company*", 2017, "Not Disclosed", "Biz", 40.0, 0.04),
        Holding("GFL (NYSE: GFL)", 2018, "BC", "Biz", 10.0, 0.01), Holding("Small Co", 2020, "GP", "Tech", 1.0, 0.001)], 101.0, 0.101)
    p = collateral.build_pool(s, {"company_aliases": {}}, {"exclude_undisclosed": True, "min_fair_value": 5.0})
    assert [(a.key, a.eligible) for a in p] == [("Open Co", True), ("Business Services Company", False), ("GFL", True), ("Small Co", False)]
    assert p[1].reason == "name or sponsor not disclosed" and p[2].listed and "minimum" in p[3].reason
    summ = collateral.pool_summary(s, p)
    assert summ["eligible_fv"] == 60.0 and summ["excluded_fv"] == 41.0 and summ["implied_portfolio_fv"] == pytest.approx(1000.0)
    assert summ["listed_share_of_eligible"] == pytest.approx(10 / 60)


def test_eligible_nav_is_fund_finance_labs_number():
    assets = sizing.to_assets(POOL)
    assert sizing.eligible_nav(assets, COV) == nf.eligible_nav(assets, 0.20, 3, 0.50)
    total = 1000.0                                               # cap 20% -> 300 counts as 200; top-3 (200+200+150) capped at 50% of 900
    assert sizing.eligible_nav(assets, COV)[0] == pytest.approx(900 - (550 - 450))


def test_loan_is_opening_ltv_times_eligible_nav_and_grid_follows_the_formula():
    g = sizing.size_grid(POOL, COV, SIZ)
    assert g["eligible_nav"] == pytest.approx(800.0)
    c = {x["opening_ltv"]: x for x in g["candidates"]}
    assert c[0.20]["loan"] == pytest.approx(160.0) and c[0.20]["drawdown_to_breach"] == pytest.approx(0.5)
    u = {(x["opening_ltv"], x["drawdown"]): x for x in g["uniform"]}
    assert u[(0.20, 0.25)]["ltv"] == pytest.approx(0.20 / 0.75) and u[(0.20, 0.25)]["status"] == "ok"
    assert u[(0.20, 0.50)]["status"] == "breach" and u[(0.10, 0.50)]["status"] == "ok"
    assert len(g["single_name"]) == 4


def test_a_uniform_sector_scenario_equals_a_uniform_drawdown():
    resolved, skipped = sizing.resolve_scenarios([{"name": "all -25%", "shocks": {"default": 0.25}}], ["Tech", "Fin", "Ind"], None, {}, "SPY")
    row = sizing.run_scenarios(POOL, COV, 160.0, resolved)[0]
    assert not skipped and row["ltv"] == pytest.approx(0.20 / 0.75) and row["pool_fall"] == pytest.approx(0.25)
    assert row["shocks"] == "every sector -25%"


def test_sector_scenario_hits_only_that_sector():
    resolved, _ = sizing.resolve_scenarios([{"name": "tech", "shocks": {"Tech": 0.5, "default": 0.0}}], ["Tech", "Fin", "Ind"], None, {}, "SPY")
    row = sizing.run_scenarios(POOL, COV, 160.0, resolved)[0]
    assert row["pool_fall"] == pytest.approx(250 / 1000) and row["shocks"] == "Tech -50%; all other sectors -0%"
    stressed = sizing.to_assets(POOL, {"N0": 150.0, "N1": 100.0})
    assert row["eligible_nav"] == pytest.approx(sizing.eligible_nav(stressed, COV)[0])


def test_market_history_scenario_uses_the_worst_fall_in_the_window_or_is_skipped():
    book = PriceBook()
    book.add("AAA", [(date(2022, 1, 31), 100, 100), (date(2022, 6, 30), 60, 60), (date(2022, 12, 30), 90, 90)])
    sc = [{"name": "hist", "historical": {"window_start": "2022-01-31", "window_end": "2022-12-31", "pass_through": 0.5}}]
    resolved, skipped = sizing.resolve_scenarios(sc, ["Tech"], book, {"Tech": "AAA"}, "SPY")
    assert resolved[0]["shocks"] == {"Tech": pytest.approx(0.20)} and resolved[0]["kind"] == "market history" and not skipped
    resolved, skipped = sizing.resolve_scenarios(sc, ["Tech", "Fin"], book, {"Tech": "AAA"}, "SPY")
    assert resolved == [] and "SPY" in skipped[0]
    assert sizing.max_drawdown(book.rows("AAA"), date(2022, 7, 1), date(2022, 12, 31)) == 0.0


RO = dict(all_in_rate_pct=10.0, tenor_years=4, cov=COV, sweep_below=0.5, sweep_above=1.0)


def test_runoff_first_quarter_by_hand():
    r = sizing.runoff(1000.0, 200.0, pace_per_year=0.20, **RO)
    q1 = r["rows"][0]                                    # proceeds 50, interest 5, half of the remaining 45 repays principal
    assert q1["exit_proceeds"] == pytest.approx(50.0) and q1["interest"] == pytest.approx(5.0)
    assert q1["principal_repaid"] == pytest.approx(22.5) and q1["loan_end"] == pytest.approx(177.5) and q1["nav_end"] == pytest.approx(950.0)
    assert r["repaid_quarter"] is not None and r["balance_at_maturity"] == 0.0 and not r["breached"]


def test_runoff_with_no_exits_capitalises_interest_and_is_never_repaid():
    r = sizing.runoff(1000.0, 200.0, pace_per_year=0.0, **RO)
    assert r["repaid_quarter"] is None and r["balance_at_maturity"] == pytest.approx(200 * 1.025 ** 16)
    assert r["interest_capitalised"] == pytest.approx(200 * 1.025 ** 16 - 200)


def test_drought_and_markdown_make_it_worse_and_full_sweep_kicks_in():
    base = sizing.runoff(1000.0, 250.0, pace_per_year=0.15, **RO)
    dry = sizing.runoff(1000.0, 250.0, pace_per_year=0.15, drought_multiplier=0.25, drought_quarters=8, **RO)
    hit = sizing.runoff(1000.0, 250.0, pace_per_year=0.15, drought_multiplier=0.25, drought_quarters=8, markdown=0.25, **RO)
    assert base["balance_at_maturity"] < dry["balance_at_maturity"] and dry["peak_ltv"] < hit["peak_ltv"]
    assert hit["swept"] and hit["rows"][0]["principal_repaid"] == pytest.approx(hit["rows"][0]["exit_proceeds"] - hit["rows"][0]["interest"])


def test_breakeven_pace_is_the_boundary():
    be = sizing.breakeven_pace(1000.0, 200.0, **RO)
    assert sizing.runoff(1000.0, 200.0, pace_per_year=be, **RO)["balance_at_maturity"] <= 1e-6
    assert sizing.runoff(1000.0, 200.0, pace_per_year=be - 0.005, **RO)["balance_at_maturity"] > 0
    assert sizing.breakeven_pace(1000.0, 100.0, **RO) < be
    assert sizing.breakeven_pace(100.0, 5000.0, **RO) is None and not math.isnan(be)


def test_real_pool_numbers(snaps, cfg):
    p = collateral.build_pool(snaps[-1], cfg["vehicle"], cfg["facility"]["collateral"])
    s = collateral.pool_summary(snaps[-1], p)
    assert s["eligible_names"] == 27 and s["eligible_fv"] == pytest.approx(958.1) and s["excluded_fv"] == pytest.approx(93.1)
    g = sizing.size_grid(p, cfg["facility"]["covenants"], cfg["facility"]["sizing"])
    cap = 0.075 * 958.1                                   # Action 78.4 and Solenis 72.6 are capped at 7.5% of the pool
    assert g["candidates"][0]["excluded_single_cap"] == pytest.approx((78.4 - cap) + (72.6 - cap))
    assert g["eligible_nav"] == pytest.approx(922.9, abs=0.05)
