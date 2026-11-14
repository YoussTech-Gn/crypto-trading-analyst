"""Integration tests for database migrations, persistence, constraints, and PostgreSQL dialect compatibility."""

from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from database.migrations.runner import apply_migrations, get_applied_migrations
from database.session import DatabaseConnection, create_connection
from packages.config.settings import load_config
from packages.market_data.models import Candle, SymbolEvaluation
from packages.market_data.repository import MarketDataRepository
from packages.market_data.validator import TIMEFRAME_INTERVAL_MS, CandleValidator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"


class _PostgresRecordingProxyCursor:
    """Wraps a SQLite cursor while verifying PostgreSQL `%s` placeholder translation."""

    def __init__(
        self,
        sqlite_cursor: sqlite3.Cursor,
        recorded_sql: list[str],
    ) -> None:
        self._cursor = sqlite_cursor
        self._recorded_sql = recorded_sql

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        self._recorded_sql.append(sql)
        if params:
            assert "%s" in sql and "?" not in sql, (
                f"Expected PostgreSQL '%s' placeholders in translated query, got: {sql}"
            )
        sqlite_sql = sql.replace("%s", "?")
        return self._cursor.execute(sqlite_sql, tuple(params))

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> Any:
        self._recorded_sql.append(sql)
        if seq_of_params:
            assert "%s" in sql and "?" not in sql, (
                f"Expected PostgreSQL '%s' placeholders in translated executemany, got: {sql}"
            )
        sqlite_sql = sql.replace("%s", "?")
        return self._cursor.executemany(sqlite_sql, [tuple(p) for p in seq_of_params])

    def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()

    @property
    def description(self) -> Any:
        return self._cursor.description


class _PostgresRecordingProxyConnection:
    """Simulates a DB-API 2.0 PostgreSQL driver connection backed by an in-memory engine."""

    def __init__(self) -> None:
        self.raw = sqlite3.connect(":memory:")
        self.raw.execute("PRAGMA foreign_keys = ON;")
        self.recorded_sql: list[str] = []

    def cursor(self) -> _PostgresRecordingProxyCursor:
        return _PostgresRecordingProxyCursor(self.raw.cursor(), self.recorded_sql)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()


class _PostgresMockDriver:
    def __init__(self, proxy_conn: _PostgresRecordingProxyConnection) -> None:
        self.proxy_conn = proxy_conn

    def connect(self, url: str) -> _PostgresRecordingProxyConnection:
        return self.proxy_conn


class TestRepositoryPersistence(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_config(DEFAULT_CONFIG_PATH)
        self.conn = create_connection("sqlite:///:memory:")
        self.applied = apply_migrations(self.conn)
        self.repo = MarketDataRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_migrations_are_idempotent(self) -> None:
        self.assertEqual(self.applied, ["0001_initial_foundation", "0002_scanner_snapshots", "0003_scan_categories", "0004_signal_decisions"])
        reapplied = apply_migrations(self.conn)
        self.assertEqual(reapplied, [])
        self.assertEqual(get_applied_migrations(self.conn), ["0001_initial_foundation", "0002_scanner_snapshots", "0003_scan_categories", "0004_signal_decisions"])

    def test_symbol_and_candle_idempotent_upserts(self) -> None:
        now_utc = datetime(2026, 11, 13, 4, 0, 0, tzinfo=timezone.utc)
        symbols = [
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
                symbol="USDCUSDT",
                base_asset="USDC",
                quote_asset="USDT",
                exchange_status="TRADING",
                is_spot_trading_allowed=True,
                is_eligible=False,
                exclusion_reasons=("EXCLUDED_STABLECOIN_OR_FIAT_BASE:USDC",),
                evaluated_at_utc=now_utc,
            ),
        ]
        self.repo.upsert_symbol_evaluations(symbols)
        eligible = self.repo.list_symbols(eligible_only=True)
        all_syms = self.repo.list_symbols(eligible_only=False)
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0].symbol, "BTCUSDT")
        self.assertEqual(len(all_syms), 2)

        candle_1 = Candle(
            symbol="BTCUSDT",
            timeframe="1d",
            open_time_ms=1700006400000,
            close_time_ms=1700092799999,
            open=35_000.0,
            high=36_000.0,
            low=34_500.0,
            close=35_800.0,
            volume=100.0,
            quote_volume=3_550_000.0,
            trade_count=1000,
        )
        self.repo.upsert_closed_candles([candle_1])

        # Upsert updated close/volume for same open_time_ms; must update in place without duplicating
        candle_1_updated = Candle(
            symbol="BTCUSDT",
            timeframe="1d",
            open_time_ms=1700006400000,
            close_time_ms=1700092799999,
            open=35_000.0,
            high=36_200.0,
            low=34_500.0,
            close=36_100.0,
            volume=150.0,
            quote_volume=5_400_000.0,
            trade_count=1400,
        )
        self.repo.upsert_closed_candles([candle_1_updated])
        stored = self.repo.get_candles("BTCUSDT", "1d")
        self.assertEqual(len(stored), 1)
        self.assertAlmostEqual(stored[0].close, 36_100.0)
        self.assertAlmostEqual(stored[0].volume, 150.0)

    def test_database_check_constraints_reject_invalid_ohlc(self) -> None:
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
                )
            ]
        )
        invalid_candle = Candle(
            symbol="BTCUSDT",
            timeframe="1d",
            open_time_ms=1700006400000,
            close_time_ms=1700092799999,
            open=35_000.0,
            high=34_000.0,  # Violates CHECK (high >= low AND high >= open)
            low=34_500.0,
            close=34_800.0,
            volume=10.0,
            quote_volume=350_000.0,
            trade_count=50,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.upsert_closed_candles([invalid_candle])

    def test_postgresql_dialect_migration_and_upsert_execution(self) -> None:
        proxy = _PostgresRecordingProxyConnection()
        pg_conn = create_connection(
            "postgresql://analyst:pass@localhost:5432/crypto_trading_analyst",
            pg_driver_override=_PostgresMockDriver(proxy),
        )
        try:
            self.assertEqual(pg_conn.dialect, "postgresql")
            applied = apply_migrations(pg_conn)
            self.assertEqual(applied, ["0001_initial_foundation", "0002_scanner_snapshots", "0003_scan_categories", "0004_signal_decisions"])

            pg_repo = MarketDataRepository(pg_conn)
            now_utc = datetime(2026, 11, 13, 4, 2, 0, tzinfo=timezone.utc)
            pg_repo.upsert_symbol_evaluations(
                [
                    SymbolEvaluation(
                        symbol="ETHUSDT",
                        base_asset="ETH",
                        quote_asset="USDT",
                        exchange_status="TRADING",
                        is_spot_trading_allowed=True,
                        is_eligible=True,
                        exclusion_reasons=(),
                        evaluated_at_utc=now_utc,
                    )
                ]
            )
            interval_1d = TIMEFRAME_INTERVAL_MS["1d"]
            ref_ms = int(now_utc.timestamp() * 1000)
            latest_open = ((ref_ms // interval_1d) * interval_1d) - interval_1d
            candles = [
                Candle(
                    symbol="ETHUSDT",
                    timeframe="1d",
                    open_time_ms=latest_open - (199 - i) * interval_1d,
                    close_time_ms=latest_open - (199 - i) * interval_1d + interval_1d - 1,
                    open=2500.0 + i,
                    high=2550.0 + i,
                    low=2480.0 + i,
                    close=2520.0 + i,
                    volume=1000.0,
                    quote_volume=2_500_000.0,
                    trade_count=5000,
                )
                for i in range(200)
            ]
            pg_repo.upsert_closed_candles(candles)
            validator = CandleValidator(self.cfg.timeframes)
            val_res = validator.validate(
                "ETHUSDT", "1d", candles, reference_time_utc=now_utc
            )
            run_id = pg_repo.record_validation_run(val_res)
            self.assertTrue(len(run_id) > 10)

            fetched = pg_repo.get_candles("ETHUSDT", "1d", limit=5)
            self.assertEqual(len(fetched), 5)
            latest_run = pg_repo.get_latest_validation_run("ETHUSDT", "1d")
            self.assertIsNotNone(latest_run)
            assert latest_run is not None
            self.assertEqual(latest_run["freshness_status"], "FRESH")
        finally:
            pg_conn.close()


if __name__ == "__main__":
    unittest.main()
