"""Verify the real Python DB adapter + migrations + repository against a PostgreSQL server.

Usage (never use a production database; use a throwaway Neon branch):
    set DATABASE_URL=postgresql://...        (Windows cmd)
    python scripts/verify_postgres.py

Writes only a clearly-named test symbol (ZZTESTUSDT) and removes it at the end.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run from any folder
from datetime import datetime, timezone

from database.migrations.runner import apply_migrations, get_applied_migrations
from database.session import create_connection
from packages.market_data.models import Candle, SymbolEvaluation
from packages.market_data.models import BookTicker, Ticker24h
from packages.market_data.repository import MarketDataRepository
from packages.scanner import MarketScanner, ScannerRepository
from packages.config.settings import load_config


def main() -> int:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url.startswith(("postgresql://", "postgres://")):
        print("FAIL: set DATABASE_URL to a postgresql:// URL")
        return 2
    conn = create_connection(url)
    try:
        first = apply_migrations(conn)
        second = apply_migrations(conn)
        assert second == [], f"migrations not idempotent: {second}"
        print("migrations applied now:", first, "| applied total:", get_applied_migrations(conn))

        repo = MarketDataRepository(conn)
        now = datetime.now(timezone.utc)
        repo.upsert_symbol_evaluations([SymbolEvaluation(
            symbol="ZZTESTUSDT", base_asset="ZZTEST", quote_asset="USDT",
            exchange_status="TRADING", is_spot_trading_allowed=True,
            is_eligible=True, exclusion_reasons=(), evaluated_at_utc=now)])
        repo.upsert_closed_candles([Candle(
            symbol="ZZTESTUSDT", timeframe="4h", open_time_ms=1700006400000,
            close_time_ms=1700020799999, open=1.0, high=2.0, low=0.5, close=1.5,
            volume=10.0, quote_volume=15.0, trade_count=3)])
        got = repo.get_candles(symbol="ZZTESTUSDT", timeframe="4h", limit=5)
        assert len(got) == 1 and got[0].close == 1.5, got
        try:
            repo.upsert_closed_candles([Candle(
                symbol="ZZTESTUSDT", timeframe="4h", open_time_ms=1700020800000,
                close_time_ms=1700035199999, open=1.0, high=0.1, low=0.5, close=1.5,
                volume=1.0, quote_volume=1.0, trade_count=1)])
            print("FAIL: invalid candle (high<low) was accepted")
            return 1
        except Exception as exc:  # expected: DB CHECK constraint or repo validation
            conn.rollback()
            print("OK invalid candle rejected:", type(exc).__name__)
        cfg = load_config()
        scanner = MarketScanner(cfg.universe, "USDT")
        now_ms = int(now.timestamp() * 1000)
        snap = scanner.scan(
            [SymbolEvaluation("ZZTESTUSDT", "ZZTEST", "USDT", "TRADING", True, True, (), now)],
            [Ticker24h("ZZTESTUSDT", 1.0, 99.0, 50e6, now_ms)],
            [BookTicker("ZZTESTUSDT", 1.0, 1.0001)],
            scanned_at_utc=now,
        )
        srepo = ScannerRepository(conn)
        srepo.save_snapshot(snap)
        loaded = srepo.get_snapshot(snap.snapshot_id)
        assert loaded is not None and loaded.entries == snap.entries, "snapshot round-trip failed"
        assert MarketScanner.replay(loaded) == loaded.entries, "replay mismatch"
        assert loaded.entries[0].status == "SHORTLISTED"
        print("OK scanner snapshot saved, loaded and replayed")
        conn.execute("DELETE FROM scan_snapshots WHERE snapshot_id = ?", (snap.snapshot_id,))
        conn.execute("DELETE FROM symbols WHERE symbol = ?", ("ZZTESTUSDT",))
        conn.commit()
        print(f"PASS: PostgreSQL adapter, migrations {get_applied_migrations(conn)}, upsert, read-back, constraints, scanner snapshot")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
