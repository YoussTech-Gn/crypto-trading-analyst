"""Unit tests for symbol discovery and configurable exclusion reason tracking."""

from __future__ import annotations

import unittest
from pathlib import Path

from packages.config.settings import load_config
from packages.market_data.discovery import SymbolDiscoveryService
from packages.market_data.models import SymbolInfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"


class TestSymbolDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_config(DEFAULT_CONFIG_PATH)
        self.service = SymbolDiscoveryService(
            universe_config=self.cfg.universe,
            quote_asset=self.cfg.exchange.quote_asset,
        )

    def test_eligible_usdt_spot_symbols_pass(self) -> None:
        btc = SymbolInfo(
            symbol="BTCUSDT",
            status="TRADING",
            base_asset="BTC",
            quote_asset="USDT",
            is_spot_trading_allowed=True,
            permissions=("SPOT",),
        )
        result = self.service.evaluate_symbol(btc)
        self.assertTrue(result.is_eligible)
        self.assertEqual(result.exclusion_reasons, ())

    def test_excludes_non_usdt_and_halted_and_non_spot(self) -> None:
        eth_btc = SymbolInfo(
            symbol="ETHBTC",
            status="BREAK",
            base_asset="ETH",
            quote_asset="BTC",
            is_spot_trading_allowed=False,
            permissions=("MARGIN",),
        )
        result = self.service.evaluate_symbol(eth_btc)
        self.assertFalse(result.is_eligible)
        self.assertIn("NON_TARGET_QUOTE_ASSET:BTC", result.exclusion_reasons)
        self.assertIn("EXCHANGE_STATUS_NOT_TRADING:BREAK", result.exclusion_reasons)
        self.assertIn("SPOT_TRADING_NOT_ALLOWED", result.exclusion_reasons)
        self.assertIn("MISSING_SPOT_PERMISSION", result.exclusion_reasons)

    def test_excludes_stablecoins_with_explicit_reason(self) -> None:
        for base in ("USDC", "FDUSD", "DAI", "TUSD", "EUR"):
            info = SymbolInfo(
                symbol=f"{base}USDT",
                status="TRADING",
                base_asset=base,
                quote_asset="USDT",
                is_spot_trading_allowed=True,
                permissions=("SPOT",),
            )
            ev = self.service.evaluate_symbol(info)
            self.assertFalse(ev.is_eligible)
            self.assertIn(f"EXCLUDED_STABLECOIN_OR_FIAT_BASE:{base}", ev.exclusion_reasons)

    def test_excludes_leveraged_tokens_explicit_and_suffix(self) -> None:
        btc_up = SymbolInfo(
            symbol="BTCUPUSDT",
            status="TRADING",
            base_asset="BTCUP",
            quote_asset="USDT",
            is_spot_trading_allowed=True,
            permissions=("SPOT",),
        )
        ev_explicit = self.service.evaluate_symbol(btc_up)
        self.assertFalse(ev_explicit.is_eligible)
        self.assertIn("EXCLUDED_LEVERAGED_TOKEN_EXPLICIT:BTCUP", ev_explicit.exclusion_reasons)

        sol_bull = SymbolInfo(
            symbol="SOLBULLUSDT",
            status="TRADING",
            base_asset="SOLBULL",
            quote_asset="USDT",
            is_spot_trading_allowed=True,
            permissions=("SPOT",),
        )
        ev_suffix = self.service.evaluate_symbol(sol_bull)
        self.assertFalse(ev_suffix.is_eligible)
        self.assertIn("EXCLUDED_LEVERAGED_TOKEN_SUFFIX:BULL", ev_suffix.exclusion_reasons)

    def test_does_not_falsely_exclude_short_base_symbol_matching_suffix(self) -> None:
        # 'UP' has length 2 (< len('UP') + 2 = 4), so it should NOT trigger the suffix rule
        short_token = SymbolInfo(
            symbol="UPUSDT",
            status="TRADING",
            base_asset="UP",
            quote_asset="USDT",
            is_spot_trading_allowed=True,
            permissions=("SPOT",),
        )
        ev = self.service.evaluate_symbol(short_token)
        self.assertTrue(ev.is_eligible)

    def test_discover_report_partitions_and_sorts_symbols(self) -> None:
        symbols = [
            SymbolInfo("SOLUSDT", "TRADING", "SOL", "USDT", True, ("SPOT",)),
            SymbolInfo("BTCUSDT", "TRADING", "BTC", "USDT", True, ("SPOT",)),
            SymbolInfo("USDCUSDT", "TRADING", "USDC", "USDT", True, ("SPOT",)),
        ]
        report = self.service.discover(symbols)
        self.assertEqual(report.total_exchange_symbols, 3)
        self.assertEqual([s.symbol for s in report.eligible_symbols], ["BTCUSDT", "SOLUSDT"])
        self.assertEqual([s.symbol for s in report.excluded_symbols], ["USDCUSDT"])


if __name__ == "__main__":
    unittest.main()


class TestMissingPermissionMetadata(unittest.TestCase):
    def test_empty_permissions_are_excluded_fail_closed(self) -> None:
        from packages.config.settings import load_config
        cfg = load_config(Path(__file__).resolve().parents[2] / "config" / "default.yaml")
        service = SymbolDiscoveryService(cfg.universe, cfg.exchange.quote_asset)
        info = SymbolInfo(
            symbol="BTCUSDT", status="TRADING", base_asset="BTC", quote_asset="USDT",
            is_spot_trading_allowed=True, permissions=(),
        )
        result = service.evaluate_symbol(info)
        self.assertFalse(result.is_eligible)
        self.assertIn("MISSING_SPOT_PERMISSION", result.exclusion_reasons)

