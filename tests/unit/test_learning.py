import numpy as np
import pytest

from packages.learning.dataset import barrier_label, bars_since, rolling_prev, xs_rank
from packages.learning.model import FrequencyTable, Logistic, clustered_mean_ci, one_position_per_symbol, weighted_auc, H4


def test_barrier_label_stop_wins_ties_and_fees_are_charged():
    n = 40
    o = np.full(n, 100.0); h = np.full(n, 100.5); l = np.full(n, 99.5); c = np.full(n, 100.0); atr = np.full(n, 1.0)
    h[3], l[3] = 103.0, 98.0                         # candle t+3 touches both barriers of row t=0
    r = barrier_label(o, h, l, c, atr, 2.0, 1.5)
    stop_px = 98.5 * (1 - 0.0005)
    assert r[0] == pytest.approx((stop_px - 100) / 1.5 - 0.001 * (100 + stop_px) / 1.5)
    assert np.isnan(r[-1])                           # no full horizon ahead (no next open)


def test_barrier_label_target_and_timeout():
    n = 40
    o = np.full(n, 100.0); h = np.full(n, 100.5); l = np.full(n, 99.5); c = np.full(n, 100.2); atr = np.full(n, 1.0)
    h[5] = 102.5
    r = barrier_label(o, h, l, c, atr, 2.0, 1.5)
    assert r[0] == pytest.approx((102 - 100) / 1.5 - 0.001 * 202 / 1.5)
    assert r[6] == pytest.approx((100.2 - 100) / 1.5 - 0.001 * 200.2 / 1.5)   # nothing hit: exit at close[t+30]


def test_features_use_only_previous_candles():
    x = np.arange(30, dtype=float)
    assert rolling_prev(x, 20, np.max)[25] == 24.0     # max of x[5..24], excludes x[25]
    s, last = bars_since(np.array([False, True, False, False]))
    assert list(s) == [50, 0, 1, 2] and list(last) == [-1, 1, 1, 1]


def test_cross_sectional_rank_is_per_timestamp():
    t = np.array([1, 1, 1, 2, 2])
    r = xs_rank(t, np.array([3.0, 1.0, 2.0, 5.0, 4.0]))
    assert list(r) == pytest.approx([1.0, 1 / 3, 2 / 3, 1.0, 0.5])


def test_auc_basics():
    y = np.array([0, 0, 1, 1.0])
    assert weighted_auc(np.array([0.1, 0.2, 0.8, 0.9]), y) == 1.0
    assert weighted_auc(np.array([0.5, 0.5, 0.5, 0.5]), y) == 0.5
    assert weighted_auc(np.array([0.1, 0.9, 0.8, 0.2]), y, np.array([1, 0, 1, 1.0])) == 1.0   # weight 0 removes the 0.9 negative


def test_logistic_learns_a_real_signal_and_not_noise():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(4000, 3))
    y = (rng.random(4000) < 1 / (1 + np.exp(-1.5 * X[:, 0]))).astype(float)
    m = Logistic().fit(X[:3000], y[:3000], np.ones(3000))
    assert weighted_auc(m.predict(X[3000:]), y[3000:]) > 0.7
    m2 = Logistic().fit(X[:3000], rng.permutation(y[:3000]), np.ones(3000))
    assert abs(weighted_auc(m2.predict(X[3000:]), y[3000:]) - 0.5) < 0.06


def test_frequency_table_ignores_rare_buckets():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(3000, 2))
    y = (X[:, 0] > 0).astype(float)
    week = np.arange(3000) // 10
    ft = FrequencyTable([0, 1], min_weeks=25).fit(X, y, np.ones(3000), week)
    p = ft.predict(X)
    assert weighted_auc(p, y) > 0.8
    ft2 = FrequencyTable([0, 1], min_weeks=10_000).fit(X, y, np.ones(3000), week)
    assert np.allclose(ft2.predict(X), ft2.base)


def test_one_position_per_symbol_and_clustered_ci():
    t = np.array([0, 5, 40, 0]) * H4
    s = np.array([0, 0, 0, 1])
    kept = one_position_per_symbol(np.array([0, 3, 1, 2]), t, s)
    assert list(kept) == [0, 3, 2]
    m, lo, hi, g = clustered_mean_ci(np.array([1.0, -1.0, 1.0, 1.0]), np.array([0, 0, 1, 2]) * 7 * 86_400_000)
    assert m == 0.5 and lo < m < hi and g == 3
