"""Deterministic candle series validator.

Enforces PROJECT_SPEC.md Section 4.3, Rule 8, and Milestone 1 Clarifications #2 & #3:
- Separates unfinished (currently forming) candles from closed candles using UTC timestamps.
- Validates OHLCV numerical integrity (finite numbers, positive prices, non-negative volume,
  High >= max(Open, Close), Low <= min(Open, Close), High >= Low, valid candle duration).
- Detects out-of-order timestamps, duplicate open_time_ms, and missing internal candles.
- Clearly distinguishes:
  * UNFINISHED_CANDLE_FILTERED (normal separation of the currently forming bar)
  * DELAYED_CANDLE_AVAILABILITY (the most recently completed UTC bar closed within
    max_close_delay_seconds [default 300s / 5m] and is not yet present in closed candles)
  * STALE_DATA (the most recently completed UTC bar closed more than max_close_delay_seconds
    ago and is still missing, or data lags by more than one closed bar)
  * MISSING_CANDLES (internal sequence gaps between closed candles)
  * INSUFFICIENT_HISTORY (closed candle count < configured minimum: 200 for 1d, 500 for 4h)
- Blocks downstream analysis whenever any integrity, history, delay, or staleness issue exists.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Sequence

from packages.config.settings import TimeframesConfig
from packages.market_data.models import (
    Candle,
    CandleValidationIssue,
    CandleValidationResult,
    DataFreshnessStatus,
)

TIMEFRAME_INTERVAL_MS: dict[str, int] = {
    "1d": 86_400_000,
    "4h": 14_400_000,
}


class CandleValidator:
    """Validates historical and live 1D/4H candle series for integrity and freshness."""

    def __init__(self, timeframes_config: TimeframesConfig) -> None:
        self._config = timeframes_config

    def _required_min_candles(self, timeframe: str) -> int:
        tf = timeframe.strip().lower()
        if tf == "1d":
            return self._config.min_closed_candles_1d
        if tf == "4h":
            return self._config.min_closed_candles_4h
        raise ValueError(f"Unsupported timeframe '{timeframe}'. Expected '1d' or '4h'.")

    @staticmethod
    def _validate_single_candle(candle: Candle, interval_ms: int) -> list[CandleValidationIssue]:
        issues: list[CandleValidationIssue] = []
        numeric_fields = (
            ("open", candle.open),
            ("high", candle.high),
            ("low", candle.low),
            ("close", candle.close),
            ("volume", candle.volume),
            ("quote_volume", candle.quote_volume),
        )
        for name, value in numeric_fields:
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                issues.append(
                    CandleValidationIssue(
                        code="MALFORMED_CANDLE_DATA",
                        message=f"Non-finite value for {name} on candle {candle.open_time_ms}",
                        candle_open_time_ms=candle.open_time_ms,
                        details={"field": name},
                    )
                )
                return issues

        if candle.open <= 0 or candle.high <= 0 or candle.low <= 0 or candle.close <= 0:
            issues.append(
                CandleValidationIssue(
                    code="MALFORMED_CANDLE_DATA",
                    message=f"Non-positive OHLC price on candle {candle.open_time_ms}",
                    candle_open_time_ms=candle.open_time_ms,
                )
            )

        if candle.volume < 0 or candle.quote_volume < 0 or candle.trade_count < 0:
            issues.append(
                CandleValidationIssue(
                    code="MALFORMED_CANDLE_DATA",
                    message=f"Negative volume or trade_count on candle {candle.open_time_ms}",
                    candle_open_time_ms=candle.open_time_ms,
                )
            )

        if candle.high < max(candle.open, candle.close) or candle.low > min(candle.open, candle.close) or candle.high < candle.low:
            issues.append(
                CandleValidationIssue(
                    code="MALFORMED_CANDLE_DATA",
                    message=(
                        f"OHLC envelope violation on candle {candle.open_time_ms}: "
                        f"O={candle.open}, H={candle.high}, L={candle.low}, C={candle.close}"
                    ),
                    candle_open_time_ms=candle.open_time_ms,
                )
            )

        if candle.open_time_ms <= 0 or candle.close_time_ms <= candle.open_time_ms:
            issues.append(
                CandleValidationIssue(
                    code="MALFORMED_CANDLE_DATA",
                    message=f"Invalid candle timestamps: open={candle.open_time_ms}, close={candle.close_time_ms}",
                    candle_open_time_ms=candle.open_time_ms,
                )
            )
        else:
            # Binance klines have close_time_ms = open_time_ms + interval_ms - 1 (or exact boundary)
            duration_ms = candle.close_time_ms - candle.open_time_ms
            if duration_ms not in (interval_ms - 1, interval_ms):
                issues.append(
                    CandleValidationIssue(
                        code="MALFORMED_CANDLE_DATA",
                        message=(
                            f"Unexpected candle duration {duration_ms}ms for timeframe "
                            f"interval {interval_ms}ms at {candle.open_time_ms}"
                        ),
                        candle_open_time_ms=candle.open_time_ms,
                        details={"duration_ms": duration_ms, "expected_interval_ms": interval_ms},
                    )
                )

        if candle.open_time_ms % interval_ms != 0:
            issues.append(
                CandleValidationIssue(
                    code="MALFORMED_CANDLE_DATA",
                    message=(
                        f"Candle open_time_ms {candle.open_time_ms} is not aligned to "
                        f"UTC interval boundary ({interval_ms}ms)"
                    ),
                    candle_open_time_ms=candle.open_time_ms,
                )
            )

        return issues

    def validate(
        self,
        symbol: str,
        timeframe: str,
        candles: Sequence[Candle],
        reference_time_utc: datetime | None = None,
    ) -> CandleValidationResult:
        """Validate a sequence of candles as of `reference_time_utc` (defaults to current UTC time)."""
        tf = timeframe.strip().lower()
        if tf not in TIMEFRAME_INTERVAL_MS:
            raise ValueError(f"Unsupported timeframe '{timeframe}'. Expected '1d' or '4h'.")

        interval_ms = TIMEFRAME_INTERVAL_MS[tf]
        required_min = self._required_min_candles(tf)
        max_delay_sec = self._config.max_close_delay_seconds

        now_utc = reference_time_utc or datetime.now(timezone.utc)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        else:
            now_utc = now_utc.astimezone(timezone.utc)

        now_ms = int(now_utc.timestamp() * 1000)

        # Most recently completed UTC interval boundary at now_ms:
        expected_latest_close_boundary_ms = (now_ms // interval_ms) * interval_ms
        expected_latest_open_ms = expected_latest_close_boundary_ms - interval_ms
        expected_latest_close_ms = expected_latest_close_boundary_ms - 1

        issues: list[CandleValidationIssue] = []

        if not candles:
            issues.append(
                CandleValidationIssue(
                    code="EMPTY_DATASET",
                    message=f"No candles provided for {symbol} ({tf}).",
                )
            )
            return CandleValidationResult(
                symbol=symbol,
                timeframe=tf,
                evaluated_at_utc=now_utc,
                is_valid=False,
                analysis_allowed=False,
                freshness_status=DataFreshnessStatus.EMPTY_DATASET,
                closed_candles=(),
                unfinished_candles=(),
                required_min_closed_candles=required_min,
                max_close_delay_seconds=max_delay_sec,
                expected_latest_closed_open_time_ms=expected_latest_open_ms,
                expected_latest_closed_close_time_ms=expected_latest_close_ms,
                actual_latest_closed_open_time_ms=None,
                actual_latest_closed_close_time_ms=None,
                close_delay_seconds=None,
                issues=tuple(issues),
            )

        # 1. Check ordering, duplicates, and per-candle integrity, and separate unfinished candles
        closed_candles: list[Candle] = []
        unfinished_candles: list[Candle] = []
        seen_open_times: set[int] = set()
        prev_open_time_ms: int | None = None

        has_out_of_order = False
        has_duplicates = False
        has_malformed = False

        for candle in candles:
            if candle.symbol.strip().upper() != symbol.strip().upper():
                has_malformed = True
                issues.append(
                    CandleValidationIssue(
                        code="MALFORMED_CANDLE_DATA",
                        message=f"Symbol mismatch in candle series: expected {symbol}, got {candle.symbol}",
                        candle_open_time_ms=candle.open_time_ms,
                    )
                )

            if candle.timeframe.strip().lower() != tf:
                has_malformed = True
                issues.append(
                    CandleValidationIssue(
                        code="MALFORMED_CANDLE_DATA",
                        message=f"Timeframe mismatch in candle series: expected {tf}, got {candle.timeframe}",
                        candle_open_time_ms=candle.open_time_ms,
                    )
                )

            candle_issues = self._validate_single_candle(candle, interval_ms)
            if candle_issues:
                has_malformed = True
                issues.extend(candle_issues)

            if prev_open_time_ms is not None and candle.open_time_ms < prev_open_time_ms:
                has_out_of_order = True
                issues.append(
                    CandleValidationIssue(
                        code="OUT_OF_ORDER_TIMESTAMPS",
                        message=(
                            f"Candle open_time_ms {candle.open_time_ms} precedes "
                            f"previous candle {prev_open_time_ms}"
                        ),
                        candle_open_time_ms=candle.open_time_ms,
                    )
                )

            if candle.open_time_ms in seen_open_times:
                has_duplicates = True
                issues.append(
                    CandleValidationIssue(
                        code="DUPLICATE_CANDLES",
                        message=f"Duplicate candle open_time_ms detected: {candle.open_time_ms}",
                        candle_open_time_ms=candle.open_time_ms,
                    )
                )
            seen_open_times.add(candle.open_time_ms)
            prev_open_time_ms = candle.open_time_ms

            if candle.is_closed_at(now_ms):
                closed_candles.append(candle)
            else:
                unfinished_candles.append(candle)

        # 2. Check internal missing candles across closed_candles (when ordered)
        has_missing_gaps = False
        if not has_out_of_order and len(closed_candles) >= 2:
            for idx in range(1, len(closed_candles)):
                prev_c = closed_candles[idx - 1]
                curr_c = closed_candles[idx]
                delta_ms = curr_c.open_time_ms - prev_c.open_time_ms
                if delta_ms > interval_ms:
                    missing_count = (delta_ms // interval_ms) - 1
                    has_missing_gaps = True
                    issues.append(
                        CandleValidationIssue(
                            code="MISSING_CANDLES",
                            message=(
                                f"Missing {missing_count} closed candle(s) between "
                                f"{prev_c.open_time_ms} and {curr_c.open_time_ms}"
                            ),
                            candle_open_time_ms=curr_c.open_time_ms,
                            details={
                                "previous_open_time_ms": prev_c.open_time_ms,
                                "current_open_time_ms": curr_c.open_time_ms,
                                "missing_count": missing_count,
                            },
                        )
                    )

        # 3. Evaluate freshness / delayed candle availability / staleness
        actual_latest_open_ms: int | None = None
        actual_latest_close_ms: int | None = None
        close_delay_seconds: float | None = None
        has_delayed_availability = False
        has_stale_data = False

        if not closed_candles:
            has_stale_data = True
            issues.append(
                CandleValidationIssue(
                    code="EMPTY_CLOSED_CANDLES",
                    message=f"No closed candles available for {symbol} ({tf}) as of {now_utc.isoformat()}",
                )
            )
        else:
            latest_closed = closed_candles[-1]
            actual_latest_open_ms = latest_closed.open_time_ms
            actual_latest_close_ms = latest_closed.close_time_ms
            seconds_since_expected_boundary = (now_ms - expected_latest_close_boundary_ms) / 1000.0

            if actual_latest_open_ms == expected_latest_open_ms:
                close_delay_seconds = 0.0
            elif actual_latest_open_ms == (expected_latest_open_ms - interval_ms):
                # The candle that just closed at expected_latest_close_boundary_ms is not yet present.
                # Distinguish delayed availability (<= max_close_delay_seconds) from stale data (> max_close_delay_seconds).
                close_delay_seconds = seconds_since_expected_boundary
                if seconds_since_expected_boundary <= max_delay_sec:
                    has_delayed_availability = True
                    issues.append(
                        CandleValidationIssue(
                            code="DELAYED_CANDLE_AVAILABILITY",
                            message=(
                                f"Latest expected {tf} candle (open={expected_latest_open_ms}, "
                                f"close_boundary={expected_latest_close_boundary_ms}) closed "
                                f"{seconds_since_expected_boundary:.1f}s ago (within {max_delay_sec}s allowed delay) "
                                f"and is not yet available."
                            ),
                            candle_open_time_ms=actual_latest_open_ms,
                            details={
                                "seconds_since_expected_close": seconds_since_expected_boundary,
                                "max_close_delay_seconds": max_delay_sec,
                            },
                        )
                    )
                else:
                    has_stale_data = True
                    issues.append(
                        CandleValidationIssue(
                            code="STALE_DATA",
                            message=(
                                f"Latest expected {tf} candle (open={expected_latest_open_ms}) closed "
                                f"{seconds_since_expected_boundary:.1f}s ago, exceeding max_close_delay_seconds={max_delay_sec}s."
                            ),
                            candle_open_time_ms=actual_latest_open_ms,
                            details={
                                "seconds_since_expected_close": seconds_since_expected_boundary,
                                "max_close_delay_seconds": max_delay_sec,
                            },
                        )
                    )
            elif actual_latest_open_ms < (expected_latest_open_ms - interval_ms):
                lag_seconds = (expected_latest_close_boundary_ms - (actual_latest_open_ms + interval_ms)) / 1000.0 + seconds_since_expected_boundary
                close_delay_seconds = lag_seconds
                has_stale_data = True
                missing_bars = (expected_latest_open_ms - actual_latest_open_ms) // interval_ms
                issues.append(
                    CandleValidationIssue(
                        code="STALE_DATA",
                        message=(
                            f"Closed candle series for {symbol} ({tf}) is stale by {missing_bars} bar(s) "
                            f"({lag_seconds:.1f}s behind expected close boundary)."
                        ),
                        candle_open_time_ms=actual_latest_open_ms,
                        details={
                            "missing_recent_bars": missing_bars,
                            "lag_seconds": lag_seconds,
                        },
                    )
                )
            else:
                # actual_latest_open_ms > expected_latest_open_ms should never happen for a closed candle
                has_malformed = True
                issues.append(
                    CandleValidationIssue(
                        code="MALFORMED_CANDLE_DATA",
                        message=(
                            f"Closed candle open_time_ms {actual_latest_open_ms} is in the future "
                            f"relative to expected latest open {expected_latest_open_ms}"
                        ),
                        candle_open_time_ms=actual_latest_open_ms,
                    )
                )

        # 4. Check minimum closed candle history depth
        has_insufficient_history = False
        if len(closed_candles) < required_min:
            has_insufficient_history = True
            issues.append(
                CandleValidationIssue(
                    code="INSUFFICIENT_HISTORY",
                    message=(
                        f"Closed candle count {len(closed_candles)} for {symbol} ({tf}) is below "
                        f"required minimum of {required_min}."
                    ),
                    details={
                        "closed_candle_count": len(closed_candles),
                        "required_min_closed_candles": required_min,
                    },
                )
            )

        # Determine primary status in strict precedence order
        if has_malformed:
            freshness_status = DataFreshnessStatus.MALFORMED_CANDLE_DATA
        elif has_out_of_order:
            freshness_status = DataFreshnessStatus.OUT_OF_ORDER_TIMESTAMPS
        elif has_duplicates:
            freshness_status = DataFreshnessStatus.DUPLICATE_CANDLES
        elif has_missing_gaps:
            freshness_status = DataFreshnessStatus.MISSING_CANDLES
        elif has_stale_data:
            freshness_status = DataFreshnessStatus.STALE_DATA
        elif has_delayed_availability:
            freshness_status = DataFreshnessStatus.DELAYED_CANDLE_AVAILABILITY
        elif has_insufficient_history:
            freshness_status = DataFreshnessStatus.INSUFFICIENT_HISTORY
        else:
            freshness_status = DataFreshnessStatus.FRESH

        is_valid = len(issues) == 0 and freshness_status == DataFreshnessStatus.FRESH
        analysis_allowed = is_valid

        return CandleValidationResult(
            symbol=symbol.strip().upper(),
            timeframe=tf,
            evaluated_at_utc=now_utc,
            is_valid=is_valid,
            analysis_allowed=analysis_allowed,
            freshness_status=freshness_status,
            closed_candles=tuple(closed_candles),
            unfinished_candles=tuple(unfinished_candles),
            required_min_closed_candles=required_min,
            max_close_delay_seconds=max_delay_sec,
            expected_latest_closed_open_time_ms=expected_latest_open_ms,
            expected_latest_closed_close_time_ms=expected_latest_close_ms,
            actual_latest_closed_open_time_ms=actual_latest_open_ms,
            actual_latest_closed_close_time_ms=actual_latest_close_ms,
            close_delay_seconds=close_delay_seconds,
            issues=tuple(issues),
        )
