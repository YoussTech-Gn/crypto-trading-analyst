"""Liquidity levels and sweeps.

Sell-side levels (below price): SWING_LOW, EQUAL_LOWS, PREV_DAY_LOW. Buy-side levels are
listed for context but sweeps are only detected on sell-side levels (LONG-only scope).

Sweep rule (candle j, closed): the level is active from `active_from_index`. At the first
candle with low < level:
  * penetration < min_sweep_penetration_pct          -> a touch; level stays active;
  * penetration >= min and close > level (reclaim)    -> SWEEP (confirmed, candle closed);
  * penetration >= min and close <= level             -> level BROKEN, no sweep.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from packages.market_data.models import Candle
from packages.market_structure.swings import Swing

DAY_MS = 86_400_000
SELL_SIDE = ("SWING_LOW", "EQUAL_LOWS", "PREV_DAY_LOW")


@dataclass(frozen=True)
class LiquidityLevel:
    kind: str
    price: float
    source_index: int  # index (in the series it was built from) of the defining candle/swing
    active_from_index: int  # first candle index of the analysed series that may sweep it
    known_time_ms: int  # when the level became knowable (close time)
    expires_index: int | None = None  # first candle index where the level no longer applies


@dataclass(frozen=True)
class LiquiditySweep:
    level: LiquidityLevel
    sweep_index: int
    sweep_time_ms: int  # open time of the sweep candle
    sweep_close_time_ms: int
    penetration_pct: float
    sweep_low: float
    sweep_close: float
    status: str = "CONFIRMED"


def build_swing_levels(swings: Sequence[Swing], tolerance_pct: float) -> list[LiquidityLevel]:
    levels: list[LiquidityLevel] = []
    for kind_swing, kind_single, kind_equal in (
        ("LOW", "SWING_LOW", "EQUAL_LOWS"),
        ("HIGH", "SWING_HIGH", "EQUAL_HIGHS"),
    ):
        group = sorted((s for s in swings if s.kind == kind_swing), key=lambda s: s.index)
        for s in group:
            levels.append(LiquidityLevel(kind_single, s.price, s.index, s.confirmed_index + 1, s.confirmed_time_ms))
        for a, b in zip(group, group[1:]):
            if abs(a.price - b.price) / a.price * 100.0 <= tolerance_pct:
                price = min(a.price, b.price) if kind_swing == "LOW" else max(a.price, b.price)
                levels.append(LiquidityLevel(kind_equal, price, b.index, b.confirmed_index + 1, b.confirmed_time_ms))
    return levels


def previous_day_levels(setup_candles: Sequence[Candle], daily_candles: Sequence[Candle]) -> list[LiquidityLevel]:
    """Previous UTC day high/low, active from the first setup candle of each day."""
    by_open = {c.open_time_ms: c for c in daily_candles}
    levels: list[LiquidityLevel] = []
    first_idx: dict[int, int] = {}
    for j, c in enumerate(setup_candles):
        first_idx.setdefault(c.open_time_ms - c.open_time_ms % DAY_MS, j)
    for day, j in first_idx.items():
        prev = by_open.get(day - DAY_MS)
        if prev is None:
            continue
        end = first_idx.get(day + DAY_MS)  # None = runs to the end of the series
        levels.append(LiquidityLevel("PREV_DAY_LOW", prev.low, j, j, prev.close_time_ms, end))
        levels.append(LiquidityLevel("PREV_DAY_HIGH", prev.high, j, j, prev.close_time_ms, end))
    return levels


def detect_sweeps(
    candles: Sequence[Candle], levels: Sequence[LiquidityLevel], min_penetration_pct: float
) -> list[LiquiditySweep]:
    sweeps: list[LiquiditySweep] = []
    for lv in levels:
        if lv.kind not in SELL_SIDE:
            continue
        stop = len(candles) if lv.expires_index is None else min(lv.expires_index, len(candles))
        for j in range(lv.active_from_index, stop):
            c = candles[j]
            if not c.low < lv.price:
                continue
            pen = (lv.price - c.low) / lv.price * 100.0
            if pen < min_penetration_pct:
                continue  # a touch, not a sweep
            if c.close > lv.price:
                sweeps.append(
                    LiquiditySweep(lv, j, c.open_time_ms, c.close_time_ms, pen, c.low, c.close)
                )
            break  # swept or broken: the level is spent either way
    return sorted(sweeps, key=lambda s: (s.sweep_index, s.level.kind, s.level.price))


_PRIORITY = {"PREV_DAY_LOW": 0, "EQUAL_LOWS": 1, "SWING_LOW": 2}


def dedupe_levels(levels: Sequence[LiquidityLevel], rel_tol: float = 1e-9) -> list[LiquidityLevel]:
    """Merge sell-side levels at the same price (keep highest-priority kind, earliest activation)."""
    out: list[LiquidityLevel] = []
    for lv in sorted(levels, key=lambda l: (l.price, _PRIORITY.get(l.kind, 9), l.active_from_index)):
        if lv.kind in SELL_SIDE and out and out[-1].kind in SELL_SIDE and abs(out[-1].price - lv.price) <= rel_tol * lv.price and out[-1].expires_index == lv.expires_index:
            keep = out[-1]
            if lv.active_from_index < keep.active_from_index:
                out[-1] = LiquidityLevel(keep.kind, keep.price, keep.source_index, lv.active_from_index, lv.known_time_ms, keep.expires_index)
            continue
        out.append(lv)
    return out


def group_sweeps(sweeps: Sequence[LiquiditySweep]) -> list[dict]:
    """One event per sweep candle: all swept levels, deepest penetration."""
    by_candle: dict[int, list[LiquiditySweep]] = {}
    for sw in sweeps:
        by_candle.setdefault(sw.sweep_index, []).append(sw)
    events = []
    for idx in sorted(by_candle):
        grp = by_candle[idx]
        deepest = max(grp, key=lambda g: g.penetration_pct)
        uniq: dict[float, LiquiditySweep] = {}
        for g in sorted(grp, key=lambda g: _PRIORITY.get(g.level.kind, 9)):
            uniq.setdefault(round(g.level.price, 8), g)  # same price: keep highest-priority kind
        grp = sorted(uniq.values(), key=lambda g: g.level.price)
        events.append({
            "sweep_index": idx,
            "sweep_time_ms": grp[0].sweep_time_ms,
            "sweep_close_time_ms": grp[0].sweep_close_time_ms,
            "levels": [{"kind": g.level.kind, "price": g.level.price, "penetration_pct": g.penetration_pct} for g in grp],
            "deepest_level_kind": deepest.level.kind,
            "deepest_penetration_pct": deepest.penetration_pct,
            "sweep_low": grp[0].sweep_low,
            "sweep_close": grp[0].sweep_close,
        })
    return events
