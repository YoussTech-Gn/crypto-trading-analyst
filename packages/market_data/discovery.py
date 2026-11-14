"""Exchange symbol discovery and eligibility filtering with explicit exclusion reasons.

Implements PROJECT_SPEC.md Section 3.2 & 3.3 and Milestone 1 Clarification #5:
- Includes only active Spot symbols quoted in the configured quote asset (USDT).
- Excludes stablecoin and fiat base assets via configurable list.
- Excludes leveraged tokens via explicit configurable list and documented suffix rule
  (requiring suffix match on tokens longer than prefix+suffix minimum length, recording the exact rule).
- Records every exclusion reason for full auditability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from packages.config.settings import UniverseConfig
from packages.market_data.models import DiscoveryReport, SymbolEvaluation, SymbolInfo


class SymbolDiscoveryService:
    """Evaluates Binance exchangeInfo symbols and classifies eligible vs. excluded pairs."""

    def __init__(
        self,
        universe_config: UniverseConfig,
        quote_asset: str = "USDT",
    ) -> None:
        self._config = universe_config
        self._quote_asset = quote_asset.strip().upper()
        self._manual_exclusions = set(self._config.excluded_assets)
        self._stablecoin_exclusions = set(self._config.excluded_stablecoin_base_assets)
        self._leveraged_explicit = set(self._config.excluded_leveraged_base_assets)
        self._leveraged_suffixes = tuple(self._config.excluded_leveraged_suffixes)

    def evaluate_symbol(
        self,
        info: SymbolInfo,
        evaluated_at_utc: datetime | None = None,
    ) -> SymbolEvaluation:
        """Evaluate a single symbol and collect all applicable exclusion reasons."""
        timestamp = evaluated_at_utc or datetime.now(timezone.utc)
        reasons: list[str] = []

        symbol_upper = info.symbol.strip().upper()
        base_upper = info.base_asset.strip().upper()
        quote_upper = info.quote_asset.strip().upper()
        status_upper = info.status.strip().upper()
        perms_upper = {p.strip().upper() for p in info.permissions}

        if quote_upper != self._quote_asset:
            reasons.append(f"NON_TARGET_QUOTE_ASSET:{quote_upper}")

        if status_upper != "TRADING":
            reasons.append(f"EXCHANGE_STATUS_NOT_TRADING:{status_upper}")

        if not info.is_spot_trading_allowed:
            reasons.append("SPOT_TRADING_NOT_ALLOWED")

        # Fail closed: missing permission metadata is treated the same as a missing SPOT permission.
        if "SPOT" not in perms_upper:
            reasons.append("MISSING_SPOT_PERMISSION")

        if symbol_upper in self._manual_exclusions or base_upper in self._manual_exclusions:
            reasons.append("MANUALLY_EXCLUDED_ASSET")

        if base_upper in self._stablecoin_exclusions:
            reasons.append(f"EXCLUDED_STABLECOIN_OR_FIAT_BASE:{base_upper}")

        if base_upper in self._leveraged_explicit:
            reasons.append(f"EXCLUDED_LEVERAGED_TOKEN_EXPLICIT:{base_upper}")
        else:
            # Documented leveraged-token suffix rule:
            # Binance leveraged tokens follow <UNDERLYING><UP|DOWN|BULL|BEAR> where the
            # underlying ticker is at least 2 characters long (e.g., BTCUP, ETHDOWN, BNBBEAR).
            for suffix in self._leveraged_suffixes:
                if len(base_upper) >= len(suffix) + 2 and base_upper.endswith(suffix):
                    reasons.append(f"EXCLUDED_LEVERAGED_TOKEN_SUFFIX:{suffix}")
                    break

        return SymbolEvaluation(
            symbol=symbol_upper,
            base_asset=base_upper,
            quote_asset=quote_upper,
            exchange_status=status_upper,
            is_spot_trading_allowed=info.is_spot_trading_allowed,
            is_eligible=(len(reasons) == 0),
            exclusion_reasons=tuple(reasons),
            evaluated_at_utc=timestamp,
        )

    def discover(
        self,
        symbols: Iterable[SymbolInfo],
        evaluated_at_utc: datetime | None = None,
    ) -> DiscoveryReport:
        """Evaluate all exchange symbols and produce a reproducible DiscoveryReport."""
        timestamp = evaluated_at_utc or datetime.now(timezone.utc)
        eligible: list[SymbolEvaluation] = []
        excluded: list[SymbolEvaluation] = []
        total = 0

        for item in symbols:
            total += 1
            evaluation = self.evaluate_symbol(item, evaluated_at_utc=timestamp)
            if evaluation.is_eligible:
                eligible.append(evaluation)
            else:
                excluded.append(evaluation)

        eligible.sort(key=lambda s: s.symbol)
        excluded.sort(key=lambda s: s.symbol)

        return DiscoveryReport(
            evaluated_at_utc=timestamp,
            total_exchange_symbols=total,
            eligible_symbols=tuple(eligible),
            excluded_symbols=tuple(excluded),
        )
