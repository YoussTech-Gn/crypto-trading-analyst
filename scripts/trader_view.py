"""Trader view (ADR-042): one screen that says, in plain words, what the market is doing and what each tracked rule is
waiting for. Public data only, no orders, NOT advice. It records nothing (the journal is still `forward_journal.py`).

  python scripts/trader_view.py              live, last closed 4H candle (needs internet)
  python scripts/trader_view.py --offline    from data/cache (old data; for testing without internet)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.analysis import AnalysisEngine  # noqa: E402
from packages.backtest.cache import CandleCache  # noqa: E402
from packages.config.settings import load_config  # noqa: E402
from packages.journal.forward import TRACKED  # noqa: E402
from packages.reporting import run_guarded  # noqa: E402
from packages.signals.market_view import market_view  # noqa: E402  # noqa: E402
from packages.strategies import build_recipes  # noqa: E402
from scripts.run_lab import BASKETS  # noqa: E402


def utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load_series(cfg, offline: bool):
    syms = BASKETS["main"].split(",")
    out, skipped = {}, []
    if offline:
        cache = CandleCache(ROOT / "data" / "cache")
        for s in syms:
            d = [c for _, c in sorted(cache.load(s, "1d")[0].items())]
            h = [c for _, c in sorted(cache.load(s, "4h")[0].items())]
            if d and h:
                out[s] = (d, h)
            else:
                skipped.append(s)
        return out, skipped
    from packages.market_data.client import BinancePublicClient
    from packages.market_data.validator import CandleValidator
    from scripts.forward_journal import fetch
    validator = CandleValidator(cfg.timeframes)
    with BinancePublicClient(cfg.exchange) as client:
        for s in syms:
            try:
                out[s] = (fetch(client, validator, s, "1d", cfg.backtest.analysis_window_1d + 20),
                          fetch(client, validator, s, "4h", cfg.backtest.analysis_window_4h))
            except Exception as exc:  # fail closed per coin
                skipped.append(f"{s} ({str(exc)[:40]})")
    return out, skipped


def render_text(v: dict, offline: bool, skipped: list) -> str:
    L = [f"MARKET VIEW  last closed 4H candle: {utc(v['last_close_ms'])}" + ("   (OFFLINE: cached data, NOT today's market)" if offline else ""),
         "Paper research only. Not financial advice. Nothing here is a buy or sell recommendation.", "",
         f"BITCOIN daily trend: {v['btc_trend']}",
         f"Coins in a daily UPtrend: {len(v['up'])} of {v['coins']}" + (f" ({', '.join(v['up'])})" if v["up"] else ""), "",
         "SIGNALS NOW: " + ("none" if not v["signals"] else "")]
    L += [f"  {s['coin']} {s['rule']}: entry {s['entry']:.6g}, stop {s['stop']:.6g}, target {s['target']:.6g}" for s in v["signals"]]
    L += ["", "CLOSEST TO A SIGNAL (only one condition missing):"]
    L += [f"  {c['coin']:<6} {c['rule']:<22} only {c['missing']}" for c in v["close_calls"]] or \
         ["  none - every rule is missing two or more conditions"]
    L += ["", f"{'COIN':<6} {'PRICE':>11}  {'DAILY TREND':<28}" + "".join(f"{h:<16}" for h in v["rule_heads"])]
    for r in v["rows"]:
        L.append(f"{r['coin']:<6} {r['price']:>11.6g}  {r['trend']:<28}" + "".join(f"{c:<16}" for c in r["cells"]))
    if skipped:
        L += ["", "Skipped (bad or missing data, never guessed): " + ", ".join(skipped)]
    L += ["", "HOW TO READ: each rule signals only when ALL its conditions are true at the close of a 4H candle.",
          "'2 missing' = two conditions are still false; 0 missing = SIGNAL. The daily trend must be UP for every rule.",
          "Rules: BREAKOUT55 = close above the 55-candle high; BREAKOUT20+BTC = close above the 20-candle high while Bitcoin trends up;",
          "FALSE-BREAK = a wick below a low that closes back above it (your rule). To RECORD signals, keep forward_journal.py running."]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    series, skipped = load_series(cfg, a.offline)
    if "BTCUSDT" not in series:
        print("Bitcoin data unavailable (no internet or Binance unreachable). Nothing to show; nothing was recorded.")
        return 1
    v = market_view(AnalysisEngine(cfg.analysis), build_recipes(cfg, list(TRACKED)), series,
                    cfg.backtest.analysis_window_1d, cfg.backtest.analysis_window_4h)
    print(render_text(v, a.offline, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(run_guarded("trader_view", main))
