"""Unit tests for configuration loading and safety boundary validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from packages.config.settings import ConfigValidationError, load_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"


class TestConfigValidation(unittest.TestCase):
    def test_loads_default_yaml_with_approved_provisional_defaults(self) -> None:
        cfg = load_config(DEFAULT_CONFIG_PATH)
        self.assertEqual(cfg.exchange.name, "binance")
        self.assertEqual(cfg.exchange.market, "spot")
        self.assertEqual(cfg.exchange.quote_asset, "USDT")
        self.assertEqual(cfg.universe.max_candidates, 30)
        self.assertEqual(cfg.universe.min_quote_volume_24h, 10_000_000.0)
        self.assertEqual(cfg.universe.max_spread_bps, 20.0)
        self.assertEqual(cfg.timeframes.context, "1d")
        self.assertEqual(cfg.timeframes.setup, "4h")
        self.assertTrue(cfg.timeframes.use_closed_candles)
        self.assertEqual(cfg.timeframes.min_closed_candles_1d, 200)
        self.assertEqual(cfg.timeframes.min_closed_candles_4h, 500)
        self.assertEqual(cfg.timeframes.max_close_delay_seconds, 300)
        self.assertEqual(cfg.strategy.active_version, "baseline-1.0")
        self.assertEqual(cfg.strategy.direction, "long_only")
        self.assertEqual(cfg.strategy.minimum_reward_to_risk, 2.0)
        self.assertEqual(cfg.risk.mode, "paper")
        self.assertEqual(cfg.risk.simulated_equity, 10_000.0)
        self.assertEqual(cfg.risk.risk_per_trade_percent, 1.0)
        self.assertEqual(cfg.risk.max_open_positions, 3)
        self.assertFalse(cfg.execution.real_orders_enabled)
        self.assertTrue(cfg.execution.paper_trading_enabled)

    def test_rejects_real_orders_enabled(self) -> None:
        with self.assertRaises(ConfigValidationError) as ctx:
            load_config(
                DEFAULT_CONFIG_PATH,
                overrides={"execution": {"real_orders_enabled": True}},
            )
        self.assertIn("real_orders_enabled", str(ctx.exception))

    def test_rejects_unfinished_candles_setting(self) -> None:
        with self.assertRaises(ConfigValidationError) as ctx:
            load_config(
                DEFAULT_CONFIG_PATH,
                overrides={"timeframes": {"use_closed_candles": False}},
            )
        self.assertIn("use_closed_candles", str(ctx.exception))

    def test_rejects_non_spot_or_non_usdt(self) -> None:
        with self.assertRaises(ConfigValidationError):
            load_config(
                DEFAULT_CONFIG_PATH,
                overrides={"exchange": {"market": "futures"}},
            )
        with self.assertRaises(ConfigValidationError):
            load_config(
                DEFAULT_CONFIG_PATH,
                overrides={"exchange": {"quote_asset": "BTC"}},
            )

    def test_rejects_invalid_numeric_thresholds(self) -> None:
        with self.assertRaises(ConfigValidationError):
            load_config(
                DEFAULT_CONFIG_PATH,
                overrides={"universe": {"min_quote_volume_24h": -100}},
            )
        with self.assertRaises(ConfigValidationError):
            load_config(
                DEFAULT_CONFIG_PATH,
                overrides={"timeframes": {"max_close_delay_seconds": 0}},
            )

    def test_rejects_missing_or_malformed_yaml_file(self) -> None:
        with self.assertRaises(ConfigValidationError):
            load_config(PROJECT_ROOT / "config" / "nonexistent.yaml")

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
            tmp.write("exchange: [invalid: yaml: {")
            tmp_path = Path(tmp.name)
        try:
            with self.assertRaises(ConfigValidationError):
                load_config(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
