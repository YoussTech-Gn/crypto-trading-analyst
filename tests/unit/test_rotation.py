import math

import pytest

from packages.strategies.rotation import (RotationParams, block_bootstrap_mean_ci, ema_by_day, max_drawdown, score,
                                          sharpe, simulate, weekday_of)


def lin(start, step, n, d0=0):
    return {d0 + i: start * (1 + step) ** i for i in range(n)}


def test_weekday_epoch_was_thursday():
    assert weekday_of(0) == 3 and weekday_of(4) == 0  # 1970-01-05 was a Monday


def test_score_needs_history_and_a_full_window():
    p = RotationParams()
    up = lin(100, 0.01, 100)
    up[50] *= 1.001  # some noise so volatility is not zero
    assert score(up, 99, p) is not None and score(up, 99, p) > 0
    assert score(lin(100, 0.01, 40), 39, p) is None            # < 60 candles
    gap = dict(up)
    del gap[90]
    assert score(gap, 99, p) is None                            # a hole inside the 28-day window


def test_score_uses_no_future_close():
    p = RotationParams()
    a = lin(100, 0.01, 120)
    a[70] *= 1.01
    b = dict(a)
    b[100] = 1.0                                                # day 100 is the rebalance day itself: must be ignored
    assert score(a, 100, p) == score(b, 100, p)


def test_gate_off_means_cash_and_costs_are_charged_on_turnover():
    p = RotationParams(min_history=5, lookback=3, ema_gate=3)
    btc_down = lin(100, -0.01, 60)
    panel = {"BTCUSDT": btc_down, "A": lin(10, 0.02, 60)}
    r = simulate(panel, btc_down, 20, 50, weekday_of(20), p)
    assert all(w.weights == {} and w.net == 0.0 for w in r.weeks)
    btc_up = lin(100, 0.01, 60)
    for d in range(60):
        btc_up[d] *= 1 + 0.001 * (d % 3)
    panel = {"BTCUSDT": btc_up, "A": {d: 10 * 1.02 ** d * (1 + 0.001 * (d % 2)) for d in range(60)}}
    r = simulate(panel, btc_up, 20, 50, weekday_of(20), RotationParams(min_history=5, lookback=3, ema_gate=3, top_k=1))
    first = r.weeks[0]
    assert first.weights == {"A": 1.0} and first.turnover == pytest.approx(1.0)
    assert first.cost == pytest.approx(0.0015)
    assert first.net == pytest.approx((1 - 0.0015) * (1 + first.gross) - 1)


def test_benchmark_modes():
    btc = lin(100, 0.01, 80)
    for d in range(80):
        btc[d] *= 1 + 0.001 * (d % 2)
    p = RotationParams()
    hold = simulate({"BTCUSDT": btc}, btc, 60, 79, weekday_of(60), p, "btc_hold")
    assert hold.weeks[0].weights == {"BTCUSDT": 1.0}
    g = simulate({"BTCUSDT": btc}, btc, 60, 79, weekday_of(60), p, "btc_gate")
    assert g.weeks[0].gate_on and g.weeks[0].weights == {"BTCUSDT": 1.0}
    assert g.weeks[1].turnover < 0.05                            # holding on: only drift, almost no trading


def test_stats():
    assert max_drawdown([0.1, -0.5, 0.2]) == pytest.approx(0.5)
    assert sharpe([0.01] * 10) == 0.0
    lo, hi = block_bootstrap_mean_ci([0.03, -0.01, -0.02, 0.0, 0.01, -0.01] * 20)
    assert lo < 0 < hi
    lo, hi = block_bootstrap_mean_ci([0.02 + 0.001 * (i % 3) for i in range(100)])
    assert lo > 0
    e = ema_by_day({0: 1.0, 1: 2.0}, 3)
    assert e[1] == pytest.approx(1.5)
