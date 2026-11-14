"""Unit tests for BinancePublicClient using httpx.MockTransport."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import httpx

from packages.config.settings import load_config
from packages.market_data.client import (
    BinanceAPIError,
    BinancePublicClient,
    BinanceRateLimitError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"


class TestBinancePublicClient(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_config(DEFAULT_CONFIG_PATH)

    def test_fetch_exchange_symbols_and_weight_tracking(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/v3/exchangeInfo")
            return httpx.Response(
                status_code=200,
                headers={"X-MBX-USED-WEIGHT-1M": "42"},
                json={
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "status": "TRADING",
                            "baseAsset": "BTC",
                            "quoteAsset": "USDT",
                            "isSpotTradingAllowed": True,
                            "permissions": ["SPOT"],
                            "baseAssetPrecision": 8,
                            "quotePrecision": 8,
                        }
                    ]
                },
            )

        http_client = httpx.Client(
            base_url=self.cfg.exchange.base_url,
            transport=httpx.MockTransport(handler),
        )
        with BinancePublicClient(self.cfg.exchange, http_client=http_client) as client:
            symbols = client.fetch_exchange_symbols()
            self.assertEqual(len(symbols), 1)
            self.assertEqual(symbols[0].symbol, "BTCUSDT")
            self.assertEqual(client.last_used_weight_1m, 42)

    def test_fetch_klines_parses_valid_rows(self) -> None:
        sample_kline = [
            1700006400000,
            "36000.50",
            "36500.00",
            "35800.25",
            "36250.75",
            "1234.56",
            1700020799999,
            "44750000.00",
            28910,
            "600.0",
            "21000000.0",
            "0",
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/v3/klines")
            self.assertEqual(request.url.params["symbol"], "BTCUSDT")
            self.assertEqual(request.url.params["interval"], "4h")
            return httpx.Response(status_code=200, json=[sample_kline])

        http_client = httpx.Client(
            base_url=self.cfg.exchange.base_url,
            transport=httpx.MockTransport(handler),
        )
        client = BinancePublicClient(self.cfg.exchange, http_client=http_client)
        candles = client.fetch_klines("BTCUSDT", "4h", limit=10)
        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].open_time_ms, 1700006400000)
        self.assertAlmostEqual(candles[0].close, 36250.75)
        self.assertEqual(candles[0].trade_count, 28910)

    def test_retries_on_429_and_raises_when_exhausted(self) -> None:
        calls: list[int] = []
        sleeps: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(
                status_code=429,
                headers={"Retry-After": "1.5"},
                text="Too many requests",
            )

        http_client = httpx.Client(
            base_url=self.cfg.exchange.base_url,
            transport=httpx.MockTransport(handler),
        )
        client = BinancePublicClient(
            self.cfg.exchange,
            http_client=http_client,
            sleep_fn=lambda s: sleeps.append(s),
        )
        with self.assertRaises(BinanceRateLimitError):
            client.fetch_exchange_symbols()
        self.assertEqual(len(calls), self.cfg.exchange.max_retries + 1)
        self.assertEqual(len(sleeps), self.cfg.exchange.max_retries)

    def test_recovers_after_transient_500_error(self) -> None:
        attempt = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempt["count"] += 1
            if attempt["count"] == 1:
                return httpx.Response(status_code=502, text="Bad Gateway")
            return httpx.Response(status_code=200, json={"symbols": []})

        http_client = httpx.Client(
            base_url=self.cfg.exchange.base_url,
            transport=httpx.MockTransport(handler),
        )
        client = BinancePublicClient(
            self.cfg.exchange,
            http_client=http_client,
            sleep_fn=lambda _: None,
        )
        symbols = client.fetch_exchange_symbols()
        self.assertEqual(symbols, [])
        self.assertEqual(attempt["count"], 2)

    def test_rejects_malformed_kline_payload(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, content=b'[["bad_row"]]')

        http_client = httpx.Client(
            base_url=self.cfg.exchange.base_url,
            transport=httpx.MockTransport(handler),
        )
        client = BinancePublicClient(self.cfg.exchange, http_client=http_client)
        with self.assertRaises(BinanceAPIError):
            client.fetch_klines("BTCUSDT", "1d", limit=5)


if __name__ == "__main__":
    unittest.main()
