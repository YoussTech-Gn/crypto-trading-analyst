"""Milestone 3 tests: indicators, swings, structure, liquidity, FVG, engine, no look-ahead."""
from __future__ import annotations

import math
import random

import pytest

from packages.analysis import AnalysisEngine
from packages.config.settings import AnalysisConfig
from packages.fvg import detect_bullish_fvgs
from packages.indicators import atr, ema, relative_volume, rsi
from packages.liquidity import dedupe_levels, group_sweeps, LiquidityLevel, build_swing_levels, detect_sweeps, previous_day_levels
from packages.market_data.models import Candle
from packages.market_structure import assess_daily_trend, detect_breaks, detect_swings, label_swings

H4 = 4 * 3_600_000
D1 = 86_400_000


def mk(i, o, h, l, c, v=100.0, step=H4, start=0):
    t = start + i * step
    return Candle("TESTUSDT", "4h" if step == H4 else "1d", t, t + step - 1, o, h, l, c, v, v * c, 10)


def series(highs_lows, step=H4, start=0):
    return [mk(i, (h + l) / 2, h, l, (h + l) / 2, step=step, start=start) for i, (h, l) in enumerate(highs_lows)]


# ---------------- indicators ----------------
def test_ema_seed_and_recurrence():
    out = ema([1, 2, 3, 4, 5], 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(4 * 0.5 + 2.0 * 0.5)
    assert out[4] == pytest.approx(5 * 0.5 + out[3] * 0.5)


def test_ema_short_input_all_none():
    assert ema([1, 2], 5) == [None, None]


def test_rsi_extremes_and_flat():
    assert rsi(list(range(1, 30)), 14)[-1] == 100.0
    assert rsi(list(range(30, 1, -1)), 14)[-1] == pytest.approx(0.0)
    assert rsi([5.0] * 20, 14)[-1] == 50.0
    assert rsi([1, 2, 3], 14) == [None, None, None]


def test_rsi_known_value():
    # classic Wilder example sequence (first RSI value, period 14) ~ 70.46
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
              45.89, 46.03, 45.61, 46.28, 46.28]
    assert rsi(closes, 14)[14] == pytest.approx(70.46, abs=0.1)


def test_atr_first_value_and_smoothing():
    h = [10, 11, 12, 13]; l = [8, 9, 10, 11]; c = [9, 10, 11, 12]
    out = atr(h, l, c, 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)  # TR = 2,2,2
    assert out[3] == pytest.approx((2.0 * 2 + 2.0) / 3)


def test_atr_length_mismatch():
    with pytest.raises(ValueError):
        atr([1], [1, 2], [1], 1)


def test_relative_volume_excludes_current():
    out = relative_volume([10, 10, 10, 30], 3)
    assert out[3] == pytest.approx(3.0)
    assert out[2] is None
    assert relative_volume([0, 0, 0, 5], 3)[3] is None


def test_indicators_reject_nan():
    with pytest.raises(ValueError):
        ema([1.0, float("nan"), 3.0], 2)


def test_indicators_no_lookahead():
    rnd = random.Random(1)
    vals = [100 + rnd.uniform(-5, 5) for _ in range(120)]
    full = ema(vals, 10)
    for cut in (30, 60, 99):
        assert ema(vals[:cut], 10) == full[:cut]
    full_r = rsi(vals, 14)
    assert rsi(vals[:70], 14) == full_r[:70]


# ---------------- swings / structure ----------------
def test_swing_detection_and_confirmation_index():
    hl = [(10, 9), (11, 10), (12, 11), (15, 12), (12, 11), (11, 10), (10, 9), (9, 8), (8, 7)]
    sw = detect_swings(series(hl), 2)
    highs = [s for s in sw if s.kind == "HIGH"]
    assert len(highs) == 1 and highs[0].index == 3 and highs[0].price == 15
    assert highs[0].confirmed_index == 5


def test_equal_highs_are_not_swings():
    hl = [(10, 9), (10, 9), (12, 9), (12, 9), (10, 9), (10, 9)]
    assert [s for s in detect_swings(series(hl), 1) if s.kind == "HIGH"] == []


def test_swings_no_lookahead_prefix_property():
    rnd = random.Random(7)
    price = 100.0
    cs = []
    for i in range(150):
        price += rnd.uniform(-3, 3)
        cs.append(mk(i, price, price + rnd.uniform(0, 2), price - rnd.uniform(0, 2), price))
    full = detect_swings(cs, 3)
    for cut in (40, 77, 120):
        prefix = detect_swings(cs[:cut], 3)
        expected = [s for s in full if s.confirmed_index <= cut - 1]
        assert prefix == expected


def test_labels_hh_hl_lh_ll():
    from packages.market_structure import Swing
    mk_s = lambda k, i, p: Swing(k, i, p, i, i + 1, i + 1)
    out = label_swings([mk_s("HIGH", 1, 10), mk_s("LOW", 2, 5), mk_s("HIGH", 3, 12), mk_s("LOW", 4, 6),
                        mk_s("HIGH", 5, 11), mk_s("LOW", 6, 4)])
    assert [s.label for s in out] == ["FIRST", "FIRST", "HH", "HL", "LH", "LL"]


def test_break_of_structure_requires_close_not_wick():
    hl = [(10, 9), (11, 10), (15, 11), (11, 10), (10, 9), (16, 9), (10, 9)]  # wick to 16
    cs = series(hl)
    sw = detect_swings(cs, 1)
    # candle 5 has high 16 but close (16+9)/2=12.5 < 15 -> no break
    assert detect_breaks(cs[:6], sw) == []
    cs2 = cs[:5] + [mk(5, 12, 17, 12, 16.5), mk(6, 16, 17, 15, 16)]
    br = detect_breaks(cs2, detect_swings(cs2, 1))
    assert br and br[0].direction == "UP" and br[0].break_index == 5 and br[0].level == 15


def trend_series(n=260, up=True):
    cs = []
    p = 100.0
    for i in range(n):
        wave = 4.0 * math.sin(i / 3.0)
        p = 100 + (i * 0.8 if up else -i * 0.3) + wave
        cs.append(mk(i, p, p + 1.0, p - 1.0, p, step=D1))
    return cs


def test_daily_trend_bullish_on_clean_uptrend():
    cs = trend_series(260, True)
    f, s = ema([c.close for c in cs], 50), ema([c.close for c in cs], 200)
    sw = label_swings(detect_swings(cs, 3))
    t = assess_daily_trend(cs, sw, f[-1], s[-1], 2)
    assert t.bullish, t.failed_conditions


def test_daily_trend_fails_closed_without_history():
    cs = trend_series(40, True)
    t = assess_daily_trend(cs, label_swings(detect_swings(cs, 3)), None, None, 2)
    assert not t.bullish and "EMA_AVAILABLE" in t.failed_conditions


def test_daily_trend_not_bullish_in_downtrend():
    cs = trend_series(260, False)
    f, s = ema([c.close for c in cs], 50), ema([c.close for c in cs], 200)
    t = assess_daily_trend(cs, label_swings(detect_swings(cs, 3)), f[-1], s[-1], 2)
    assert not t.bullish


# ---------------- liquidity ----------------
def test_equal_lows_detected_within_tolerance():
    from packages.market_structure import Swing
    a = Swing("LOW", 5, 100.0, 5, 8, 8); b = Swing("LOW", 15, 100.05, 15, 18, 18)
    lv = build_swing_levels([a, b], 0.1)
    assert any(l.kind == "EQUAL_LOWS" and l.price == 100.0 for l in lv)
    assert not any(l.kind == "EQUAL_LOWS" for l in build_swing_levels([a, b], 0.01))


def test_sweep_requires_reclaim_and_min_penetration():
    level = LiquidityLevel("SWING_LOW", 100.0, 0, 1, 0)
    base = [mk(0, 105, 106, 104, 105)]
    # wick below to 99 (1%) closing back above -> sweep
    sweep = base + [mk(1, 105, 106, 99, 103)]
    r = detect_sweeps(sweep, [level], 0.05)
    assert len(r) == 1 and r[0].sweep_index == 1 and r[0].penetration_pct == pytest.approx(1.0)
    # closes below -> break, no sweep
    assert detect_sweeps(base + [mk(1, 105, 106, 99, 99.5)], [level], 0.05) == []
    # tiny touch (0.01%) -> not a sweep, level stays active
    touch = base + [mk(1, 105, 106, 99.99, 103), mk(2, 103, 104, 98, 102)]
    r = detect_sweeps(touch, [level], 0.05)
    assert len(r) == 1 and r[0].sweep_index == 2


def test_level_spent_after_first_sweep():
    level = LiquidityLevel("SWING_LOW", 100.0, 0, 1, 0)
    cs = [mk(0, 105, 106, 104, 105), mk(1, 105, 106, 99, 103), mk(2, 103, 104, 98, 102)]
    assert len(detect_sweeps(cs, [level], 0.05)) == 1


def test_buy_side_levels_never_swept():
    level = LiquidityLevel("SWING_HIGH", 100.0, 0, 1, 0)
    cs = [mk(0, 95, 96, 94, 95), mk(1, 95, 105, 94, 95)]
    assert detect_sweeps(cs, [level], 0.05) == []


def test_previous_day_levels_use_previous_utc_day_only():
    daily = [mk(0, 10, 20, 5, 15, step=D1), mk(1, 15, 30, 12, 25, step=D1)]
    setup = [mk(i, 20, 21, 19, 20, start=D1) for i in range(0, 1)]  # inside day 1
    setup = [Candle("T", "4h", D1 + i * H4, D1 + (i + 1) * H4 - 1, 20, 21, 19, 20, 1, 1, 1) for i in range(6)]
    lv = previous_day_levels(setup, daily)
    low = [l for l in lv if l.kind == "PREV_DAY_LOW"]
    assert len(low) == 1 and low[0].price == 5 and low[0].active_from_index == 0
    assert previous_day_levels(setup[:0], daily) == []


# ---------------- FVG ----------------
def test_bullish_fvg_geometry_and_statuses():
    base = [mk(0, 10, 11, 9, 10.5), mk(1, 10.5, 15, 10, 14), mk(2, 14, 16, 12, 15)]  # gap [11,12]
    g = detect_bullish_fvgs(base)
    assert len(g) == 1 and (g[0].lower, g[0].upper) == (11, 12) and g[0].status == "UNTOUCHED"
    assert detect_bullish_fvgs(base + [mk(3, 15, 16, 11.8, 15.5)])[0].status == "ENTERED"
    assert detect_bullish_fvgs(base + [mk(3, 15, 16, 10.9, 15.5)])[0].status == "FILLED"
    assert detect_bullish_fvgs(base + [mk(3, 15, 16, 10, 10.5)])[0].status == "INVALIDATED"


def test_no_fvg_when_candles_overlap():
    cs = [mk(0, 10, 12, 9, 11), mk(1, 11, 13, 10, 12), mk(2, 12, 14, 11.5, 13)]
    assert detect_bullish_fvgs(cs) == []


def test_fvg_formation_is_prefix_stable():
    rnd = random.Random(3)
    p = 100.0
    cs = []
    for i in range(120):
        p += rnd.uniform(-2, 3)
        cs.append(mk(i, p, p + rnd.uniform(0, 3), p - rnd.uniform(0, 3), p + rnd.uniform(-1, 1)))
    full = {(g.index, g.lower, g.upper) for g in detect_bullish_fvgs(cs)}
    pre = {(g.index, g.lower, g.upper) for g in detect_bullish_fvgs(cs[:80])}
    assert pre == {x for x in full if x[0] < 80}


# ---------------- engine ----------------
def build_pair(n_d=260, n_h=500):
    daily = trend_series(n_d, True)
    rnd = random.Random(11)
    p = 150.0
    setup = []
    for i in range(n_h):
        p += rnd.uniform(-2, 2.2)
        setup.append(mk(i, p, p + rnd.uniform(0, 1.5), p - rnd.uniform(0, 1.5), p + rnd.uniform(-0.5, 0.5),
                        v=100 + rnd.uniform(0, 50)))
    return daily, setup


def test_engine_is_deterministic_and_plain_data():
    daily, setup = build_pair()
    e = AnalysisEngine(AnalysisConfig())
    a, b = e.analyze("TESTUSDT", daily, setup), e.analyze("TESTUSDT", daily, setup)
    assert a == b
    d = a.to_dict()
    assert d["note"].startswith("analysis only") and "bullish" in d["daily_trend"]
    assert all("confirmed_time_ms" in s for s in d["setup_swings"])


def test_engine_prefix_does_not_see_future():
    daily, setup = build_pair()
    e = AnalysisEngine(AnalysisConfig())
    cut = 300
    full = e.analyze("T", daily, setup)
    pre = e.analyze("T", daily, setup[:cut])
    full_sw = [s for s in full.setup_swings if s["confirmed_index"] <= cut - 1]
    assert pre.setup_swings == full_sw
    full_fvg_idx = {g["index"] for g in full.fair_value_gaps if g["index"] < cut}
    assert {g["index"] for g in pre.fair_value_gaps} == full_fvg_idx


def test_engine_rejects_empty_and_unsorted():
    e = AnalysisEngine()
    daily, setup = build_pair()
    with pytest.raises(ValueError):
        e.analyze("T", [], setup)
    with pytest.raises(ValueError):
        e.analyze("T", daily, list(reversed(setup)))


def test_config_validation():
    with pytest.raises(Exception):
        AnalysisConfig(ema_fast=200, ema_slow=50)
    with pytest.raises(Exception):
        AnalysisConfig(unknown_field=1)
    assert AnalysisConfig().swing_lookback == 3


def test_dedupe_same_price_levels_keeps_priority():
    a = LiquidityLevel("SWING_LOW", 81.34, 3, 5, 0)
    b = LiquidityLevel("PREV_DAY_LOW", 81.34, 9, 2, 0)
    out = dedupe_levels([a, b])
    assert len(out) == 1 and out[0].kind == "PREV_DAY_LOW" and out[0].active_from_index == 2


def test_group_sweeps_one_event_per_candle():
    lv1 = LiquidityLevel("SWING_LOW", 100.0, 0, 1, 0)
    lv2 = LiquidityLevel("SWING_LOW", 100.5, 0, 1, 0)
    cs = [mk(0, 105, 106, 104, 105), mk(1, 105, 106, 99, 103)]
    ev = group_sweeps(detect_sweeps(cs, [lv1, lv2], 0.05))
    assert len(ev) == 1 and len(ev[0]["levels"]) == 2 and ev[0]["deepest_level_kind"] == "SWING_LOW"


def test_prev_day_level_expires_at_end_of_its_day():
    daily = [mk(0, 10, 20, 5, 15, step=D1), mk(1, 15, 30, 12, 25, step=D1), mk(2, 25, 30, 20, 28, step=D1)]
    setup = [Candle("T", "4h", D1 + i * H4, D1 + (i + 1) * H4 - 1, 20, 21, 19, 20, 1, 1, 1) for i in range(12)]
    # day-1 candles idx 0-5 (PDL=5), day-2 candles idx 6-11 (PDL=12)
    setup[8] = Candle("T", "4h", setup[8].open_time_ms, setup[8].close_time_ms, 20, 21, 4, 20, 1, 1, 1)  # dips under day-1 PDL on day 2
    lv = previous_day_levels(setup, daily)
    pdl1 = [l for l in lv if l.kind == "PREV_DAY_LOW" and l.price == 5][0]
    assert pdl1.expires_index == 6
    assert detect_sweeps(setup, [pdl1], 0.05) == []  # day-1 PDL cannot be swept on day 2


def test_group_sweeps_collapses_same_price_levels():
    a = LiquidityLevel("SWING_LOW", 100.0, 0, 1, 0)
    b = LiquidityLevel("PREV_DAY_LOW", 100.0, 0, 1, 0, 5)
    cs = [mk(0, 105, 106, 104, 105), mk(1, 105, 106, 99, 103)]
    ev = group_sweeps(detect_sweeps(cs, [a, b], 0.05))
    assert len(ev) == 1 and len(ev[0]["levels"]) == 1 and ev[0]["levels"][0]["kind"] == "PREV_DAY_LOW"


def test_features_block_is_additive_and_has_no_look_ahead():
    import random
    from packages.analysis import AnalysisEngine
    from packages.market_data.models import Candle

    random.seed(3)
    H4, D1 = 14_400_000, 86_400_000
    price, setup, daily = 100.0, [], []
    for i in range(600):
        price *= 1 + random.uniform(-0.01, 0.011)
        t = 1_600_000_000_000 // H4 * H4 + i * H4
        setup.append(Candle("T", "4h", t, t + H4 - 1, price, price * 1.004, price * 0.996, price, 10.0, 1000.0, 5))
    for i in range(300):
        t = 1_600_000_000_000 // D1 * D1 + (i - 150) * D1
        daily.append(Candle("T", "1d", t, t + D1 - 1, 100.0 + i * 0.1, 101.0 + i * 0.1, 99.0 + i * 0.1, 100.0 + i * 0.1, 10.0, 1000.0, 5))
    eng = AnalysisEngine()
    full = eng.analyze("T", daily, setup).to_dict()
    f = full["features"]
    assert f["prior_high_20"] == max(c.high for c in setup[-21:-1])   # excludes the last candle
    assert f["recent_low_10"] == min(c.low for c in setup[-10:])      # includes the last candle
    assert 0.0 <= f["setup_atr_pct_rank_200"] <= 1.0 and f["daily_roc_20"] > 0
    # truncating the future must not change the value computed at an earlier candle (no look-ahead)
    cut = eng.analyze("T", daily, setup[:-5]).to_dict()["features"]
    assert cut["prior_high_20"] == max(c.high for c in setup[:-5][-21:-1])
    assert "indicators" in full and "setup_atr" in full["indicators"]  # existing output untouched
