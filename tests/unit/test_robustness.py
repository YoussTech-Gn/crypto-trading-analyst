import pytest

from packages.backtest.robustness import path_drawdown, shuffle_drawdowns, trade_shuffle_report


def test_path_drawdown():
    assert path_drawdown([1, -1, -1, 2, -3]) == pytest.approx(3.0)
    assert path_drawdown([1, 1, 1]) == 0.0


def test_shuffling_keeps_results_and_is_reproducible():
    rs = [1.0, -1.0] * 20
    a, b = shuffle_drawdowns(rs, 200, seed=3), shuffle_drawdowns(rs, 200, seed=3)
    assert a == b and a == sorted(a) and len(a) == 200


def test_report_flags_an_unusual_order_and_needs_30_trades():
    assert trade_shuffle_report([1.0] * 29) is None
    worst = [1.0] * 20 + [-1.0] * 20          # all losses at the end: drawdown 20R in this order...
    rep = trade_shuffle_report(worst)
    assert rep["original_dd_r"] == 20.0 and rep["original_percentile"] > 0.9   # ...which is worse than almost every shuffle
    smooth = [1.0, -1.0] * 20                  # alternating: drawdown 1R, better than almost every shuffle
    assert trade_shuffle_report(smooth)["original_percentile"] < 0.1
