"""Persistence, reproducibility and API tests for scanner snapshots."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import create_app
from database.migrations.runner import apply_migrations
from database.session import create_connection
from packages.config.settings import load_config
from packages.market_data.models import BookTicker, SymbolEvaluation, Ticker24h
from packages.scanner import MarketScanner, ScannerRepository

CFG = Path(__file__).resolve().parents[2] / "config" / "default.yaml"
NOW = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
NOW_MS = int(NOW.timestamp() * 1000)


class TestScannerPersistence(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_config(CFG, overrides={"database_url": "sqlite:///:memory:"})
        self.conn = create_connection(self.cfg.database_url)
        apply_migrations(self.conn)
        scanner = MarketScanner(self.cfg.universe, "USDT")
        evals = [
            SymbolEvaluation("AAAUSDT", "AAA", "USDT", "TRADING", True, True, (), NOW),
            SymbolEvaluation("BBBUSDT", "BBB", "USDT", "TRADING", True, True, (), NOW),
            SymbolEvaluation("LOWUSDT", "LOW", "USDT", "TRADING", True, True, (), NOW),
            SymbolEvaluation("NVDABUSDT", "NVDAB", "USDT", "TRADING", True, True, (), NOW),
        ]
        tickers = [Ticker24h("AAAUSDT", 1.0, 5.0, 40e6, NOW_MS), Ticker24h("BBBUSDT", 1.0, -2.0, 70e6, NOW_MS),
                   Ticker24h("LOWUSDT", 1.0, 90.0, 1e6, NOW_MS),
                   Ticker24h("NVDABUSDT", 1.0, 0.5, 30e6, NOW_MS)]
        books = [BookTicker(s, 100.0, 100.01) for s in ("AAAUSDT", "BBBUSDT", "LOWUSDT", "NVDABUSDT")]
        self.snap = scanner.scan(evals, tickers, books, scanned_at_utc=NOW)
        self.repo = ScannerRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_migration_0002_is_applied_and_idempotent(self) -> None:
        self.assertEqual(apply_migrations(self.conn), [])
        row = self.conn.fetchone_dict("SELECT count(*) AS n FROM schema_migrations")
        self.assertEqual(row["n"], 4)

    def test_snapshot_round_trip_and_replay_matches(self) -> None:
        self.repo.save_snapshot(self.snap)
        loaded = self.repo.get_snapshot(self.snap.snapshot_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.entries, self.snap.entries)
        self.assertEqual(MarketScanner.replay(loaded), loaded.entries)
        self.assertEqual(self.repo.get_snapshot(None).snapshot_id, self.snap.snapshot_id)

    def test_database_rejects_excluded_entry_with_rank(self) -> None:
        self.repo.save_snapshot(self.snap)
        with self.assertRaises(Exception):
            self.conn.execute(
                "INSERT INTO scan_rankings (snapshot_id, symbol, status, rank) VALUES (?, ?, ?, ?)",
                (self.snap.snapshot_id, "XUSDT", "EXCLUDED", 1),
            )
        self.conn.rollback()

    def test_api_latest_scan_and_404_without_snapshots(self) -> None:
        client = TestClient(create_app(config=self.cfg, db_conn=self.conn))
        self.assertEqual(client.get("/api/v1/scans/latest").status_code, 404)
        self.repo.save_snapshot(self.snap)
        body = client.get("/api/v1/scans/latest").json()
        self.assertEqual(body["counts"]["shortlisted"], 3)
        self.assertEqual([e["symbol"] for e in body["entries"][:2]], ["BBBUSDT", "AAAUSDT"])
        self.assertIn("not a trading signal", body["note"])
        only_excluded = client.get("/api/v1/scans/latest?status=EXCLUDED").json()
        self.assertEqual([e["symbol"] for e in only_excluded["entries"]], ["LOWUSDT"])
        self.assertEqual(client.get("/api/v1/scans/latest?status=BOGUS").status_code, 422)
        by_cat = client.get("/api/v1/scans/latest?category=tokenized_stock").json()
        self.assertEqual([e["symbol"] for e in by_cat["entries"]], ["NVDABUSDT"])
        self.assertIn("TOKENIZED_STOCK", body["categories"])
        self.assertEqual(client.get("/api/v1/scans/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
