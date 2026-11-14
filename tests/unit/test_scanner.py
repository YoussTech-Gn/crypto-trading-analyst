"""Unit tests for the deterministic market scanner (Milestone 2)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from packages.config.settings import load_config
from packages.market_data.models import BookTicker, SymbolEvaluation, Ticker24h
from packages.scanner import MarketScanner

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
NOW_MS = int(NOW.timestamp() * 1000)


def ev(symbol: str, eligible: bool = True, reasons: tuple[str, ...] = (), quote: str = "USDT") -> SymbolEvaluation:
    base = symbol.removesuffix(quote)
    return SymbolEvaluation(symbol, base, quote, "TRADING", True, eligible, reasons, NOW)


def tk(symbol: str, qv: float, change: float = 1.0, age_s: int = 5) -> Ticker24h:
    return Ticker24h(symbol, 100.0, change, qv, NOW_MS - age_s * 1000)


def bk(symbol: str, bid: float = 100.0, ask: float = 100.01) -> BookTicker:
    return BookTicker(symbol, bid, ask)


class TestScanner(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_config(PROJECT_ROOT / "config" / "default.yaml")
        self.scanner = MarketScanner(self.cfg.universe, "USDT")

    def _scan(self, evals, tickers, books):
        return self.scanner.scan(evals, tickers, books, scanned_at_utc=NOW)

    def _by_symbol(self, snap):
        return {e.symbol: e for e in snap.entries}

    def test_ranks_by_quote_volume_then_symbol(self) -> None:
        snap = self._scan(
            [ev("AAAUSDT"), ev("BBBUSDT"), ev("CCCUSDT")],
            [tk("AAAUSDT", 50e6), tk("BBBUSDT", 90e6), tk("CCCUSDT", 50e6)],
            [bk("AAAUSDT"), bk("BBBUSDT"), bk("CCCUSDT")],
        )
        self.assertEqual([e.symbol for e in snap.entries], ["BBBUSDT", "AAAUSDT", "CCCUSDT"])
        self.assertEqual([e.rank for e in snap.entries], [1, 2, 3])

    def test_large_24h_gain_does_not_change_rank_or_create_signal(self) -> None:
        snap = self._scan(
            [ev("PUMPUSDT"), ev("BIGUSDT")],
            [tk("PUMPUSDT", 20e6, change=95.0), tk("BIGUSDT", 80e6, change=-3.0)],
            [bk("PUMPUSDT"), bk("BIGUSDT")],
        )
        by = self._by_symbol(snap)
        self.assertEqual(by["BIGUSDT"].rank, 1)
        self.assertEqual(by["PUMPUSDT"].rank, 2)
        for entry in snap.entries:
            self.assertFalse(hasattr(entry, "direction"))
            self.assertFalse(hasattr(entry, "signal"))

    def test_exclusion_reasons_are_explicit(self) -> None:
        snap = self._scan(
            [ev("OKUSDT"), ev("LOWUSDT"), ev("WIDEUSDT"), ev("NOTICKUSDT"),
             ev("NOBOOKUSDT"), ev("STALEUSDT"), ev("USDCUSDT", False, ("EXCLUDED_STABLECOIN_OR_FIAT_BASE:USDC",)),
             ev("BADBOOKUSDT")],
            [tk("OKUSDT", 50e6), tk("LOWUSDT", 1e6), tk("WIDEUSDT", 50e6), tk("NOBOOKUSDT", 50e6),
             tk("STALEUSDT", 50e6, age_s=3600), tk("USDCUSDT", 900e6), tk("BADBOOKUSDT", 50e6)],
            [bk("OKUSDT"), bk("LOWUSDT"), bk("WIDEUSDT", 100.0, 101.0), bk("NOTICKUSDT"),
             bk("STALEUSDT"), bk("USDCUSDT"), bk("BADBOOKUSDT", 100.0, 99.0)],
        )
        by = self._by_symbol(snap)
        self.assertEqual(by["OKUSDT"].status, "SHORTLISTED")
        self.assertIn("BELOW_MIN_QUOTE_VOLUME", by["LOWUSDT"].exclusion_reasons)
        self.assertIn("SPREAD_TOO_WIDE", by["WIDEUSDT"].exclusion_reasons)
        self.assertIn("NO_TICKER_DATA", by["NOTICKUSDT"].exclusion_reasons)
        self.assertIn("NO_BOOK_TICKER", by["NOBOOKUSDT"].exclusion_reasons)
        self.assertIn("STALE_TICKER_DATA", by["STALEUSDT"].exclusion_reasons)
        self.assertIn("INVALID_BOOK_TICKER", by["BADBOOKUSDT"].exclusion_reasons)
        self.assertEqual(by["USDCUSDT"].exclusion_reasons, ("EXCLUDED_STABLECOIN_OR_FIAT_BASE:USDC",))
        for name in ("LOWUSDT", "WIDEUSDT", "NOTICKUSDT", "NOBOOKUSDT", "STALEUSDT", "USDCUSDT", "BADBOOKUSDT"):
            self.assertEqual(by[name].status, "EXCLUDED")
            self.assertIsNone(by[name].rank)

    def test_shortlist_is_capped_at_max_candidates(self) -> None:
        symbols = [f"C{i:02d}USDT" for i in range(35)]
        snap = self._scan(
            [ev(s) for s in symbols],
            [tk(s, 1e9 - i * 1e6) for i, s in enumerate(symbols)],
            [bk(s) for s in symbols],
        )
        self.assertEqual(len(snap.shortlisted), 30)
        self.assertEqual(sum(1 for e in snap.entries if e.status == "RANKED_NOT_SHORTLISTED"), 5)

    def test_non_usdt_symbols_are_skipped_and_counted(self) -> None:
        snap = self._scan(
            [ev("AAAUSDT"), ev("ETHBTC", quote="BTC")],
            [tk("AAAUSDT", 50e6)], [bk("AAAUSDT")],
        )
        self.assertEqual(len(snap.entries), 1)
        self.assertEqual(snap.non_target_quote_skipped, 1)

    def test_categories_are_assigned_from_config_and_do_not_affect_rank(self) -> None:
        snap = self._scan(
            [ev("NVDABUSDT"), ev("XAUTUSDT"), ev("AAAUSDT")],
            [tk("NVDABUSDT", 90e6), tk("XAUTUSDT", 50e6), tk("AAAUSDT", 20e6)],
            [bk("NVDABUSDT"), bk("XAUTUSDT"), bk("AAAUSDT")],
        )
        by = self._by_symbol(snap)
        self.assertEqual(by["NVDABUSDT"].category, "TOKENIZED_STOCK")
        self.assertEqual(by["XAUTUSDT"].category, "COMMODITY")
        self.assertEqual(by["AAAUSDT"].category, "CRYPTO")
        self.assertEqual([e.symbol for e in snap.entries], ["NVDABUSDT", "XAUTUSDT", "AAAUSDT"])
        self.assertEqual(MarketScanner.replay(snap), snap.entries)

    def test_config_rejects_asset_in_two_categories(self) -> None:
        from packages.config.settings import UniverseConfig
        with self.assertRaises(ValueError):
            UniverseConfig(asset_categories={"A": ["X"], "B": ["x"]})
        with self.assertRaises(ValueError):
            UniverseConfig(asset_categories={"CRYPTO": ["X"]})

    def test_replay_reproduces_ranking_from_stored_inputs(self) -> None:
        snap = self._scan(
            [ev("AAAUSDT"), ev("BBBUSDT"), ev("LOWUSDT")],
            [tk("AAAUSDT", 50e6), tk("BBBUSDT", 90e6), tk("LOWUSDT", 1e6)],
            [bk("AAAUSDT"), bk("BBBUSDT"), bk("LOWUSDT")],
        )
        self.assertEqual(MarketScanner.replay(snap), snap.entries)
        # Changing live data afterwards cannot change what the stored snapshot says.
        self.assertEqual(MarketScanner.replay(snap), snap.entries)


if __name__ == "__main__":
    unittest.main()
