"""Binance Spot public market-data client.

Enforces PROJECT_SPEC.md Section 1.2, Section 2, Rule 7, and Rule 8:
- Connects exclusively to public Binance Spot market-data endpoints (`/api/v3/exchangeInfo`,
  `/api/v3/klines`, `/api/v3/ping`, `/api/v3/time`).
- Does NOT accept, store, or transmit private API keys, secrets, or order endpoints.
- Tracks `X-MBX-USED-WEIGHT-1M` response headers, handles HTTP 429/418 rate limits and
  transient 5xx/network errors with bounded retries, and validates payload structure.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable

import httpx

from packages.config.settings import ExchangeConfig
from packages.market_data.models import BookTicker, Candle, SymbolInfo, Ticker24h

ALLOWED_TIMEFRAMES = {"1d", "4h"}


class BinanceAPIError(RuntimeError):
    """Raised when Binance public REST API returns an invalid or non-recoverable response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BinanceRateLimitError(BinanceAPIError):
    """Raised when Binance rate limit (HTTP 429/418) or configured weight limit is exceeded."""


class BinancePublicClient:
    """Read-only public REST client for Binance Spot market data."""

    def __init__(
        self,
        exchange_config: ExchangeConfig,
        http_client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = exchange_config
        self._sleep_fn = sleep_fn
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=self._config.base_url,
            timeout=self._config.request_timeout_seconds,
            headers={
                "Accept": "application/json",
                "User-Agent": "crypto-trading-analyst/0.1.0 (public-market-data-only)",
            },
        )
        self.last_used_weight_1m: int = 0
        # ADR-045: hosts tried in order on network errors (only when this client owns its HTTP connection)
        self._hosts = [self._config.base_url, *getattr(self._config, "fallback_base_urls", ())] if self._owns_client else [self._config.base_url]
        self._host_index = 0
        self.host_in_use: str = self._config.base_url

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "BinancePublicClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def _request_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Perform a GET request with retry/backoff and rate-limit header tracking."""
        if not path.startswith("/api/v3/"):
            raise ValueError(f"Only public /api/v3/ endpoints are permitted; got '{path}'")

        attempts = self._config.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                response = self._client.get(path, params=params)
            except httpx.RequestError as exc:
                last_error = exc
                if attempt < attempts - 1:
                    self._sleep_fn(self._config.retry_backoff_seconds * (2**attempt))
                    continue
                if self._host_index + 1 < len(self._hosts):  # ADR-045: switch to the next host and start again
                    self._host_index += 1
                    self.host_in_use = self._hosts[self._host_index]
                    self._client.base_url = self.host_in_use
                    return self._request_json(path, params)
                raise BinanceAPIError(
                    f"Network error requesting {path} after {attempts} attempt(s) on {len(self._hosts)} host(s): {exc}"
                ) from exc

            weight_header = response.headers.get("X-MBX-USED-WEIGHT-1M")
            if weight_header is not None:
                try:
                    self.last_used_weight_1m = int(weight_header)
                except ValueError:
                    pass

            if response.status_code in (429, 418):
                retry_after = response.headers.get("Retry-After")
                wait_seconds = self._config.retry_backoff_seconds * (2**attempt)
                if retry_after:
                    try:
                        wait_seconds = max(wait_seconds, float(retry_after))
                    except ValueError:
                        pass
                if attempt < attempts - 1:
                    self._sleep_fn(wait_seconds)
                    continue
                raise BinanceRateLimitError(
                    f"Binance rate limit exceeded (HTTP {response.status_code}) on {path}",
                    status_code=response.status_code,
                )

            if 500 <= response.status_code < 600:
                if attempt < attempts - 1:
                    self._sleep_fn(self._config.retry_backoff_seconds * (2**attempt))
                    continue
                raise BinanceAPIError(
                    f"Binance server error HTTP {response.status_code} on {path}",
                    status_code=response.status_code,
                )

            if response.status_code != 200:
                raise BinanceAPIError(
                    f"Unexpected HTTP {response.status_code} on {path}: {response.text[:300]}",
                    status_code=response.status_code,
                )

            try:
                return response.json()
            except ValueError as exc:
                raise BinanceAPIError(f"Malformed JSON payload from {path}: {exc}") from exc

        raise BinanceAPIError(f"Exhausted retries for {path}: {last_error}")

    def fetch_exchange_symbols(self) -> list[SymbolInfo]:
        """Retrieve and validate symbol metadata from `/api/v3/exchangeInfo`."""
        payload = self._request_json("/api/v3/exchangeInfo")
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            raise BinanceAPIError("Malformed /api/v3/exchangeInfo payload: missing 'symbols' list")

        results: list[SymbolInfo] = []
        for raw in payload["symbols"]:
            if not isinstance(raw, dict):
                raise BinanceAPIError("Malformed symbol entry in /api/v3/exchangeInfo")
            try:
                symbol = str(raw["symbol"]).strip().upper()
                status = str(raw["status"]).strip().upper()
                base_asset = str(raw["baseAsset"]).strip().upper()
                quote_asset = str(raw["quoteAsset"]).strip().upper()
            except KeyError as exc:
                raise BinanceAPIError(
                    f"Missing required field {exc} in exchangeInfo symbol entry"
                ) from exc

            is_spot_allowed = bool(raw.get("isSpotTradingAllowed", False))

            # Binance returns either `permissions` (list of strings) or `permissionSets` (nested list)
            permissions: list[str] = []
            if isinstance(raw.get("permissions"), list):
                permissions.extend(str(p).upper() for p in raw["permissions"])
            if isinstance(raw.get("permissionSets"), list):
                for group in raw["permissionSets"]:
                    if isinstance(group, list):
                        permissions.extend(str(p).upper() for p in group)

            results.append(
                SymbolInfo(
                    symbol=symbol,
                    status=status,
                    base_asset=base_asset,
                    quote_asset=quote_asset,
                    is_spot_trading_allowed=is_spot_allowed,
                    permissions=tuple(dict.fromkeys(permissions)),
                    base_asset_precision=int(raw.get("baseAssetPrecision", 8)),
                    quote_precision=int(raw.get("quotePrecision", 8)),
                )
            )
        return results

    def fetch_24h_tickers(self) -> list[Ticker24h]:
        """Retrieve 24h statistics for all symbols from `/api/v3/ticker/24hr`.

        Entries with missing, non-numeric, or non-finite fields are dropped (fail closed):
        the scanner then reports NO_TICKER_DATA for those symbols.
        """
        payload = self._request_json("/api/v3/ticker/24hr")
        if not isinstance(payload, list):
            raise BinanceAPIError("Malformed /api/v3/ticker/24hr payload: expected list")
        results: list[Ticker24h] = []
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            try:
                last_price = float(raw["lastPrice"])
                change = float(raw["priceChangePercent"])
                quote_volume = float(raw["quoteVolume"])
                close_time = int(raw["closeTime"])
                symbol = str(raw["symbol"]).strip().upper()
            except (KeyError, TypeError, ValueError):
                continue
            if not all(math.isfinite(v) for v in (last_price, change, quote_volume)):
                continue
            results.append(
                Ticker24h(
                    symbol=symbol,
                    last_price=last_price,
                    price_change_percent=change,
                    quote_volume=quote_volume,
                    close_time_ms=close_time,
                )
            )
        return results

    def fetch_book_tickers(self) -> list[BookTicker]:
        """Retrieve best bid/ask for all symbols from `/api/v3/ticker/bookTicker`."""
        payload = self._request_json("/api/v3/ticker/bookTicker")
        if not isinstance(payload, list):
            raise BinanceAPIError("Malformed /api/v3/ticker/bookTicker payload: expected list")
        results: list[BookTicker] = []
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            try:
                bid = float(raw["bidPrice"])
                ask = float(raw["askPrice"])
                symbol = str(raw["symbol"]).strip().upper()
            except (KeyError, TypeError, ValueError):
                continue
            if not (math.isfinite(bid) and math.isfinite(ask)):
                continue
            results.append(BookTicker(symbol=symbol, bid_price=bid, ask_price=ask))
        return results

    def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[Candle]:
        """Retrieve historical klines from `/api/v3/klines` for `1d` or `4h`."""
        tf = timeframe.strip().lower()
        if tf not in ALLOWED_TIMEFRAMES:
            raise ValueError(
                f"Invalid timeframe '{timeframe}'. Milestone 1 supports only {sorted(ALLOWED_TIMEFRAMES)}."
            )
        if limit < 1 or limit > 1000:
            raise ValueError("Binance klines limit must be between 1 and 1000")

        clean_symbol = symbol.strip().upper()
        params: dict[str, Any] = {
            "symbol": clean_symbol,
            "interval": tf,
            "limit": limit,
        }
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)

        payload = self._request_json("/api/v3/klines", params=params)
        if not isinstance(payload, list):
            raise BinanceAPIError(
                f"Malformed /api/v3/klines response for {clean_symbol} ({tf}): expected list"
            )

        candles: list[Candle] = []
        for idx, row in enumerate(payload):
            if not isinstance(row, list) or len(row) < 9:
                raise BinanceAPIError(
                    f"Malformed kline row at index {idx} for {clean_symbol} ({tf}): expected >=9 elements"
                )
            try:
                open_time_ms = int(row[0])
                open_price = float(row[1])
                high_price = float(row[2])
                low_price = float(row[3])
                close_price = float(row[4])
                volume = float(row[5])
                close_time_ms = int(row[6])
                quote_volume = float(row[7])
                trade_count = int(row[8])
            except (TypeError, ValueError) as exc:
                raise BinanceAPIError(
                    f"Invalid numeric field in kline row {idx} for {clean_symbol} ({tf}): {exc}"
                ) from exc

            candles.append(
                Candle(
                    symbol=clean_symbol,
                    timeframe=tf,
                    open_time_ms=open_time_ms,
                    close_time_ms=close_time_ms,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                    quote_volume=quote_volume,
                    trade_count=trade_count,
                )
            )
        return candles
