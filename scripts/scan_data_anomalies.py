"""Find every individually broken candle in Binance history (public data, no orders) so we know where clean data starts.

Usage: python scripts/scan_data_anomalies.py [--symbols BTCUSDT,ETHUSDT,SOLUSDT] [--since 2020-05-01]
Output: printed and saved to reports/data_anomalies.txt
Each line = one candle that the validator would reject, with the reason. We then decide: clip the window, or skip.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.backtest.data import fetch_history
from packages.config.settings import load_config
from packages.market_data.client import BinancePublicClient
from packages.market_data.validator import TIMEFRAME_INTERVAL_MS, CandleValidator
from packages.reporting import run_guarded


def day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--since", default="2020-05-01")
    a = ap.parse_args()
    cfg = load_config()
    since = int(datetime.strptime(a.since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    lines = [f"DATA ANOMALY SCAN since {a.since}  (candles the validator would reject, one by one)"]
    all_days: Counter = Counter()
    with BinancePublicClient(cfg.exchange) as client:
        for sym in [s.strip().upper() for s in a.symbols.split(",") if s.strip()]:
            for tf in ("4h", "1d"):
                raw = fetch_history(client, sym, tf, since, now)
                step = TIMEFRAME_INTERVAL_MS[tf]
                bad = []
                for c in raw:
                    for issue in CandleValidator._validate_single_candle(c, step):
                        bad.append((c.open_time_ms, issue.message[:110]))
                # gaps between consecutive candles
                gaps = [(raw[i].open_time_ms, (raw[i + 1].open_time_ms - raw[i].open_time_ms) // step - 1)
                        for i in range(len(raw) - 1) if raw[i + 1].open_time_ms - raw[i].open_time_ms != step]
                lines.append(f"\n{sym} {tf}: candles={len(raw)} broken={len(bad)} gaps={len(gaps)}")
                for ms, msg in bad[:40]:
                    lines.append(f"  BROKEN {day(ms)}  {msg}")
                    all_days[day(ms)[:10]] += 1
                for ms, n in gaps[:20]:
                    lines.append(f"  GAP    after {day(ms)}  missing_candles={n}")
                if bad:
                    lines.append(f"  first broken: {day(bad[0][0])}   last broken: {day(bad[-1][0])}")
                print(f"{sym} {tf} candles={len(raw)} broken={len(bad)} gaps={len(gaps)}", flush=True)
    lines.append(f"\nBroken days across symbols (day: count): {dict(sorted(all_days.items()))}")
    text = "\n".join(lines) + "\n"
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "data_anomalies.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(run_guarded("scan_data_anomalies", main))
