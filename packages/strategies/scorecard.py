"""Scorecard: how close is a recipe to the goal, what is missing, and why.

Multiple-testing guard: the more recipes the lab has tried (k), the stricter the confidence bar. The bar is a one-sided
Bonferroni z for k trials, so a recipe is only called a pass if the LOWER confidence bound of its pooled avg R is above 0.
Goal values are PROVISIONAL and set by the user.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Mapping, Sequence

from packages.backtest.engine import Trade
from packages.backtest.metrics import max_drawdown_r, summarize, time_clustered_mean_se

TRIALS_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "lab_trials.json"
FAST_STOP_BARS = 2


@dataclass(frozen=True)
class Goal:
    min_avg_r: float = 0.20              # PROVISIONAL: pooled average R after fees and slippage
    min_profit_factor: float = 1.3       # PROVISIONAL
    max_negative_windows: int = 1        # PROVISIONAL: at most this many windows with avg R <= 0
    max_drawdown_r: float = 20.0         # PROVISIONAL: worst pooled drawdown in R
    min_pooled_trades: int = 100         # PROVISIONAL: below this the sample is too small to judge
    min_trades_per_window: int = 10      # a window with fewer trades is reported but not counted as evidence


def z_for_trials(k: int, alpha: float = 0.05) -> float:
    """One-sided z for confidence 1 - alpha/k (Bonferroni). k=1 -> 1.645, k=30 -> about 2.93."""
    k = max(1, int(k))
    return NormalDist().inv_cdf(1 - alpha / k)


def load_trial_count(path: Path = TRIALS_PATH) -> int:
    if path.exists():
        return len(json.loads(path.read_text(encoding="utf-8")).get("recipes", []))
    return 0


def register_trials(names: Sequence[str], path: Path = TRIALS_PATH) -> int:
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"recipes": []}
    for n in names:
        if n not in data["recipes"]:
            data["recipes"].append(n)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return len(data["recipes"])


def _mean_sd(xs: Sequence[float]) -> tuple[float, float]:
    n = len(xs)
    if n == 0:
        return 0.0, 0.0
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    return m, sd


def score_recipe(per_window: Mapping[str, Sequence[Trade]], goal: Goal = Goal(), trials: int = 1) -> dict:
    pooled = [t for ts in per_window.values() for t in ts]
    n = len(pooled)
    s = summarize(pooled, [], len(pooled), 30)
    mean, sd = _mean_sd([t.r_multiple for t in pooled])
    z = z_for_trials(trials)
    cl = time_clustered_mean_se(pooled)
    se_used = max(cl["se_naive"], cl["se_clustered"])  # never trust a bound narrower than the time-clustered one
    ci_lower = mean - z * se_used if n > 1 else float("-inf")
    ci_lower_naive = mean - z * cl["se_naive"] if n > 1 else float("-inf")
    avg_fee_r = sum(t.fee_r for t in pooled) / n if n else 0.0
    windows = {}
    for w, ts in per_window.items():
        m = sum(t.r_multiple for t in ts) / len(ts) if ts else 0.0
        windows[w] = {"trades": len(ts), "avg_r": round(m, 3)}
    counted = {w: v for w, v in windows.items() if v["trades"] >= goal.min_trades_per_window}
    negative = [w for w, v in counted.items() if v["avg_r"] <= 0]
    losses = [t for t in pooled if t.r_multiple <= 0]
    fast = [t for t in losses if t.bars_held <= FAST_STOP_BARS and t.exit_reason == "STOP"]
    timeouts = [t for t in pooled if t.exit_reason == "TIMEOUT"]
    pf = s.get("profit_factor")
    dd = max_drawdown_r(pooled) if pooled else 0.0

    unmet: list[str] = []
    if n < goal.min_pooled_trades:
        unmet.append(f"SAMPLE_TOO_SMALL: {n} trades < {goal.min_pooled_trades}")
    if mean < goal.min_avg_r:
        unmet.append(f"AVG_R: {mean:+.2f} < {goal.min_avg_r:+.2f}")
    if pf is None or pf < goal.min_profit_factor:
        unmet.append(f"PROFIT_FACTOR: {pf if pf is None else round(pf, 2)} < {goal.min_profit_factor}")
    if len(negative) > goal.max_negative_windows:
        unmet.append(f"STABILITY: negative in {len(negative)} windows {negative}")
    if dd > goal.max_drawdown_r:
        unmet.append(f"DRAWDOWN: {dd:.1f}R > {goal.max_drawdown_r}R")
    if ci_lower <= 0:
        unmet.append(f"CONFIDENCE: lower bound {ci_lower:+.2f}R <= 0 (z={z:.2f} for {trials} recipes tried, "
                     f"{cl['n_clusters']} weekly clusters)")

    causes: list[str] = []
    wr, be = s.get("win_rate"), s.get("breakeven_win_rate")
    if n and be is not None and wr is not None and wr < be:
        causes.append(f"WIN_RATE {wr:.0%} is below breakeven {be:.0%} (needs +{(be - wr) * 100:.0f} points)")
    if losses and len(fast) / len(losses) >= 0.40:
        causes.append(f"FAST_STOPS: {len(fast)}/{len(losses)} losses hit the stop within {FAST_STOP_BARS} candles (entry or stop placement)")
    if n and len(timeouts) / n >= 0.20:
        causes.append(f"TIMEOUTS: {len(timeouts)}/{n} trades went nowhere (the idea lacks momentum)")
    if n and s.get("avg_win_r", 0) and s["avg_win_r"] < 1.5:
        causes.append(f"SMALL_WINS: average win {s['avg_win_r']:.2f}R is too small against 1R risk")

    return {
        "trades": n, "avg_r": round(mean, 3), "ci_lower_r": round(ci_lower, 3) if n > 1 else None,
        "ci_lower_naive_r": round(ci_lower_naive, 3) if n > 1 else None,
        "n_clusters": cl["n_clusters"], "se_naive": round(cl["se_naive"], 4), "se_clustered": round(cl["se_clustered"], 4),
        "avg_fee_r": round(avg_fee_r, 3),
        "win_rate": wr, "breakeven_win_rate": be, "profit_factor": pf, "max_drawdown_r": round(dd, 2),
        "windows": windows, "negative_windows": negative, "meets_goal": not unmet,
        "unmet": unmet, "causes": causes,
        "criteria_met": 6 - len(unmet),
    }
