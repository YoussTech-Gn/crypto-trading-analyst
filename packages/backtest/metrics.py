"""Backtest statistics and an honest verdict (sample size first)."""

from __future__ import annotations

import math
from typing import Sequence

from packages.backtest.engine import Trade, UnfilledSignal


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


WEEK_MS = 7 * 86_400_000


def time_clustered_mean_se(trades: Sequence[Trade], bucket_ms: int = WEEK_MS) -> dict:
    """Mean R with a naive and a time-clustered standard error.

    Trades on different symbols that fill in the same calendar week share the same market move, so they are not
    independent. Trades are grouped by the week of their fill and the standard error of the mean uses the grouped
    (Liang-Zeger) variance: G/(G-1) * sum_g (S_g - n_g * mean)^2 / n^2. A calendar bucket is used on purpose:
    chaining overlapping holding periods merges almost everything into a few huge clusters.
    """
    n = len(trades)
    if n < 2:
        return {"n": n, "mean": trades[0].r_multiple if n else 0.0, "n_clusters": n, "se_naive": 0.0, "se_clustered": 0.0}
    rs = [t.r_multiple for t in trades]
    mean = sum(rs) / n
    sd = math.sqrt(sum((r - mean) ** 2 for r in rs) / (n - 1))
    se_naive = sd / math.sqrt(n)
    groups: dict[int, list[float]] = {}
    for t in trades:
        groups.setdefault(t.fill_time_ms // bucket_ms, []).append(t.r_multiple)
    g = len(groups)
    if g < 2:
        return {"n": n, "mean": mean, "n_clusters": g, "se_naive": se_naive, "se_clustered": se_naive}
    ss = sum((sum(v) - len(v) * mean) ** 2 for v in groups.values())
    se_cl = math.sqrt(g / (g - 1) * ss) / n
    return {"n": n, "mean": mean, "n_clusters": g, "se_naive": se_naive, "se_clustered": se_cl}


def max_drawdown_r(trades: Sequence[Trade]) -> float:
    peak = cum = worst = 0.0
    for t in sorted(trades, key=lambda x: (x.exit_time_ms, x.symbol)):
        cum += t.r_multiple
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return worst


def max_consecutive_losses(trades: Sequence[Trade]) -> int:
    best = cur = 0
    for t in sorted(trades, key=lambda x: (x.exit_time_ms, x.symbol)):
        cur = cur + 1 if t.r_multiple <= 0 else 0
        best = max(best, cur)
    return best


def summarize(trades: Sequence[Trade], unfilled: Sequence[UnfilledSignal], signals: int, min_trades: int) -> dict:
    n = len(trades)
    wins = [t for t in trades if t.r_multiple > 0]
    losses = [t for t in trades if t.r_multiple <= 0]
    avg_r = sum(t.r_multiple for t in trades) / n if n else 0.0
    gross_win = sum(t.r_multiple for t in wins)
    gross_loss = -sum(t.r_multiple for t in losses)
    pf = gross_win / gross_loss if gross_loss > 0 else None
    wr = len(wins) / n if n else 0.0
    lo, hi = wilson_interval(len(wins), n)
    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    breakeven_wr = avg_loss / (avg_win + avg_loss) if (avg_win + avg_loss) > 0 else None
    by_reason: dict[str, int] = {}
    for t in trades:
        by_reason[t.exit_reason] = by_reason.get(t.exit_reason, 0) + 1
    by_symbol: dict[str, dict] = {}
    for t in trades:
        d = by_symbol.setdefault(t.symbol, {"trades": 0, "total_r": 0.0})
        d["trades"] += 1
        d["total_r"] += t.r_multiple
    top_share = max((v["trades"] for v in by_symbol.values()), default=0) / n if n else 0.0
    warnings: list[str] = []
    if n < min_trades:
        verdict = "INSUFFICIENT_SAMPLE"
        warnings.append(f"only {n} trades (< {min_trades}): do not draw conclusions")
    elif avg_r <= 0:
        verdict = "NEGATIVE"
    elif breakeven_wr is not None and lo > breakeven_wr:
        verdict = "PROMISING"
    else:
        verdict = "MARGINAL"
    if n and top_share > 0.5:
        warnings.append("more than half of the trades come from one symbol")
    warnings.append("single historical period, parameters not tuned or validated out-of-sample: not proof of edge")
    missed_w = sum(1 for u in unfilled if u.missed_winner)
    return {
        "verdict": verdict,
        "signals": signals,
        "filled_trades": n,
        "unfilled": len(unfilled),
        "fill_rate": n / (n + len(unfilled)) if (n + len(unfilled)) else None,
        "unfilled_missed_winners": missed_w,
        "wins": len(wins), "losses": len(losses),
        "win_rate": wr, "win_rate_wilson95": [lo, hi],
        "avg_r": avg_r, "total_r": sum(t.r_multiple for t in trades),
        "avg_win_r": avg_win, "avg_loss_r": avg_loss,
        "breakeven_win_rate": breakeven_wr,
        "profit_factor": pf,
        "max_drawdown_r": max_drawdown_r(trades),
        "max_consecutive_losses": max_consecutive_losses(trades),
        "avg_bars_held": sum(t.bars_held for t in trades) / n if n else 0.0,
        "exit_reasons": by_reason,
        "per_symbol": by_symbol,
        "top_symbol_trade_share": top_share,
        "min_trades_required": min_trades,
        "warnings": warnings,
    }
