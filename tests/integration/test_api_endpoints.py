"""Integration tests for FastAPI Milestone 1 endpoints."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import create_app
from database.migrations.runner import apply_migrations
from database.session import create_connection
from packages.config.settings import load_config
from packages.market_data.models import Candle, SymbolEvaluation
from packages.market_data.repository import MarketDataRepository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"


class TestAPIEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_config(
            DEFAULT_CONFIG_PATH,
            overrides={"database_url": "sqlite:///:memory:"},
        )
        self.conn = create_connection(self.cfg.database_url)
        apply_migrations(self.conn)
        self.repo = MarketDataRepository(self.conn)

        now_utc = datetime(2026, 11, 13, 4, 0, 0, tzinfo=timezone.utc)
        self.repo.upsert_symbol_evaluations(
            [
                SymbolEvaluation(
                    symbol="BTCUSDT",
                    base_asset="BTC",
                    quote_asset="USDT",
                    exchange_status="TRADING",
                    is_spot_trading_allowed=True,
                    is_eligible=True,
                    exclusion_reasons=(),
                    evaluated_at_utc=now_utc,
                ),
                SymbolEvaluation(
                    symbol="FDUSDUSDT",
                    base_asset="FDUSD",
                    quote_asset="USDT",
                    exchange_status="TRADING",
                    is_spot_trading_allowed=True,
                    is_eligible=False,
                    exclusion_reasons=("EXCLUDED_STABLECOIN_OR_FIAT_BASE:FDUSD",),
                    evaluated_at_utc=now_utc,
                ),
            ]
        )
        self.repo.upsert_closed_candles(
            [
                Candle(
                    symbol="BTCUSDT",
                    timeframe="4h",
                    open_time_ms=1700006400000,
                    close_time_ms=1700020799999,
                    open=36000.0,
                    high=36500.0,
                    low=35900.0,
                    close=36300.0,
                    volume=500.0,
                    quote_volume=18_100_000.0,
                    trade_count=10000,
                )
            ]
        )
        self.app = create_app(config=self.cfg, db_conn=self.conn)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.conn.close()

    def test_health_endpoint_reports_safety_and_timeframes(self) -> None:
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertFalse(body["safety"]["real_orders_enabled"])
        self.assertEqual(body["timeframes"]["min_closed_candles_1d"], 200)
        self.assertEqual(body["timeframes"]["min_closed_candles_4h"], 500)
        self.assertEqual(body["timeframes"]["max_close_delay_seconds"], 300)

    def test_health_returns_503_when_database_unavailable(self) -> None:
        self.conn.close()
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["status"], "unavailable")
        self.conn = create_connection(self.cfg.database_url)  # keep tearDown valid

    def test_health_reports_database_ok(self) -> None:
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.json()["database"], "ok")

    def test_symbols_endpoint_filters_eligible_and_shows_exclusions(self) -> None:
        resp_eligible = self.client.get("/api/v1/symbols?eligible_only=true")
        self.assertEqual(resp_eligible.status_code, 200)
        self.assertEqual(resp_eligible.json()["count"], 1)
        self.assertEqual(resp_eligible.json()["symbols"][0]["symbol"], "BTCUSDT")

        resp_all = self.client.get("/api/v1/symbols?eligible_only=false")
        self.assertEqual(resp_all.status_code, 200)
        self.assertEqual(resp_all.json()["count"], 2)

    def test_candles_endpoint_returns_stored_candles_and_rejects_bad_tf(self) -> None:
        resp = self.client.get("/api/v1/candles/BTCUSDT/4h?limit=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["candles"][0]["close"], 36300.0)

        resp_bad = self.client.get("/api/v1/candles/BTCUSDT/15m")
        self.assertEqual(resp_bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()
