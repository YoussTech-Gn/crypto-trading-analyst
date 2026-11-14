"""Run one market scan (public Binance data only) and store the snapshot.

Usage:  python scripts/run_scan.py
Uses DATABASE_URL (or the config default). No API keys are used or accepted.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run from any folder
from datetime import datetime, timezone

from database.migrations.runner import apply_migrations
from database.session import create_connection
from packages.reporting import run_guarded
from packages.config.settings import load_config
from packages.market_data.client import BinancePublicClient
from packages.market_data.discovery import SymbolDiscoveryService
from packages.market_data.repository import MarketDataRepository
from packages.scanner import MarketScanner, ScannerRepository


def main() -> int:
    cfg = load_config()
    conn = create_connection(cfg.database_url)
    try:
        apply_migrations(conn)
        now = datetime.now(timezone.utc)
        with BinancePublicClient(cfg.exchange) as client:
            symbols = client.fetch_exchange_symbols()
            tickers = client.fetch_24h_tickers()
            book = client.fetch_book_tickers()

        report = SymbolDiscoveryService(cfg.universe, cfg.exchange.quote_asset).discover(
            symbols, evaluated_at_utc=now
        )
        evaluations = list(report.eligible_symbols) + list(report.excluded_symbols)
        MarketDataRepository(conn).upsert_symbol_evaluations(evaluations)

        scanner = MarketScanner(cfg.universe, cfg.exchange.quote_asset)
        snap = scanner.scan(evaluations, tickers, book, scanned_at_utc=now)
        if scanner.replay(snap) != snap.entries:
            print("FAIL: replay does not reproduce the ranking")
            return 1
        ScannerRepository(conn).save_snapshot(snap)

        print(f"snapshot {snap.snapshot_id} at {snap.created_at_utc.isoformat()}")
        print(f"evaluated={len(snap.entries)} shortlisted={len(snap.shortlisted)}")
        for e in snap.shortlisted:
            print(f"{e.rank:>3}  {e.symbol:<14} {e.category:<15} vol24h={e.quote_volume:>16,.0f}  "
                  f"chg={e.price_change_percent:+7.2f}%  spread={e.spread_bps:5.2f}bps")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(run_guarded("run_scan", main))
