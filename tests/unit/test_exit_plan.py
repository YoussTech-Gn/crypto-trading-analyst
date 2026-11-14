"""Exit management (ExitPlan): conservative ordering, break-even is not free, partial exits, time exit."""
from __future__ import annotations

import pytest

from packages.backtest import ExitPlan, simulate_order
from packages.backtest.engine import net_r
from packages.market_data.models import Candle

H4 = 4 * 3_600_000
ENTRY, STOP, TARGET = 100.0, 95.0, 110.0  # risk = 5, so +1R = 105 and +2R = 110
FEE, SLIP = 0.1, 0.05


def c(i, o, h, l, cl):
    t = i * H4
    return Candle("T", "4h", t, t + H4 - 1, o, h, l, cl, 1.0, 1.0, 1)


def flat(i, price=120.0):
    return c(i, price, price + 1, price - 1, price)


def run(candles, plan, max_hold=30):
    return simulate_order(candles, 0, ENTRY, STOP, TARGET, 6, max_hold, FEE, SLIP, plan)


def test_inactive_plan_equals_default_path():
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 101, 111, 100, 109)]
    a = run(cs, None)
    b = run(cs, ExitPlan())
    assert a == b


def test_breakeven_stop_exits_flat_but_pays_fees_and_slippage():
    # candle 2 reaches +1R (105) -> stop moves to entry from candle 3; candle 3 drops to the entry and stops out.
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 101, 106, 100, 104), c(3, 104, 104, 99, 100)]
    kind, (fill, ex, px, reason, r, fee_r), _ = run(cs, ExitPlan(breakeven_after_r=1.0))
    assert (kind, fill, ex, reason) == ("TRADE", 1, 3, "BREAKEVEN")
    assert px == pytest.approx(min(ENTRY * (1 - SLIP / 100), 104))
    assert r < 0  # not free: fees + slippage
    assert r == pytest.approx(net_r(ENTRY, STOP, px, FEE))
    assert fee_r == pytest.approx(0.001 * (ENTRY + px) / 5)


def test_breakeven_does_not_apply_inside_the_trigger_candle():
    # same candle reaches +1R and falls to the entry: the stop has NOT moved yet, so the trade is still alive
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 101, 106, 99.5, 103), c(3, 103, 111, 102, 110)]
    kind, payload, _ = run(cs, ExitPlan(breakeven_after_r=1.0))
    assert payload[3] == "TARGET"


def test_original_stop_still_wins_ties_before_breakeven():
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 100, 106, 94, 100)]
    kind, payload, _ = run(cs, ExitPlan(breakeven_after_r=1.0))
    assert payload[3] == "STOP"


def test_partial_exit_blends_two_fills():
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 101, 106, 100, 104), c(3, 104, 111, 103, 110)]
    plan = ExitPlan(partial_at_r=1.0, partial_fraction=0.5, breakeven_after_partial=True)
    kind, (fill, ex, px, reason, r, fee_r), _ = run(cs, plan)
    assert reason == "TARGET" and ex == 3
    gross = (0.5 * (105 - ENTRY) + 0.5 * (110 - ENTRY)) / 5
    fees = 0.001 * (0.5 * (ENTRY + 105) + 0.5 * (ENTRY + 110)) / 5
    assert r == pytest.approx(gross - fees)
    assert px == pytest.approx(0.5 * 105 + 0.5 * 110)


def test_partial_then_breakeven_stop_keeps_the_banked_half():
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 101, 106, 100, 104), c(3, 104, 104, 98, 99)]
    plan = ExitPlan(partial_at_r=1.0, partial_fraction=0.5, breakeven_after_partial=True)
    kind, (fill, ex, px, reason, r, fee_r), _ = run(cs, plan)
    assert reason == "BREAKEVEN"
    assert r > -0.5  # half the position was banked at +1R, so the loss is far smaller than a full stop
    full_stop_r = net_r(ENTRY, STOP, STOP * (1 - SLIP / 100), FEE)
    assert r > full_stop_r


def test_time_exit_closes_a_stalled_trade_but_not_a_working_one():
    stalled = [flat(0), c(1, 101, 101, 99, 100)] + [c(i, 100, 101, 99, 100.5) for i in range(2, 6)]
    kind, payload, _ = run(stalled, ExitPlan(time_exit_bars=3, time_exit_min_mfe_r=0.5))
    assert payload[3] == "TIME_DECAY" and payload[1] == 4  # fill 1 + 3 candles
    working = [flat(0), c(1, 101, 101, 99, 100), c(2, 100, 104, 100, 103)] + [c(i, 103, 104, 102, 103) for i in range(3, 6)]
    kind, payload, _ = run(working, ExitPlan(time_exit_bars=3, time_exit_min_mfe_r=0.5))
    assert kind == "OPEN"  # it reached +0.8R, so the time exit does not fire and the trade is still running


def test_trade_still_open_is_reported_open():
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 100, 102, 99, 101)]
    kind, payload, _ = run(cs, ExitPlan(breakeven_after_r=1.0))
    assert kind == "OPEN" and payload is None


def test_trailing_stop_protects_from_the_next_candle_and_locks_profit():
    # candle 2 rises to 108 (+1.6R): the trail (1R = 5 below the high) becomes 103, effective from candle 3.
    # Candle 2 also dips to 100.5 which is above the old stop, and candle 3 falls to 102 -> exits near 103.
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 101, 108, 100.5, 107), c(3, 107, 107, 102, 103)]
    plan = ExitPlan(trail_after_r=1.0, trail_distance_r=1.0)
    kind, (fill, ex, px, reason, r, fee_r), _ = simulate_order(cs, 0, ENTRY, STOP, 200.0, 6, 30, FEE, SLIP, plan)
    assert (kind, ex, reason) == ("TRADE", 3, "TRAIL")
    assert px == pytest.approx(103 * (1 - SLIP / 100))
    assert r > 0.4  # about +0.6R before fees


def test_trailing_stop_never_moves_down_and_does_not_act_inside_the_trigger_candle():
    # same candle reaches +1.6R and falls to 101: the stop had not moved yet, so the trade survives that candle
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 101, 108, 96, 107), c(3, 107, 109, 106, 108)]
    plan = ExitPlan(trail_after_r=1.0, trail_distance_r=1.0)
    kind, payload, _ = simulate_order(cs, 0, ENTRY, STOP, 200.0, 6, 30, FEE, SLIP, plan)
    assert kind == "OPEN"
    # a later pull-back never loosens the stop
    cs2 = cs + [c(4, 108, 108, 101, 102)]
    kind, (fill, ex, px, reason, r, fee_r), _ = simulate_order(cs2, 0, ENTRY, STOP, 200.0, 6, 30, FEE, SLIP, plan)
    assert reason == "TRAIL" and ex == 4 and px == pytest.approx(min(104.0 * (1 - SLIP / 100), 108))  # high 109 - 5 = 104


def test_plan_can_extend_the_maximum_holding_time():
    cs = [flat(0), c(1, 101, 101, 99, 100)] + [c(i, 100, 101, 99.5, 100.5) for i in range(2, 45)]
    kind, payload, _ = simulate_order(cs, 0, ENTRY, STOP, 200.0, 6, 30, FEE, SLIP, ExitPlan())
    assert payload[3] == "TIMEOUT"  # default path: 30 candles
    kind, payload, _ = simulate_order(cs, 0, ENTRY, STOP, 200.0, 6, 30, FEE, SLIP, ExitPlan(max_hold_candles=60))
    assert kind == "OPEN"
    kind, payload, _ = simulate_order(cs, 0, ENTRY, STOP, 200.0, 6, 30, FEE, SLIP, ExitPlan(max_hold_candles=20))
    assert payload[3] == "TIMEOUT" and payload[1] == 1 + 20
