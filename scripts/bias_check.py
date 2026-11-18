"""Look-ahead and warm-up bias checks on cached candles (ADR-041). Offline: reads data/cache only, no network, no orders.

  python scripts/bias_check.py                      (BTCUSDT, ETHUSDT, SOLUSDT)
  python scripts/bias_check.py --symbols BNBUSDT --samples 40 --decision-steps 60
Writes reports/bias_check.txt. Exit code 1 if any learning feature looks ahead.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.analysis import AnalysisEngine  # noqa: E402
from packages.backtest.bias import lookahead_features, recursive_decisions, recursive_features  # noqa: E402
from packages.backtest.cache import CandleCache  # noqa: E402
from packages.config.settings import load_config  # noqa: E402
from packages.journal.forward import TRACKED  # noqa: E402
from packages.learning.dataset import build_symbol, load_cache_arrays  # noqa: E402
from packages.strategies import build_recipes  # noqa: E402

CACHE = ROOT / "data" / "cache"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--samples", type=int, default=25, help="candles checked for look-ahead per symbol")
    ap.add_argument("--decision-steps", type=int, default=40, help="recent closed candles checked for decision warm-up")
    a = ap.parse_args()
    cfg = load_config()
    engine = AnalysisEngine(cfg.analysis)
    recipes = build_recipes(cfg, list(TRACKED))
    cache = CandleCache(CACHE)
    L = ["BIAS CHECK (ADR-041; ideas from Freqtrade lookahead-analysis and recursive-analysis)", ""]
    leak = False
    for sym in [s.strip().upper() for s in a.symbols.split(",") if s.strip()]:
        a4, a1 = load_cache_arrays(CACHE / f"{sym}_4h.json"), load_cache_arrays(CACHE / f"{sym}_1d.json")
        if a4 is None or a1 is None:
            L.append(f"{sym}: not in data/cache (run scripts/overnight.py once)")
            continue
        n = len(a4["c"])
        idx = np.linspace(300, n - 1, a.samples).astype(int)
        la = lookahead_features(build_symbol, a4, a1, idx)
        bad = {k: v for k, v in la.items() if v}
        leak |= bool(bad)
        L.append(f"{sym}: look-ahead in learning features: " + ("NONE (all features identical with the future removed)" if not bad
                                                                else f"FOUND {bad}"))
        rf = recursive_features(build_symbol, a4, a1)
        top = sorted(rf.items(), key=lambda kv: -kv[1])[:5]
        L.append(f"{sym}: warm-up sensitivity of features (largest relative difference, startups 200/500/1000): "
                 + ", ".join(f"{k} {v:.2e}" for k, v in top))
        _, cov = cache.load(sym, "4h")
        daily = [c for _, c in sorted(cache.load(sym, "1d")[0].items())]
        setup = [c for _, c in sorted(cache.load(sym, "4h")[0].items())]
        steps = range(len(setup) - a.decision_steps, len(setup))
        rd = recursive_decisions(engine, recipes, sym, daily, setup, steps)
        L.append(f"{sym}: recipe decisions that change between a 600 and a 900 candle window: "
                 + ", ".join(f"{k} {v['changed']}/{v['steps']}" for k, v in rd.items()))
        L.append("")
    L.append("VERDICT: " + ("LOOK-AHEAD FOUND - fix before trusting any result" if leak else "no look-ahead found in the sampled candles"))
    text = "\n".join(L) + "\n"
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "bias_check.txt").write_text(text, encoding="utf-8")
    print(text)
    return 1 if leak else 0


if __name__ == "__main__":
    sys.exit(main())
