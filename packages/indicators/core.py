"""Indicator formulas. Every function returns a list aligned 1:1 with the input; positions
without enough history are None. Values at index i use only inputs at indexes <= i."""

from __future__ import annotations

import math
from typing import Sequence


def _check(values: Sequence[float], period: int, name: str) -> None:
    if period < 1:
        raise ValueError(f"{name}: period must be >= 1")
    for v in values:
        if not math.isfinite(v):
            raise ValueError(f"{name}: non-finite input value")


def ema(values: Sequence[float], period: int) -> list[float | None]:
    """EMA seeded with the SMA of the first `period` values; k = 2/(period+1)."""
    _check(values, period, "ema")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    k = 2.0 / (period + 1)
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev
    return out


def rsi(closes: Sequence[float], period: int = 14) -> list[float | None]:
    """Wilder RSI. First value at index `period` (average of the first `period` changes)."""
    _check(closes, period, "rsi")
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def value(g: float, l: float) -> float:
        if l == 0.0:
            return 50.0 if g == 0.0 else 100.0
        return 100.0 - 100.0 / (1.0 + g / l)

    out[period] = value(avg_gain, avg_loss)
    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = value(avg_gain, avg_loss)
    return out


def atr(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14
) -> list[float | None]:
    """Wilder ATR. TR[0] = high-low; TR[i] = max(h-l, |h-prev_close|, |l-prev_close|).
    First ATR at index period-1 = mean(TR[0..period-1]); then Wilder smoothing."""
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("atr: highs, lows and closes must have equal length")
    _check(highs, period, "atr")
    _check(lows, period, "atr")
    _check(closes, period, "atr")
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    tr = [highs[0] - lows[0]]
    for i in range(1, n):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    prev = sum(tr[:period]) / period
    out[period - 1] = prev
    for i in range(period, n):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


def relative_volume(volumes: Sequence[float], period: int = 20) -> list[float | None]:
    """volume[i] / mean(volume[i-period .. i-1]) (current candle excluded). None if mean is 0."""
    _check(volumes, period, "relative_volume")
    out: list[float | None] = [None] * len(volumes)
    for i in range(period, len(volumes)):
        mean = sum(volumes[i - period : i]) / period
        out[i] = volumes[i] / mean if mean > 0 else None
    return out
