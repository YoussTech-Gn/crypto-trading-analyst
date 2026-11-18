import numpy as np

from packages.backtest.bias import lookahead_features, recursive_features
from packages.learning.dataset import SymbolFrame, build_symbol, shift

H4, D = 14_400_000, 86_400_000


def synthetic(n4=1400, seed=3):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n4)))
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.005, n4))
    l = np.minimum(o, c) * (1 - rng.uniform(0, 0.005, n4))
    v = rng.uniform(800, 1200, n4)
    t = np.arange(n4, dtype=np.int64) * H4
    a4 = {"open_time": t, "close_time": t + H4 - 1, "o": o, "h": h, "l": l, "c": c, "v": v}
    nd = n4 // 6
    dt = np.arange(nd, dtype=np.int64) * D
    dc = c[5::6][:nd]
    a1 = {"open_time": dt, "close_time": dt + D - 1, "o": dc, "h": dc * 1.01, "l": dc * 0.99, "c": dc, "v": np.full(nd, 1e4)}
    return a4, a1


def test_learning_features_do_not_look_ahead():
    a4, a1 = synthetic()
    bad = lookahead_features(build_symbol, a4, a1, [300, 555, 801, 1100, 1399])
    assert all(v == 0 for v in bad.values()), {k: v for k, v in bad.items() if v}


def test_the_checker_catches_a_feature_that_uses_the_future():
    def leaky(sym, a4, a1):
        f = build_symbol(sym, a4, a1)
        X = dict(f.X)
        X["next_close"] = shift(a4["c"], -1)  # deliberately peeks at the next candle
        return SymbolFrame(f.symbol, f.open_time, X, f.y_r, f.y2_r, f.ret18, f.valid)
    a4, a1 = synthetic()
    bad = lookahead_features(leaky, a4, a1, [300, 700, 1100])
    assert bad["next_close"] == 3 and bad["rsi14"] == 0


def test_warm_up_sensitivity_is_reported_and_small_for_long_startups():
    a4, a1 = synthetic()
    rf = recursive_features(build_symbol, a4, a1, startups=(500, 1000))
    assert "dist_ema50_atr" in rf
    assert rf["roc6"] == 0.0                     # non-recursive features do not depend on the start
    assert rf["dist_ema50_atr"] < 1e-3           # EMA50 after 500 candles has forgotten its start


def test_recipe_decisions_do_not_depend_on_the_window_length():
    from packages.analysis import AnalysisEngine
    from packages.backtest.bias import recursive_decisions
    from packages.config.settings import load_config
    from packages.market_data.models import Candle
    from packages.strategies import build_recipes
    a4, a1 = synthetic(n4=3200, seed=11)
    mk = lambda tf, a: [Candle("X", tf, int(t), int(ct), float(o), float(h), float(l), float(c), float(v), float(v * c), 100)
                        for t, ct, o, h, l, c, v in zip(a["open_time"], a["close_time"], a["o"], a["h"], a["l"], a["c"], a["v"])]
    setup, daily = mk("4h", a4), mk("1d", a1)
    cfg = load_config()
    rd = recursive_decisions(AnalysisEngine(cfg.analysis), build_recipes(cfg, ["sweep_only", "brk55_trail"]), "X", daily, setup,
                             range(len(setup) - 10, len(setup)))
    assert rd["sweep_only"]["steps"] == 10 and rd["sweep_only"]["changed"] == 0
