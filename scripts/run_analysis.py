"""Analyse one symbol on live public data (read-only). Usage: python scripts/run_analysis.py BTCUSDT"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.reporting import run_guarded
from packages.analysis import AnalysisEngine
from packages.config.settings import load_config
from packages.market_data.client import BinancePublicClient
from packages.market_data.validator import CandleValidator


def ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def main() -> int:
    symbol = (sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT").upper()
    cfg = load_config()
    validator = CandleValidator(cfg.timeframes)
    series = {}
    with BinancePublicClient(cfg.exchange) as client:
        for tf in ("1d", "4h"):
            raw = client.fetch_klines(symbol, tf, limit=300 if tf == "1d" else 600)
            res = validator.validate(symbol, tf, raw)
            if not res.analysis_allowed:
                print(f"EXCLUDED: {symbol} {tf} data not valid for analysis: {res.issues}")
                return 1
            series[tf] = list(res.closed_candles)
    r = AnalysisEngine(cfg.analysis).analyze(symbol, series["1d"], series["4h"])
    print(f"{symbol}  1D last closed: {ts(r.daily_last_open_time_ms)}  4H last closed: {ts(r.setup_last_open_time_ms)}")
    print("Daily bullish:", r.daily_trend["bullish"], "| failed:", r.daily_trend["failed_conditions"])
    print("Indicators:", r.indicators)
    print("Recent 4H sweep events (one per candle, sell-side):")
    for e in r.sweep_events[-5:]:
        lv = ", ".join(f"{l['kind']}@{round(l['price'], 6)}" for l in e["levels"])
        print("  ", ts(e["sweep_time_ms"]), f"deepest={e['deepest_penetration_pct']:.3f}%", lv)
    print("Recent 4H bullish FVGs:")
    for g in r.fair_value_gaps[-5:]:
        print("  ", ts(g["formed_time_ms"]), f"[{g['lower']}, {g['upper']}]", g["status"])
    print("Recent 4H structure breaks:")
    for b in r.structure_breaks[-5:]:
        print("  ", ts(b["break_time_ms"]), b["direction"], b["level"])
    print(r.note)
    return 0


if __name__ == "__main__":
    sys.exit(run_guarded("run_analysis", main))
