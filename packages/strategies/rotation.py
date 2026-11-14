"""Weekly cross-sectional rotation simulator for hypothesis H1 (ADR-032). Pure functions, no I/O.

Prices are daily closes keyed by day index (UTC day number since 1970-01-01). A rebalance "on day t" happens at
00:00 UTC of day t, decides with closes of days <= t-1 only, and trades at the close of day t-1 (the same instant).
The position is held until the next rebalance; in between, weights drift with prices.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Mapping, Sequence

DAY_MS = 86_400_000
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def weekday_of(day: int) -> int:
    """0 = Monday. Day 0 (1970-01-01) was a Thursday."""
    return (day + 3) % 7


def ema_by_day(closes: Mapping[int, float], n: int) -> dict[int, float]:
    out, prev, k = {}, None, 2.0 / (n + 1)
    for d in sorted(closes):
        prev = closes[d] if prev is None else closes[d] * k + prev * (1 - k)
        out[d] = prev
    return out


@dataclass(frozen=True)
class RotationParams:
    top_k: int = 3
    lookback: int = 28
    min_history: int = 60
    ema_gate: int = 50
    fee: float = 0.0010
    slippage: float = 0.0005
    hold_days: int = 7


def score(closes: Mapping[int, float], t: int, p: RotationParams) -> float | None:
    """Volatility-adjusted momentum on closes up to day t-1, or None if the symbol is not eligible."""
    if sum(1 for d in closes if d < t) < p.min_history:
        return None
    window = [closes.get(d) for d in range(t - 1 - p.lookback, t)]
    if any(c is None or c <= 0 for c in window):
        return None
    rets = [math.log(window[i] / window[i - 1]) for i in range(1, len(window))]
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
    if sd <= 0:
        return None
    return math.log(window[-1] / window[0]) / sd


def _price_at(closes: Mapping[int, float], d: int, floor: int) -> float | None:
    """Close of day d, or the last close after `floor` if day d is missing (gap or delisting)."""
    for x in range(d, floor - 1, -1):
        if x in closes:
            return closes[x]
    return None


@dataclass
class Week:
    day: int
    weights: dict[str, float]
    turnover: float
    cost: float
    gross: float
    net: float
    gate_on: bool


@dataclass
class RunResult:
    weeks: list[Week] = field(default_factory=list)

    @property
    def returns(self) -> list[float]:
        return [w.net for w in self.weeks]


def simulate(panel: Mapping[str, Mapping[int, float]], btc: Mapping[int, float], first_day: int, last_day: int,
             weekday: int, p: RotationParams, mode: str = "rotation") -> RunResult:
    """mode 'rotation' = H1; 'btc_gate' = 100% BTC when the gate is on; 'btc_hold' = always 100% BTC."""
    ema = ema_by_day(btc, p.ema_gate)
    cost_rate = p.fee + p.slippage
    t = first_day
    while weekday_of(t) != weekday:
        t += 1
    held: dict[str, float] = {}
    res = RunResult()
    while t + p.hold_days - 1 <= last_day:
        b_close, b_ema = btc.get(t - 1), ema.get(t - 1)
        gate = b_close is not None and b_ema is not None and b_close > b_ema
        if mode == "btc_hold":
            target = {"BTCUSDT": 1.0}
        elif mode == "btc_gate":
            target = {"BTCUSDT": 1.0} if gate else {}
        elif not gate:
            target = {}
        else:
            scored = [(s, sym) for sym, cl in panel.items() if (s := score(cl, t, p)) is not None]
            scored.sort(key=lambda x: (-x[0], x[1]))
            top = [sym for _, sym in scored[: p.top_k]]
            target = {sym: 1.0 / len(top) for sym in top} if top else {}
        names = set(target) | set(held)
        turnover = sum(abs(target.get(n, 0.0) - held.get(n, 0.0)) for n in names)
        cost = turnover * cost_rate
        end = t + p.hold_days - 1
        gross, grown = 0.0, {}
        for sym, w in target.items():
            series = btc if sym == "BTCUSDT" and sym not in panel else panel[sym]
            p0, p1 = series.get(t - 1), _price_at(series, end, t - 1)
            r = (p1 / p0 - 1.0) if p0 and p1 else 0.0
            gross += w * r
            grown[sym] = w * (1.0 + r)
        total = (1.0 - sum(target.values())) + sum(grown.values())
        held = {s: v / total for s, v in grown.items()} if total > 0 else {}
        net = (1.0 - cost) * (1.0 + gross) - 1.0
        res.weeks.append(Week(t, target, turnover, cost, gross, net, gate))
        t += p.hold_days
    return res


# ------------------------------------------------------------------------------------------------ statistics
def sharpe(rets: Sequence[float], periods: float = 52.0) -> float:
    if len(rets) < 2:
        return 0.0
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
    return m / sd * math.sqrt(periods) if sd > 1e-12 else 0.0


def equity(rets: Sequence[float]) -> list[float]:
    nav, out = 1.0, []
    for r in rets:
        nav *= 1.0 + r
        out.append(nav)
    return out


def max_drawdown(rets: Sequence[float]) -> float:
    peak, dd = 1.0, 0.0
    for v in equity(rets):
        peak = max(peak, v)
        dd = max(dd, 1.0 - v / peak)
    return dd


def cagr(rets: Sequence[float], periods: float = 52.1775) -> float:
    if not rets:
        return 0.0
    nav = equity(rets)[-1]
    return nav ** (periods / len(rets)) - 1.0 if nav > 0 else -1.0


def block_bootstrap_mean_ci(xs: Sequence[float], block: int = 4, n_boot: int = 10_000, seed: int = 7,
                            alpha: float = 0.05) -> tuple[float, float]:
    """Circular moving-block bootstrap of the mean (keeps week-to-week dependence). Returns (lower, upper)."""
    n = len(xs)
    if n < block * 2:
        return float("-inf"), float("inf")
    rng = random.Random(seed)
    k = math.ceil(n / block)
    means = []
    for _ in range(n_boot):
        tot, cnt = 0.0, 0
        for _ in range(k):
            s = rng.randrange(n)
            for j in range(block):
                if cnt == n:
                    break
                tot += xs[(s + j) % n]
                cnt += 1
        means.append(tot / n)
    means.sort()
    return means[int(alpha / 2 * n_boot)], means[int((1 - alpha / 2) * n_boot) - 1]
