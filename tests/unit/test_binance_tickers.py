"""Unit tests for 24h and bookTicker parsing (fail-closed on malformed entries)."""

from __future__ import annotations

import unittest
from pathlib import Path

import httpx

from packages.config.settings import load_config
from packages.market_data.client import BinanceAPIError, BinancePublicClient

CFG = Path(__file__).resolve().parents[2] / "config" / "default.yaml"


def make_client(payloads: dict[str, object]) -> BinancePublicClient:
    cfg = load_config(CFG)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payloads[request.url.path])

    http = httpx.Client(base_url=cfg.exchange.base_url, transport=httpx.MockTransport(handler))
    return BinancePublicClient(cfg.exchange, http_client=http, sleep_fn=lambda _s: None)


class TestTickerParsing(unittest.TestCase):
    def test_24h_tickers_parse_and_drop_invalid_entries(self) -> None:
        client = make_client({"/api/v3/ticker/24hr": [
            {"symbol": "BTCUSDT", "lastPrice": "100.5", "priceChangePercent": "2.5",
             "quoteVolume": "123456789.1", "closeTime": 1700000000000},
            {"symbol": "BADUSDT", "lastPrice": "abc", "priceChangePercent": "1",
             "quoteVolume": "5", "closeTime": 1},
            {"symbol": "NANUSDT", "lastPrice": "1", "priceChangePercent": "1",
             "quoteVolume": "NaN", "closeTime": 1},
            {"symbol": "MISSINGUSDT"},
        ]})
        result = client.fetch_24h_tickers()
        self.assertEqual([t.symbol for t in result], ["BTCUSDT"])
        self.assertEqual(result[0].quote_volume, 123456789.1)

    def test_book_tickers_parse_and_drop_invalid_entries(self) -> None:
        client = make_client({"/api/v3/ticker/bookTicker": [
            {"symbol": "BTCUSDT", "bidPrice": "100.0", "askPrice": "100.1"},
            {"symbol": "BADUSDT", "bidPrice": "x", "askPrice": "1"},
        ]})
        result = client.fetch_book_tickers()
        self.assertEqual([b.symbol for b in result], ["BTCUSDT"])

    def test_non_list_payload_is_rejected(self) -> None:
        client = make_client({"/api/v3/ticker/24hr": {"oops": 1}})
        with self.assertRaises(BinanceAPIError):
            client.fetch_24h_tickers()


if __name__ == "__main__":
    unittest.main()
