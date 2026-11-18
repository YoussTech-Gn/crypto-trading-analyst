"""Look-ahead and warm-up (recursive) bias checks (idea from Freqtrade's `lookahead-analysis` / `recursive-analysis`;
our own implementation, ADR-041).

1. Look-ahead (learning features): a feature of candle k must be identical whether it is computed on the full history or on
   history cut right after candle k. Any difference means the feature used the future.
2. Warm-up / recursive (learning features): recursive indicators (EMA, Wilder ATR/RSI) depend on where the series starts.
   We compute the last candle's features with different amounts of history (like Freqtrade's startup candles 199/499/999)
   and report the largest relative difference.
3. Warm-up (recipe decisions): the same recipe on the same closed candle, analysed with a short and a long window, must give
   the same decision; the share of decisions that change is reported.
"""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

import numpy as np

STARTUPS = (200, 500, 1000)


def _cut(a4: Mapping[str, np.ndarray], a1: Mapping[str, np.ndarray], k: int, start: int = 0):
    """4H candles start..k, and only the daily candles CLOSED by the close of 4H candle k."""
    t4 = {key: v[start:k + 1] for key, v in a4.items()}
    close_k = a4["close_time"][k]
    m = a1["close_time"] <= close_k
    t1 = {key: v[m] for key, v in a1.items()}
    return t4, t1


def _same(a: float, b: float, rel: float = 1e-9) -> bool:
    if np.isnan(a) and np.isnan(b):
        return True
    if np.isnan(a) or np.isnan(b):
        return False
    return abs(a - b) <= rel * max(1.0, abs(a), abs(b))


def lookahead_features(builder: Callable, a4, a1, sample_idx: Sequence[int]) -> dict[str, int]:
    """Number of sampled candles whose feature changes when the future is removed (0 everywhere = no look-ahead)."""
    full = builder("X", a4, a1).X
    bad = {name: 0 for name in full}
    for k in sample_idx:
        cut = builder("X", *_cut(a4, a1, k)).X
        for name, col in full.items():
            if not _same(float(col[k]), float(cut[name][-1])):
                bad[name] += 1
    return bad


def recursive_features(builder: Callable, a4, a1, startups: Sequence[int] = STARTUPS) -> dict[str, float]:
    """Largest relative difference of each feature on the LAST candle when history is cut to each startup length.
    Startups longer than the available history are skipped. Base = the longest startup available."""
    n = len(a4["c"])
    usable = [s for s in startups if s < n]
    if len(usable) < 2:
        return {}
    k = n - 1
    vals = {s: builder("X", *_cut(a4, a1, k, start=k - s)).X for s in usable}
    base = vals[max(usable)]
    out = {}
    for name, col in base.items():
        b = float(col[-1])
        worst = 0.0
        for s in usable:
            v = float(vals[s][name][-1])
            if np.isnan(b) or np.isnan(v):
                worst = max(worst, 0.0 if np.isnan(b) and np.isnan(v) else float("inf"))
            else:
                worst = max(worst, abs(v - b) / max(abs(b), 1e-12))
        out[name] = worst
    return out


def recursive_decisions(engine, recipes: Mapping, symbol: str, daily, setup, steps: Sequence[int],
                        short=(300, 600), long=(450, 900)) -> dict[str, dict]:
    """For each recipe: on how many steps does the decision (SIGNAL/NO_TRADE and entry/stop) change between a short and a
    long analysis window? A non-zero rate means warm-up matters for that recipe."""
    out = {name: {"steps": 0, "changed": 0} for name in recipes}
    for t in steps:
        close_t = setup[t].close_time_ms
        k = sum(1 for d in daily if d.close_time_ms <= close_t)
        if t + 1 < long[1] or k < long[0]:
            continue
        a_s = engine.analyze(symbol, daily[k - short[0]:k], setup[t + 1 - short[1]:t + 1]).to_dict()
        a_l = engine.analyze(symbol, daily[k - long[0]:k], setup[t + 1 - long[1]:t + 1]).to_dict()
        for name, r in recipes.items():
            ds, dl = r.decide(a_s), r.decide(a_l)
            out[name]["steps"] += 1
            key = lambda d: (d.decision, None if d.entry is None else round(d.entry, 8), None if d.stop is None else round(d.stop, 8))
            if key(ds) != key(dl):
                out[name]["changed"] += 1
    return out
