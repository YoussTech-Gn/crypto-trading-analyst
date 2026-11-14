"""Unit tests for deterministic 1D/4H candle validation, staleness, delay, and fail-closed guards."""

from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone
from pathlib import Path

from packages.config.settings import load_config
from packages.market_data.models import (
    Candle,
    DataFreshnessStatus,
    UnreliableMarketDataError,
)
from packages.market_data.validator import TIMEFRAME_INTERVAL_MS, CandleValidator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"


def build_candle_series(
    symbol: str,
    timeframe: str,
    count: int,
    latest_open_time_ms: int,
    include_unfinished_bar: bool = False,
) -> list[Candle]:
    interval_ms = TIMEFRAME_INTERVAL_MS[timeframe]
    start_open_ms = latest_open_time_ms - (count - 1) * interval_ms
    candles: list[Candle] = []
    for i in range(count):
        open_ms = start_open_ms + i * interval_ms
        close_ms = open_ms + interval_ms - 1
        base_price = 50_000.0 + i * 10.0
        candles.append(
            Candle(
                symbol=symbol,
                timeframe=timeframe,
                open_time_ms=open_ms,
                close_time_ms=close_ms,
                open=base_price,
                high=base_price + 50.0,
                low=base_price - 40.0,
                close=base_price + 20.0,
                volume=120.5,
                quote_volume=120.5 * base_price,
                trade_count=1500,
            )
        )
    if include_unfinished_bar:
        next_open = latest_open_time_ms + interval_ms
        candles.append(
            Candle(
                symbol=symbol,
                timeframe=timeframe,
                open_time_ms=next_open,
                close_time_ms=next_open + interval_ms - 1,
                open=52_000.0,
                high=52_100.0,
                low=51_950.0,
                close=52_050.0,
                volume=15.0,
                quote_volume=780_000.0,
                trade_count=200,
            )
        )
    return candles


class TestCandleValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_config(DEFAULT_CONFIG_PATH)
        self.validator = CandleValidator(self.cfg.timeframes)
        # Fixed reference UTC time: 2026-11-13 04:02:00 UTC (120s after the 04:00:00 UTC 4H boundary)
        self.ref_time_utc = datetime(2026, 11, 13, 4, 2, 0, tzinfo=timezone.utc)
        self.ref_ms = int(self.ref_time_utc.timestamp() * 1000)
        self.interval_4h = TIMEFRAME_INTERVAL_MS["4h"]
        self.interval_1d = TIMEFRAME_INTERVAL_MS["1d"]

        # At 04:02:00 UTC, the most recently completed 4h candle opened at 00:00:00 UTC and closed at 03:59:59.999 UTC
        self.expected_4h_close_boundary = (self.ref_ms // self.interval_4h) * self.interval_4h
        self.expected_4h_latest_open = self.expected_4h_close_boundary - self.interval_4h

        # At 04:02:00 UTC, the most recently completed 1d candle opened yesterday at 00:00:00 UTC
        self.expected_1d_close_boundary = (self.ref_ms // self.interval_1d) * self.interval_1d
        self.expected_1d_latest_open = self.expected_1d_close_boundary - self.interval_1d

    def test_valid_4h_and_1d_series_with_unfinished_candle_filtered(self) -> None:
        candles_4h = build_candle_series(
            "BTCUSDT",
            "4h",
            count=500,
            latest_open_time_ms=self.expected_4h_latest_open,
            include_unfinished_bar=True,
        )
        res_4h = self.validator.validate(
            "BTCUSDT", "4h", candles_4h, reference_time_utc=self.ref_time_utc
        )
        self.assertTrue(res_4h.is_valid)
        self.assertTrue(res_4h.analysis_allowed)
        self.assertEqual(res_4h.freshness_status, DataFreshnessStatus.FRESH)
        self.assertEqual(len(res_4h.closed_candles), 500)
        self.assertEqual(len(res_4h.unfinished_candles), 1)
        self.assertEqual(res_4h.close_delay_seconds, 0.0)
        self.assertEqual(len(res_4h.require_valid_for_analysis()), 500)

        candles_1d = build_candle_series(
            "BTCUSDT",
            "1d",
            count=200,
            latest_open_time_ms=self.expected_1d_latest_open,
            include_unfinished_bar=True,
        )
        res_1d = self.validator.validate(
            "BTCUSDT", "1d", candles_1d, reference_time_utc=self.ref_time_utc
        )
        self.assertTrue(res_1d.is_valid)
        self.assertEqual(res_1d.freshness_status, DataFreshnessStatus.FRESH)
        self.assertEqual(len(res_1d.closed_candles), 200)
        self.assertEqual(len(res_1d.unfinished_candles), 1)

    def test_distinguishes_delayed_candle_availability_within_5_minutes(self) -> None:
        # At 04:02:00 UTC (120s past 04:00 close), if the 00:00..04:00 bar is not yet available
        # and the latest closed bar is 20:00..00:00, status must be DELAYED_CANDLE_AVAILABILITY
        # and downstream analysis must be blocked.
        prev_4h_open = self.expected_4h_latest_open - self.interval_4h
        candles_delayed = build_candle_series(
            "BTCUSDT",
            "4h",
            count=500,
            latest_open_time_ms=prev_4h_open,
        )
        res = self.validator.validate(
            "BTCUSDT", "4h", candles_delayed, reference_time_utc=self.ref_time_utc
        )
        self.assertFalse(res.is_valid)
        self.assertFalse(res.analysis_allowed)
        self.assertEqual(
            res.freshness_status, DataFreshnessStatus.DELAYED_CANDLE_AVAILABILITY
        )
        self.assertAlmostEqual(res.close_delay_seconds or 0.0, 120.0, places=1)
        with self.assertRaises(UnreliableMarketDataError):
            res.require_valid_for_analysis()

    def test_declares_stale_data_when_delay_exceeds_5_minutes(self) -> None:
        # At 04:05:01 UTC (301s past 04:00 close, exceeding 300s max_close_delay_seconds),
        # missing the 00:00..04:00 bar must be classified as STALE_DATA (not delayed).
        late_ref_utc = datetime(2026, 11, 13, 4, 5, 1, tzinfo=timezone.utc)
        prev_4h_open = self.expected_4h_latest_open - self.interval_4h
        candles_stale = build_candle_series(
            "BTCUSDT",
            "4h",
            count=500,
            latest_open_time_ms=prev_4h_open,
        )
        res = self.validator.validate(
            "BTCUSDT", "4h", candles_stale, reference_time_utc=late_ref_utc
        )
        self.assertFalse(res.is_valid)
        self.assertFalse(res.analysis_allowed)
        self.assertEqual(res.freshness_status, DataFreshnessStatus.STALE_DATA)
        self.assertAlmostEqual(res.close_delay_seconds or 0.0, 301.0, places=1)
        with self.assertRaises(UnreliableMarketDataError):
            res.require_valid_for_analysis()

    def test_detects_internal_missing_candles(self) -> None:
        candles = build_candle_series(
            "BTCUSDT",
            "4h",
            count=501,
            latest_open_time_ms=self.expected_4h_latest_open,
        )
        # Drop an internal bar
        del candles[250]
        res = self.validator.validate(
            "BTCUSDT", "4h", candles, reference_time_utc=self.ref_time_utc
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.freshness_status, DataFreshnessStatus.MISSING_CANDLES)
        with self.assertRaises(UnreliableMarketDataError):
            res.require_valid_for_analysis()

    def test_detects_duplicate_and_out_of_order_candles(self) -> None:
        candles = build_candle_series(
            "BTCUSDT",
            "1d",
            count=200,
            latest_open_time_ms=self.expected_1d_latest_open,
        )
        dup_series = list(candles) + [candles[-1]]
        res_dup = self.validator.validate(
            "BTCUSDT", "1d", dup_series, reference_time_utc=self.ref_time_utc
        )
        self.assertFalse(res_dup.is_valid)
        self.assertEqual(res_dup.freshness_status, DataFreshnessStatus.DUPLICATE_CANDLES)

        swapped = list(candles)
        swapped[10], swapped[11] = swapped[11], swapped[10]
        res_ooo = self.validator.validate(
            "BTCUSDT", "1d", swapped, reference_time_utc=self.ref_time_utc
        )
        self.assertFalse(res_ooo.is_valid)
        self.assertEqual(
            res_ooo.freshness_status, DataFreshnessStatus.OUT_OF_ORDER_TIMESTAMPS
        )

    def test_detects_insufficient_history(self) -> None:
        candles_1d = build_candle_series(
            "BTCUSDT",
            "1d",
            count=199,  # 1 short of 200 minimum
            latest_open_time_ms=self.expected_1d_latest_open,
        )
        res = self.validator.validate(
            "BTCUSDT", "1d", candles_1d, reference_time_utc=self.ref_time_utc
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.freshness_status, DataFreshnessStatus.INSUFFICIENT_HISTORY)

    def test_detects_malformed_ohlcv_values(self) -> None:
        candles = build_candle_series(
            "BTCUSDT",
            "1d",
            count=200,
            latest_open_time_ms=self.expected_1d_latest_open,
        )
        bad = candles[50]
        # High < Open violates OHLC invariant
        candles[50] = Candle(
            symbol=bad.symbol,
            timeframe=bad.timeframe,
            open_time_ms=bad.open_time_ms,
            close_time_ms=bad.close_time_ms,
            open=50_000.0,
            high=49_000.0,
            low=48_000.0,
            close=49_500.0,
            volume=math.nan,
            quote_volume=1000.0,
            trade_count=10,
        )
        res = self.validator.validate(
            "BTCUSDT", "1d", candles, reference_time_utc=self.ref_time_utc
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.freshness_status, DataFreshnessStatus.MALFORMED_CANDLE_DATA)


if __name__ == "__main__":
    unittest.main()
