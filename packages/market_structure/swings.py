"""Market structure (deterministic, closed candles only).

Swing HIGH at index i: high[i] is strictly greater than the highs of the `lookback` candles
before AND after it. Swing LOW is the mirror image. A swing is only KNOWN once the candle at
confirmed_index = i + lookback has closed. Nothing here reads candles after that index.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from packages.market_data.models import Candle


@dataclass(frozen=True)
class Swing:
    kind: str  # "HIGH" | "LOW"
    index: int
    price: float
    time_ms: int  # open time of the swing candle
    confirmed_index: int
    confirmed_time_ms: int  # close time of the confirming candle
    label: str = ""  # HH/LH/EQH or HL/LL/EQL, "FIRST" for the first of its kind


@dataclass(frozen=True)
class StructureBreak:
    direction: str  # "UP" (close above a swing high) | "DOWN" (close below a swing low)
    broken_swing_index: int
    level: float
    break_index: int
    break_time_ms: int  # open time of the breaking candle
    break_close_time_ms: int


@dataclass(frozen=True)
class TrendAssessment:
    bullish: bool
    failed_conditions: tuple[str, ...]
    evidence: dict


def detect_swings(candles: Sequence[Candle], lookback: int) -> list[Swing]:
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    n = len(candles)
    swings: list[Swing] = []
    for i in range(lookback, n - lookback):
        window_left = candles[i - lookback : i]
        window_right = candles[i + 1 : i + lookback + 1]
        c = candles[i]
        confirm = candles[i + lookback]
        if all(c.high > x.high for x in window_left) and all(c.high > x.high for x in window_right):
            swings.append(Swing("HIGH", i, c.high, c.open_time_ms, i + lookback, confirm.close_time_ms))
        if all(c.low < x.low for x in window_left) and all(c.low < x.low for x in window_right):
            swings.append(Swing("LOW", i, c.low, c.open_time_ms, i + lookback, confirm.close_time_ms))
    return swings


def label_swings(swings: Sequence[Swing]) -> list[Swing]:
    """Label each swing against the previous swing of the same kind."""
    last: dict[str, float] = {}
    out: list[Swing] = []
    for sw in sorted(swings, key=lambda s: (s.index, s.kind)):
        prev = last.get(sw.kind)
        if prev is None:
            label = "FIRST"
        elif sw.kind == "HIGH":
            label = "HH" if sw.price > prev else ("LH" if sw.price < prev else "EQH")
        else:
            label = "HL" if sw.price > prev else ("LL" if sw.price < prev else "EQL")
        last[sw.kind] = sw.price
        out.append(replace(sw, label=label))
    return out


def detect_breaks(candles: Sequence[Candle], swings: Sequence[Swing]) -> list[StructureBreak]:
    """Break of Structure: first CLOSE beyond a confirmed swing level after its confirmation."""
    breaks: list[StructureBreak] = []
    for sw in swings:
        for j in range(sw.confirmed_index + 1, len(candles)):
            c = candles[j]
            if sw.kind == "HIGH" and c.close > sw.price:
                breaks.append(StructureBreak("UP", sw.index, sw.price, j, c.open_time_ms, c.close_time_ms))
                break
            if sw.kind == "LOW" and c.close < sw.price:
                breaks.append(StructureBreak("DOWN", sw.index, sw.price, j, c.open_time_ms, c.close_time_ms))
                break
    return sorted(breaks, key=lambda b: (b.break_index, b.direction))


def assess_daily_trend(
    candles: Sequence[Candle],
    labeled_swings: Sequence[Swing],
    ema_fast: float | None,
    ema_slow: float | None,
    min_confirmed_swings: int,
) -> TrendAssessment:
    """Bullish only if ALL conditions pass (evaluated on the last closed candle):
    ENOUGH_SWINGS, LAST_HIGH_IS_HH, LAST_LOW_IS_HL, EMA_AVAILABLE, CLOSE_ABOVE_EMA_FAST,
    EMA_FAST_ABOVE_SLOW, NOT_INVALIDATED (last close >= latest swing low)."""
    failed: list[str] = []
    highs = [s for s in labeled_swings if s.kind == "HIGH"]
    lows = [s for s in labeled_swings if s.kind == "LOW"]
    last = candles[-1]
    if len(highs) < min_confirmed_swings or len(lows) < min_confirmed_swings:
        failed.append("ENOUGH_SWINGS")
    else:
        if highs[-1].label != "HH":
            failed.append("LAST_HIGH_IS_HH")
        if lows[-1].label != "HL":
            failed.append("LAST_LOW_IS_HL")
        if last.close < lows[-1].price:
            failed.append("NOT_INVALIDATED")
    if ema_fast is None or ema_slow is None:
        failed.append("EMA_AVAILABLE")
    else:
        if not last.close > ema_fast:
            failed.append("CLOSE_ABOVE_EMA_FAST")
        if not ema_fast > ema_slow:
            failed.append("EMA_FAST_ABOVE_SLOW")
    evidence = {
        "last_candle_open_time_ms": last.open_time_ms,
        "last_close": last.close,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "last_swing_high": highs[-1].price if highs else None,
        "last_swing_high_label": highs[-1].label if highs else None,
        "last_swing_low": lows[-1].price if lows else None,
        "last_swing_low_label": lows[-1].label if lows else None,
    }
    return TrendAssessment(not failed, tuple(failed), evidence)
