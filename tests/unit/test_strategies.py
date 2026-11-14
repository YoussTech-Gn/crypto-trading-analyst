import pytest

from packages.backtest.engine import Trade
from packages.config.settings import load_config
from packages.strategies import Goal, build_recipes, score_recipe, z_for_trials


def analysis(**over):
    sw = [{"kind": "HIGH", "index": 10, "price": 110.0, "time_ms": 1}, {"kind": "HIGH", "index": 20, "price": 125.0, "time_ms": 2},
          {"kind": "LOW", "index": 30, "price": 94.0, "time_ms": 3}]
    a = {
        "symbol": "TESTUSDT", "version": "analysis-1.0", "setup_last_open_time_ms": 1_000, "setup_candle_count": 101,
        "daily_trend": {"bullish": True, "failed_conditions": []},
        "indicators": {"setup_last_close": 100.0, "setup_atr": 2.0, "setup_rsi": 50.0, "setup_relative_volume": 1.6,
                       "daily_ema_fast": 100.0, "daily_ema_slow": 95.0},
        "setup_swings": sw,
        "sweep_events": [{"sweep_index": 98, "sweep_low": 96.0, "deepest_penetration_pct": 0.3}],
        "fair_value_gaps": [{"index": 99, "lower": 98.0, "upper": 100.0, "size_in_atr": 1.0, "status": "UNTOUCHED", "formed_time_ms": 5}],
        "structure_breaks": [{"direction": "UP", "broken_swing_index": 10, "level": 99.0, "break_index": 97}],
        "features": {"setup_ema_20": 99.0, "setup_ema_50": 95.0, "setup_prev_close": 99.0, "setup_last_open": 99.0,
                     "setup_last_high": 100.5, "setup_last_low": 98.5, "prior_high_20": 99.5, "prior_high_55": 99.5,
                     "recent_low_5": 96.0, "recent_low_10": 95.0, "recent_low_20": 94.0, "setup_rsi_prev": 28.0},
        "regime": {"btc_daily_bullish": True},
    }
    a.update(over)
    return a


def recipes():
    return build_recipes(load_config())


def test_all_recipes_signal_on_a_clean_setup_with_sane_levels():
    for name, r in recipes().items():
        d = r.decide(analysis())
        assert d.decision == "SIGNAL", (name, d.reasons)
        assert d.stop < d.entry < d.target
        assert d.risk_reward >= 2.0 - 1e-9


def test_sweep_only_needs_no_fvg_and_fvg_only_needs_no_sweep():
    rs = recipes()
    assert rs["sweep_only"].decide(analysis(fair_value_gaps=[])).decision == "SIGNAL"
    assert rs["fvg_only"].decide(analysis(sweep_events=[])).decision == "SIGNAL"
    assert rs["sweep_fvg"].decide(analysis(fair_value_gaps=[])).decision == "NO_TRADE"


def test_daily_trend_gate_blocks_every_recipe():
    bad = analysis(daily_trend={"bullish": False, "failed_conditions": ["x"]})
    for name, r in recipes().items():
        assert r.decide(bad).decision == "NO_TRADE", name


def test_bos_retest_requires_a_recent_break():
    assert recipes()["bos_retest"].decide(analysis(structure_breaks=[])).decision == "NO_TRADE"


def mk_trades(rs, bars=5, reason="TARGET"):
    return [Trade("X", i, i, 100, 95, 110, 2, i, i, i + 1, i + 1, 100, reason, r, bars, "", 0.5, 1.0, {}) for i, r in enumerate(rs)]


def test_scorecard_reports_gap_and_cause():
    losing = {"w1": mk_trades([-1.0] * 20 + [2.0] * 4, bars=1, reason="STOP"), "w2": mk_trades([-1.0] * 20 + [2.0] * 4, bars=1, reason="STOP")}
    c = score_recipe(losing, Goal(), trials=4)
    assert not c["meets_goal"] and any(u.startswith("AVG_R") for u in c["unmet"])
    assert any(x.startswith("FAST_STOPS") for x in c["causes"])


def test_trials_make_the_confidence_bar_stricter():
    assert z_for_trials(30) > z_for_trials(1) > 1.6


def _t(week, r, i):
    ms = week * 7 * 86_400_000 + i
    return Trade("X", i, ms, 100, 95, 110, 2, i, ms, i + 1, ms + 1, 100, "STOP" if r < 0 else "TARGET", r, 2, "", 0.5, 1.0, {})


def test_clustered_se_is_larger_when_trades_in_a_week_move_together():
    from packages.backtest.metrics import time_clustered_mean_se
    # 10 weeks, 5 trades per week; every trade in a week has the SAME result (a market-wide move)
    together = [_t(w, -1.0 if w % 2 else 2.0, w * 10 + j) for w in range(10) for j in range(5)]
    c = time_clustered_mean_se(together)
    assert c["n_clusters"] == 10 and c["se_clustered"] > 2 * c["se_naive"]


def test_clustered_se_matches_naive_when_every_trade_is_in_its_own_week():
    from packages.backtest.metrics import time_clustered_mean_se
    alone = [_t(w, -1.0 if w % 3 else 2.0, w) for w in range(60)]
    c = time_clustered_mean_se(alone)
    assert c["n_clusters"] == 60 and c["se_clustered"] == pytest.approx(c["se_naive"], rel=0.1)


def test_scorecard_uses_the_wider_clustered_bound_and_reports_fee_drag():
    together = {"w": [_t(w, -1.0 if w % 2 else 2.0, w * 10 + j) for w in range(10) for j in range(5)]}
    c = score_recipe(together, Goal(), trials=1)
    assert c["ci_lower_r"] < c["ci_lower_naive_r"] and c["n_clusters"] == 10 and c["avg_fee_r"] == 0.0


def test_fvg_only_is_unchanged_by_the_refactor():
    d = recipes()["fvg_only"].decide(analysis())
    assert d.entry == 99.0 and d.stop == pytest.approx(98.0 - 1.0 * 2.0)  # midpoint entry, gap low minus 1 ATR


def test_variants_change_exactly_one_part():
    rs = recipes()
    base = rs["fvg_only"].components
    for name, r in rs.items():
        if not name.startswith("fvg_") or name == "fvg_only":
            continue
        diff = [k for k in set(base) | set(r.components) if base.get(k) != r.components.get(k)]
        assert len(diff) == 1, (name, diff)


def test_entry_variants_place_the_limit_at_the_edges_of_the_gap():
    rs = recipes()
    assert rs["fvg_entry_upper"].decide(analysis()).entry == 100.0
    assert rs["fvg_entry_lower"].decide(analysis()).entry == 98.0


def test_stop_variants():
    rs = recipes()
    assert rs["fvg_stop_half"].decide(analysis()).stop == pytest.approx(98.0 - 0.5 * 2.0)
    assert rs["fvg_stop_2atr"].decide(analysis()).stop == pytest.approx(98.0 - 2.0 * 2.0)
    d = rs["fvg_stop_struct"].decide(analysis())
    # the swing low (index 30) is before the gap (index 99), so it is used: 94 - 0.25 * 2 = 93.5, entry - 2 = 97
    assert d.stop == pytest.approx(min(94.0 - 0.25 * 2.0, d.entry - 1.0 * 2.0))
    assert rs["fvg_stop_struct"].decide(analysis(setup_swings=[{"kind": "HIGH", "index": 10, "price": 110.0, "time_ms": 1}])).decision == "NO_TRADE"


def test_structural_stop_is_never_closer_than_one_atr():
    near_low = analysis(setup_swings=[{"kind": "HIGH", "index": 10, "price": 110.0, "time_ms": 1},
                                      {"kind": "LOW", "index": 30, "price": 98.8, "time_ms": 3}])
    d = recipes()["fvg_stop_struct"].decide(near_low)
    assert d.entry - d.stop == pytest.approx(2.0)  # 1 ATR floor, not 98.8 - 0.5


def test_volume_filter_blocks_quiet_setups_only():
    quiet = analysis()
    quiet["indicators"] = {**quiet["indicators"], "setup_relative_volume": 0.6}
    r = recipes()["fvg_volume"]
    assert r.decide(quiet).decision == "NO_TRADE" and "RELATIVE_VOLUME_OK" in r.decide(quiet).reasons
    assert r.decide(analysis()).decision == "SIGNAL"
    assert recipes()["fvg_only"].decide(quiet).decision == "SIGNAL"


def test_exit_variants_carry_a_plan_and_the_others_do_not():
    rs = recipes()
    with_plan = {n for n, r in rs.items() if getattr(r, "exit_plan", None) is not None}
    assert with_plan == {"fvg_exit_1r", "fvg_exit_1_5r", "fvg_exit_be", "fvg_exit_partial", "fvg_exit_time",
                         "brk20_trail", "brk55_trail", "brk20_vol_trail", "brk20_btc_trail", "pullback_ema20_trail",
                         "rsi_dip_30", "rsi_dip_35"}


# ---- families (M6c) -------------------------------------------------------------------------------------------------

def feat(**over):
    a = analysis()
    a["features"] = {**a["features"], **over}
    return a


def test_registry_has_all_families_with_unique_names():
    rs = recipes()
    assert len(rs) == 29 and len(set(rs)) == 29
    for n in ("brk20_trail", "pullback_ema20", "rsi_dip_30", "fvg_btc", "combo_upper_2atr_btc"):
        assert n in rs


def test_breakout_needs_a_close_above_the_prior_high_and_the_ema50():
    r = recipes()["brk20_trail"]
    d = r.decide(analysis())
    assert d.decision == "SIGNAL" and d.entry == 100.0 and d.stop == pytest.approx(100.0 - 2.0 * 2.0)
    assert r.decide(feat(prior_high_20=100.5)).decision == "NO_TRADE"
    assert r.decide(feat(setup_ema_50=101.0)).decision == "NO_TRADE"
    assert r.decide(feat(prior_high_20=None)).decision == "NO_TRADE"
    assert recipes()["brk55_trail"].decide(feat(prior_high_55=100.5)).decision == "NO_TRADE"
    assert recipes()["brk55_trail"].decide(feat(prior_high_20=100.5)).decision == "SIGNAL"


def test_breakout_variants_add_one_filter_each():
    rs = recipes()
    quiet = analysis()
    quiet["indicators"] = {**quiet["indicators"], "setup_relative_volume": 1.2}
    assert rs["brk20_vol_trail"].decide(quiet).decision == "NO_TRADE"
    assert rs["brk20_trail"].decide(quiet).decision == "SIGNAL"
    bear = analysis(regime={"btc_daily_bullish": False})
    assert rs["brk20_btc_trail"].decide(bear).decision == "NO_TRADE"
    assert rs["brk20_trail"].decide(bear).decision == "SIGNAL"
    assert rs["brk20_btc_trail"].decide(analysis(regime={"btc_daily_bullish": None})).decision == "NO_TRADE"
    assert rs["brk20_btc_trail"].decide(analysis(regime=None)).decision == "NO_TRADE"


def test_trailing_families_declare_a_trail_and_a_far_cap():
    r = recipes()["brk20_trail"]
    assert r.exit_plan.trail_after_r == 1.0 and r.exit_plan.max_hold_candles == 120
    d = r.decide(analysis())
    assert d.risk_reward == pytest.approx(50.0)


def test_pullback_needs_trend_touch_and_reclaim():
    r = recipes()["pullback_ema20"]
    d = r.decide(analysis())
    assert d.decision == "SIGNAL", d.reasons
    assert d.stop == pytest.approx(min(96.0 - 0.25 * 2.0, 100.0 - 1.0 * 2.0))
    assert r.decide(feat(setup_last_low=99.5)).decision == "NO_TRADE"      # never touched the EMA20
    assert r.decide(feat(setup_ema_20=94.0)).decision == "NO_TRADE"        # EMA20 below EMA50: no uptrend
    assert r.decide(feat(setup_last_open=100.5)).decision == "NO_TRADE"    # closed red
    t = recipes()["pullback_ema20_trail"].decide(analysis())
    assert t.decision == "SIGNAL" and t.risk_reward == pytest.approx(50.0)


def test_rsi_dip_needs_a_cross_up_through_the_level():
    rs = recipes()
    a = analysis()
    a["indicators"] = {**a["indicators"], "setup_rsi": 31.0}
    assert rs["rsi_dip_30"].decide(a).decision == "SIGNAL"
    d = rs["rsi_dip_30"].decide(a)
    assert d.stop == pytest.approx(100.0 - 1.5 * 2.0) and d.risk_reward == pytest.approx(2.0)
    b = feat(setup_rsi_prev=32.0)
    b["indicators"] = {**b["indicators"], "setup_rsi": 40.0}
    assert rs["rsi_dip_30"].decide(b).decision == "NO_TRADE"               # already above
    assert rs["rsi_dip_35"].decide(b).decision == "SIGNAL"                 # crossed 35 from 32? no: 32 <= 35 < 40 yes
    assert rs["rsi_dip_30"].decide(feat(setup_rsi_prev=None)).decision == "NO_TRADE"


def test_btc_regime_recipes_equal_their_base_when_bullish_and_block_otherwise():
    rs = recipes()
    for name, base in (("fvg_btc", "fvg_only"), ("combo_upper_btc", "fvg_entry_upper")):
        a, b = rs[name].decide(analysis()), rs[base].decide(analysis())
        assert (a.entry, a.stop, a.target) == (b.entry, b.stop, b.target)
        assert rs[name].decide(analysis(regime={"btc_daily_bullish": False})).decision == "NO_TRADE"


def test_combos_combine_exactly_their_named_parts():
    rs = recipes()
    d = rs["combo_upper_2atr"].decide(analysis())
    assert d.entry == 100.0 and d.stop == pytest.approx(98.0 - 4.0)
    quiet = analysis()
    quiet["indicators"] = {**quiet["indicators"], "setup_relative_volume": 0.6}
    assert rs["combo_upper_2atr_vol"].decide(quiet).decision == "NO_TRADE"
    assert rs["combo_upper_2atr_btc"].decide(analysis(regime={"btc_daily_bullish": False})).decision == "NO_TRADE"
