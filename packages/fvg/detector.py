"""Bullish FVG: for candles C1, C2, C3 (indexes i-2, i-1, i) the gap exists when
Low(C3) > High(C1); interval [High(C1), Low(C3)]; known when C3 has closed.

Status after formation (evaluated on candles after C3, closed only; strongest wins):
  INVALIDATED : some close < lower boundary
  FILLED      : some low <= lower boundary (price traded through the whole gap)
  ENTERED     : some low <= upper boundary (price entered the gap)
  UNTOUCHED   : otherwise
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from packages.market_data.models import Candle

FVG_RULES = (
    "bullish: low(C3) > high(C1); gap=[high(C1), low(C3)]; "
    "entered: low<=upper; filled: low<=lower; invalidated: close<lower"
)


@dataclass(frozen=True)
class FairValueGap:
    index: int  # index of C3
    formed_time_ms: int  # close time of C3
    lower: float
    upper: float
    size: float
    size_pct_of_price: float
    size_in_atr: float | None
    status: str
    first_entry_index: int | None
    filled_index: int | None
    invalidated_index: int | None
    rule: str = FVG_RULES


def detect_bullish_fvgs(
    candles: Sequence[Candle], atr_values: Sequence[float | None] | None = None
) -> list[FairValueGap]:
    gaps: list[FairValueGap] = []
    for i in range(2, len(candles)):
        c1, c3 = candles[i - 2], candles[i]
        if not c3.low > c1.high:
            continue
        lower, upper = c1.high, c3.low
        entry = filled = invalid = None
        for k in range(i + 1, len(candles)):
            ck = candles[k]
            if entry is None and ck.low <= upper:
                entry = k
            if filled is None and ck.low <= lower:
                filled = k
            if invalid is None and ck.close < lower:
                invalid = k
        status = (
            "INVALIDATED" if invalid is not None
            else "FILLED" if filled is not None
            else "ENTERED" if entry is not None
            else "UNTOUCHED"
        )
        atr_i = atr_values[i] if atr_values is not None else None
        size = upper - lower
        gaps.append(
            FairValueGap(
                index=i,
                formed_time_ms=c3.close_time_ms,
                lower=lower,
                upper=upper,
                size=size,
                size_pct_of_price=size / c3.close * 100.0,
                size_in_atr=(size / atr_i) if atr_i else None,
                status=status,
                first_entry_index=entry,
                filled_index=filled,
                invalidated_index=invalid,
            )
        )
    return gaps
