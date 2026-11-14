"""Validated configuration schema and loader for AI Crypto Trading Analyst.

Enforces safety boundaries from PROJECT_SPEC.md:
- Spot market only, USDT quote asset only, LONG direction only.
- Real order execution is strictly forbidden (real_orders_enabled must be False).
- Closed-candle evaluation must be enabled.
- Configurable minimum candle counts (default 200 1D, 500 4H) and max candle close delay (default 300s / 5m).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class ConfigValidationError(ValueError):
    """Raised when application configuration is missing, malformed, or violates safety boundaries."""


class ExchangeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["binance"] = "binance"
    market: Literal["spot"] = "spot"
    quote_asset: Literal["USDT"] = "USDT"
    base_url: str = Field(default="https://api.binance.com", min_length=8)
    request_timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=30.0)
    max_rate_limit_weight_per_minute: int = Field(default=1200, ge=100, le=6000)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        if not (cleaned.startswith("https://") or cleaned.startswith("http://")):
            raise ValueError("exchange.base_url must start with https:// or http://")
        return cleaned


class UniverseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_candidates: int = Field(default=30, ge=1, le=200)
    min_quote_volume_24h: float = Field(default=10_000_000.0, gt=0.0)
    max_spread_bps: float = Field(default=20.0, gt=0.0, le=500.0)
    max_ticker_age_seconds: int = Field(default=300, ge=1, le=3600)
    excluded_assets: list[str] = Field(default_factory=list)
    excluded_stablecoin_base_assets: list[str] = Field(
        default_factory=lambda: [
            "USDC",
            "FDUSD",
            "TUSD",
            "USDP",
            "DAI",
            "BUSD",
            "USDE",
            "USDT",
            "EUR",
            "AEUR",
            "EURI",
            "GBP",
            "TRY",
            "BRL",
            "BIDR",
            "IDRT",
            "UAH",
            "RUB",
            "NGN",
            "PLN",
            "RON",
            "ARS",
            "ZAR",
            "JPY",
            "PAX",
            "VAI",
            "USTC",
            "USD1",
            "RLUSD",
            "U",
            "USDS",
            "PYUSD",
            "RWUSD",
        ]
    )
    excluded_leveraged_suffixes: list[str] = Field(
        default_factory=lambda: ["UP", "DOWN", "BULL", "BEAR"]
    )
    excluded_leveraged_base_assets: list[str] = Field(default_factory=list)
    # Explicit asset -> category mapping (category name -> base assets). Assets not listed
    # are reported as "CRYPTO". Display/filter only: categories never affect ranking.
    asset_categories: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("asset_categories")
    @classmethod
    def validate_asset_categories(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = {}
        seen: dict[str, str] = {}
        for raw_name, assets in value.items():
            name = str(raw_name).strip().upper()
            if not name or name == "CRYPTO":
                raise ValueError("category names must be non-empty and not 'CRYPTO' (the default)")
            cleaned: list[str] = []
            for asset in assets:
                a = str(asset).strip().upper()
                if not a:
                    continue
                if a in seen and seen[a] != name:
                    raise ValueError(f"asset {a} is in two categories: {seen[a]} and {name}")
                seen[a] = name
                if a not in cleaned:
                    cleaned.append(a)
            normalized[name] = cleaned
        return normalized

    @field_validator(
        "excluded_assets",
        "excluded_stablecoin_base_assets",
        "excluded_leveraged_suffixes",
        "excluded_leveraged_base_assets",
    )
    @classmethod
    def normalize_upper_strings(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in values:
            cleaned = str(item).strip().upper()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized


class TimeframesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: Literal["1d"] = "1d"
    setup: Literal["4h"] = "4h"
    use_closed_candles: bool = True
    min_closed_candles_1d: int = Field(default=200, ge=10, le=5000)
    min_closed_candles_4h: int = Field(default=500, ge=20, le=10000)
    max_close_delay_seconds: int = Field(default=300, ge=1, le=3600)

    @field_validator("use_closed_candles")
    @classmethod
    def enforce_closed_candles(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError(
                "timeframes.use_closed_candles must be True per PROJECT_SPEC.md Section 4.3"
            )
        return value


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_version: str = Field(default="baseline-1.0", min_length=1)
    direction: Literal["long_only"] = "long_only"
    minimum_reward_to_risk: float = Field(default=2.0, gt=0.0, le=20.0)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["paper"] = "paper"
    simulated_equity: float = Field(default=10_000.0, gt=0.0)
    risk_per_trade_percent: float = Field(default=1.0, gt=0.0, le=10.0)
    max_open_positions: int = Field(default=3, ge=1, le=50)


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    real_orders_enabled: bool = False
    paper_trading_enabled: bool = True

    @field_validator("real_orders_enabled")
    @classmethod
    def forbid_real_orders(cls, value: bool) -> bool:
        if value is not False:
            raise ValueError(
                "Safety violation: execution.real_orders_enabled must be False. "
                "Real-money execution is out of scope per PROJECT_SPEC.md Section 1.2 & Rule 7."
            )
        return value


class AnalysisConfig(BaseModel):
    """Provisional analysis parameters (engineering defaults, not validated trading edge)."""

    model_config = ConfigDict(extra="forbid")

    swing_lookback: int = Field(default=3, ge=1, le=20)
    min_confirmed_swings: int = Field(default=2, ge=2, le=10)
    ema_fast: int = Field(default=50, ge=2, le=500)
    ema_slow: int = Field(default=200, ge=3, le=1000)
    rsi_period: int = Field(default=14, ge=2, le=100)
    atr_period: int = Field(default=14, ge=2, le=100)
    relative_volume_period: int = Field(default=20, ge=2, le=500)
    equal_level_tolerance_pct: float = Field(default=0.1, gt=0.0, le=5.0)
    min_sweep_penetration_pct: float = Field(default=0.05, ge=0.0, le=5.0)

    @model_validator(mode="after")
    def ema_order(self) -> "AnalysisConfig":
        if self.ema_fast >= self.ema_slow:
            raise ValueError("analysis.ema_fast must be smaller than analysis.ema_slow")
        return self


class SignalConfig(BaseModel):
    """Provisional paper-signal parameters. Minimum RR comes from strategy.minimum_reward_to_risk."""

    model_config = ConfigDict(extra="forbid")

    sweep_window_candles: int = Field(default=6, ge=1, le=60)
    max_entry_distance_atr: float = Field(default=1.0, ge=0.0, le=10.0)
    stop_atr_buffer: float = Field(default=0.25, ge=0.0, le=5.0)
    expiry_candles: int = Field(default=6, ge=1, le=60)
    # nearest: closest confirmed swing high above entry. first_meeting_rr: first swing high that gives at least the minimum RR.
    target_mode: str = Field(default="nearest", pattern="^(nearest|first_meeting_rr)$")
    # Optional vetoes learned from post-mortems. OFF by default (0 / 100 = disabled). Enable only after
    # out-of-sample confirmation and user approval.
    min_risk_atr: float = Field(default=0.0, ge=0.0, le=10.0)
    max_sweep_penetration_pct: float = Field(default=0.0, ge=0.0, le=20.0)
    min_fvg_size_atr: float = Field(default=0.0, ge=0.0, le=10.0)
    max_rsi: float = Field(default=100.0, ge=0.0, le=100.0)
    min_relative_volume: float = Field(default=0.0, ge=0.0, le=20.0)


class BacktestConfig(BaseModel):
    """Provisional backtest assumptions. Conservative on purpose."""

    model_config = ConfigDict(extra="forbid")

    fee_pct_per_side: float = Field(default=0.1, ge=0.0, le=2.0)
    stop_slippage_pct: float = Field(default=0.05, ge=0.0, le=5.0)
    max_hold_candles: int = Field(default=30, ge=1, le=500)
    min_trades_for_confidence: int = Field(default=30, ge=1, le=10000)
    analysis_window_4h: int = Field(default=600, ge=100, le=1000)
    analysis_window_1d: int = Field(default=300, ge=200, le=1000)


class AppConfig(BaseModel):
    """Root validated application configuration."""

    model_config = ConfigDict(extra="forbid")

    exchange: ExchangeConfig
    universe: UniverseConfig
    timeframes: TimeframesConfig
    strategy: StrategyConfig
    risk: RiskConfig
    execution: ExecutionConfig
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    signals: SignalConfig = Field(default_factory=SignalConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    database_url: str = Field(
        default="postgresql://analyst:analyst_dev_password@localhost:5432/crypto_trading_analyst"
    )

    @model_validator(mode="after")
    def validate_database_url(self) -> "AppConfig":
        if not (
            self.database_url.startswith("postgresql://")
            or self.database_url.startswith("postgres://")
            or self.database_url.startswith("sqlite:///")
            or self.database_url == "sqlite:///:memory:"
        ):
            raise ValueError(
                "database_url must use a postgresql:// or sqlite:/// scheme"
            )
        return self


def load_config(
    config_path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> AppConfig:
    """Load, merge, and strictly validate configuration from YAML and environment variables."""
    resolved_path = Path(
        config_path
        or os.environ.get("CONFIG_PATH", "config/default.yaml")
    )
    if not resolved_path.is_file():
        raise ConfigValidationError(f"Configuration file not found: {resolved_path}")

    try:
        with resolved_path.open("r", encoding="utf-8") as handle:
            raw_data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigValidationError(f"Invalid YAML in {resolved_path}: {exc}") from exc

    if not isinstance(raw_data, dict):
        raise ConfigValidationError(
            f"Configuration root in {resolved_path} must be a YAML mapping"
        )

    env_db_url = os.environ.get("DATABASE_URL")
    if env_db_url and "database_url" not in raw_data:
        raw_data["database_url"] = env_db_url

    env_binance_url = os.environ.get("BINANCE_BASE_URL")
    if env_binance_url and isinstance(raw_data.get("exchange"), dict):
        raw_data["exchange"]["base_url"] = env_binance_url

    if overrides:
        for section, val in overrides.items():
            if isinstance(val, dict) and isinstance(raw_data.get(section), dict):
                raw_data[section] = {**raw_data[section], **val}
            else:
                raw_data[section] = val

    try:
        return AppConfig.model_validate(raw_data)
    except ValidationError as exc:
        raise ConfigValidationError(
            f"Configuration validation failed for {resolved_path}:\n{exc}"
        ) from exc
