"""Trade-order shuffling Monte Carlo (idea from Jesse's `monte_carlo_trades`; our own implementation, ADR-041).

The individual trade results stay the same; only their ORDER is randomised, and the drawdown of each shuffled path is
measured. It answers one question: was the historical drawdown typical, or did the strategy get a lucky (or unlucky)
sequence? It cannot create or remove edge: the average R is identical in every scenario.

Caveat (stated in the report): real losses cluster (many coins fall on the same day). Shuffling scatters those clusters, so
the shuffled drawdowns tend to look SMALLER than reality. Treat the 95th percentile as a lower bound of the risk.
"""

from __future__ import annotations

import random
from typing import Sequence

MC_SCENARIOS = 1000  # Jesse recommends at least 1000 for trade-order shuffling
MC_SEED = 7


def path_drawdown(rs: Sequence[float]) -> float:
    peak = cum = worst = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return worst


def shuffle_drawdowns(rs: Sequence[float], n: int = MC_SCENARIOS, seed: int = MC_SEED) -> list[float]:
    rng = random.Random(seed)
    xs = list(rs)
    out = []
    for _ in range(n):
        rng.shuffle(xs)
        out.append(path_drawdown(xs))
    out.sort()
    return out


def trade_shuffle_report(rs_in_time_order: Sequence[float], n: int = MC_SCENARIOS, seed: int = MC_SEED) -> dict | None:
    """Original drawdown vs the shuffled distribution. None when there are too few trades to say anything (< 30)."""
    if len(rs_in_time_order) < 30:
        return None
    original = path_drawdown(rs_in_time_order)
    dist = shuffle_drawdowns(rs_in_time_order, n, seed)
    q = lambda p: dist[min(len(dist) - 1, int(p * len(dist)))]
    rank = sum(1 for d in dist if d < original) / len(dist)
    return {"scenarios": n, "original_dd_r": round(original, 2), "median_dd_r": round(q(0.5), 2),
            "p95_dd_r": round(q(0.95), 2), "worst_dd_r": round(dist[-1], 2),
            "original_percentile": round(rank, 3)}
