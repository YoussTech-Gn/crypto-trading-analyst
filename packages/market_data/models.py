"""Typed data transfer objects and domain models for Milestone 1 Market Data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DataFreshnessStatus(str, Enum):
    """Explicit classification of candle series freshness and integrity."""

    FRESH = "FRESH"
    DELAYED_CANDLE_AVAILABILITY = "DELAYED_CANDLE_AVAILABILITY"
    STALE_DATA = "STALE_DATA"
    MISSING_CANDLES = "MISSING_CANDLES"
    DUPLICATE_CANDLES = "DUPLICATE_CANDLES"
    OUT_OF_ORDER_TIMESTAMPS = "OUT_OF_ORDER_TIMESTAMPS"
    MALFORMED_CANDLE_DATA = "MALFORMED_CANDLE_DATA"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    EMPTY_DATASET = "EMPTY_DATASET"


class UnreliableMarketDataError(RuntimeError):
    """Raised when downstream analysis attempts to consume unvalidated or unreliable market data."""

    def __init__(self, message: str, validation_result: "CandleValidationResult | None" = None) -> None:
        super().__init__(message)
        self.validation_result = validation_result


@dataclass(frozen=True)
class SymbolInfo:
    """Raw symbol metadata parsed from Binance Spot exchangeInfo."""

    symbol: str
    status: str
    base_asset: str
    quote_asset: str
    is_spot_trading_allowed: bool
    permissions: tuple[str, ...] = ()
    base_asset_precision: int = 8
    quote_precision: int = 8


@dataclass(frozen=True)
class SymbolEvaluation:
    """Result of evaluating a single exchange symbol against universe eligibility rules."""

    symbol: str
    base_asset: str
    quote_asset: str
    exchange_status: str
    is_spot_trading_allowed: bool
    is_eligible: bool
    exclusion_reasons: tuple[str, ...] = ()
    evaluated_at_utc: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True)
class DiscoveryReport:
    """Summary of exchange symbol discovery including both eligible and excluded symbols."""

    evaluated_at_utc: datetime
    total_exchange_symbols: int
    eligible_symbols: tuple[SymbolEvaluation, ...]
    excluded_symbols: tuple[SymbolEvaluation, ...]


@dataclass(frozen=True)
class Candle:
    """Normalized UTC OHLCV candle record."""

    symbol: str
    timeframe: str
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trade_count: int

    @property
    def open_time_utc(self) -> datetime:
        return datetime.fromtimestamp(self.open_time_ms / 1000.0, tz=timezone.utc)

    @property
    def close_time_utc(self) -> datetime:
        return datetime.fromtimestamp(self.close_time_ms / 1000.0, tz=timezone.utc)

    def is_closed_at(self, reference_time_ms: int) -> bool:
        """A candle is closed only after its close_time_ms has strictly passed."""
        return self.close_time_ms < reference_time_ms


@dataclass(frozen=True)
class CandleValidationIssue:
    """Detailed validation issue identified in a candle series."""

    code: str
    message: str
    candle_open_time_ms: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CandleValidationResult:
    """Complete deterministic validation report for a symbol/timeframe candle series."""

    symbol: str
    timeframe: str
    evaluated_at_utc: datetime
    is_valid: bool
    analysis_allowed: bool
    freshness_status: DataFreshnessStatus
    closed_candles: tuple[Candle, ...]
    unfinished_candles: tuple[Candle, ...]
    required_min_closed_candles: int
    max_close_delay_seconds: int
    expected_latest_closed_open_time_ms: int
    expected_latest_closed_close_time_ms: int
    actual_latest_closed_open_time_ms: int | None
    actual_latest_closed_close_time_ms: int | None
    close_delay_seconds: float | None
    issues: tuple[CandleValidationIssue, ...] = ()

    def require_valid_for_analysis(self) -> tuple[Candle, ...]:
        """Fail closed if the dataset is stale, delayed, incomplete, or malformed."""
        if not self.is_valid or not self.analysis_allowed:
            issue_summary = "; ".join(f"[{i.code}] {i.message}" for i in self.issues)
            raise UnreliableMarketDataError(
                f"Downstream analysis blocked for {self.symbol} ({self.timeframe}): "
                f"status={self.freshness_status.value}. Issues: {issue_summary}",
                validation_result=self,
            )
        return self.closed_candles


@dataclass(frozen=True)
class Ticker24h:
    """Validated 24-hour rolling ticker statistics for one symbol (public data)."""

    symbol: str
    last_price: float
    price_change_percent: float
    quote_volume: float
    close_time_ms: int


@dataclass(frozen=True)
class BookTicker:
    """Best bid/ask snapshot for one symbol (public data)."""

    symbol: str
    bid_price: float
    ask_price: float

