"""Strategy lab: run every recipe on the same windows and symbols, then score each against the goal.

Usage:
  python scripts/run_lab.py                              (main basket, windows 0,730,1460 days back, all recipes)
  python scripts/run_lab.py --basket alt                 (a different set of symbols the strategies never saw)
  python scripts/run_lab.py --windows 0 --recipes sweep_fvg,sweep_only      (quick check)
  python scripts/run_lab.py --recipes fvg_only,fvg_exit_1r,fvg_exit_be      (a family comparison)
  python scripts/run_lab.py --offline --as-of 2026-11-14   (use only the candle cache, windows anchored at a fixed date)
Output: reports/lab_<tag>.txt and .json (tag = basket unless --tag is given; printed too). Public data only, no orders.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.backtest import Backtester
from packages.backtest.cache import CandleCache
from packages.backtest.data import fetch_history, load_validated
from packages.config.settings import load_config
from packages.market_data.client import BinancePublicClient
from packages.market_data.validator import CandleValidator
from packages.reporting import run_guarded, write_failure_report
from packages.strategies import Goal, build_recipes, score_recipe, z_for_trials
from packages.strategies.scorecard import register_trials

DAY_MS = 86_400_000
FIRST_CLEAN_DATA_MS = 1_588_291_200_000  # 2020-05-01 00:00 UTC
BASKETS = {
    "main": "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,LINKUSDT,AVAXUSDT,LTCUSDT,TRXUSDT,SUIUSDT,UNIUSDT,"
            "NEARUSDT,ARBUSDT,INJUSDT,DOTUSDT,ATOMUSDT,AAVEUSDT,FILUSDT,APTUSDT,OPUSDT,TAOUSDT,ENAUSDT,HBARUSDT",
    "alt": "BCHUSDT,ETCUSDT,XLMUSDT,ALGOUSDT,VETUSDT,SANDUSDT,MANAUSDT,AXSUSDT,GRTUSDT,EGLDUSDT,THETAUSDT,ICPUSDT,"
           "RUNEUSDT,CRVUSDT,SNXUSDT,COMPUSDT,MKRUSDT,ZECUSDT,DASHUSDT,KAVAUSDT,CHZUSDT,ENJUSDT,SUSHIUSDT,1INCHUSDT,BATUSDT",
}


def work(args):
    """One job = one (window, symbol). Every recipe runs over the same candles and shares one analysis cache,
    so each step is analysed once instead of once per recipe (the analysis does not depend on the recipe)."""
    recipe_names, window, sym, daily, setup, cfg, tainted, regime = args
    recipes = build_recipes(cfg, list(recipe_names))
    cache: dict = {}
    out = {}
    for name, recipe in recipes.items():
        bt = Backtester(cfg.analysis, cfg.signals, cfg.strategy.minimum_reward_to_risk, cfg.backtest,
                        tainted_open_times=tainted, generator=recipe, analysis_cache=cache,
                        regime_daily=regime)
        r = bt.run(sym, daily, setup)
        out[name] = {
            "trades": r.trades, "signals": r.signals, "unfilled": len(r.unfilled),
            "missed_winners": sum(1 for u in r.unfilled if u.missed_winner), "open_at_end": r.open_at_end,
            "skipped_defect": r.steps_skipped_data_defect,
        }
    return window, sym, out


def parse_as_of(text: str | None) -> int:
    """Anchor of the windows in epoch ms. None -> now. Accepts epoch ms or an ISO date (UTC midnight)."""
    if not text:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    if text.isdigit():
        return int(text)
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp() * 1000)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--basket", default="main", choices=sorted(BASKETS))
    ap.add_argument("--symbols", default=None, help="override the basket")
    ap.add_argument("--windows", default="0,730,1460", help="end offsets in days (each window is --days long)")
    ap.add_argument("--days", type=int, default=730)
    ap.add_argument("--recipes", default=None)
    ap.add_argument("--tag", default=None, help="report file tag (default: the basket name)")
    ap.add_argument("--as-of", default=None, help="fix the window anchor (ISO date or epoch ms) so a run can be repeated exactly")
    ap.add_argument("--cache-dir", default=str(ROOT / "data" / "cache"), help="candle cache folder, 'none' disables the cache")
    ap.add_argument("--offline", action="store_true", help="never touch the network: use only what the cache holds")
    ap.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    a = ap.parse_args()
    cfg = load_config()
    names = [n.strip() for n in a.recipes.split(",")] if a.recipes else None
    recipes = build_recipes(cfg, names)
    symbols = [s.strip().upper() for s in (a.symbols or BASKETS[a.basket]).split(",") if s.strip()]
    offsets = [int(x) for x in a.windows.split(",")]
    validator = CandleValidator(cfg.timeframes)
    tag = a.tag or a.basket
    as_of_ms = parse_as_of(a.as_of)
    if a.offline and a.cache_dir == "none":
        print("--offline needs a cache")
        return 2
    cache = None if a.cache_dir == "none" else CandleCache(a.cache_dir)
    fetcher = cache.history(None if a.offline else fetch_history) if cache else None
    t0 = time.time()
    per_recipe: dict[str, dict[str, list]] = {n: {} for n in recipes}
    fills: dict[str, dict[str, int]] = {n: {"signals": 0, "unfilled": 0, "missed_winners": 0, "open_at_end": 0} for n in recipes}
    notes: list[str] = []
    skipped_all: dict[str, dict[str, str]] = {}
    ex = ProcessPoolExecutor(max_workers=a.workers)
    try:
        for off in offsets:
            wname = f"{a.basket}:offset{off}"
            end_ms = as_of_ms - off * DAY_MS
            start_ms = max(end_ms - (a.days + 220) * DAY_MS, FIRST_CLEAN_DATA_MS)
            jobs, skipped = [], {}
            regime = None
            client_cm = None if a.offline else BinancePublicClient(cfg.exchange)
            try:
                client = client_cm.__enter__() if client_cm else None
                try:  # the BTC daily series is the market-regime input of the *_btc recipes; missing -> recipes fail closed
                    regime, _ = load_validated(client, validator, "BTCUSDT", "1d", start_ms, end_ms, fetcher=fetcher)
                except Exception as exc:
                    notes.append(f"{wname}: BTC regime series unavailable ({str(exc)[:100]}); *_btc recipes will not trade here")
                for sym in symbols:
                    try:
                        daily, _ = load_validated(client, validator, sym, "1d", start_ms, end_ms, fetcher=fetcher)
                        setup, tainted = load_validated(client, validator, sym, "4h", start_ms, end_ms, fetcher=fetcher)
                        jobs.append((sym, daily, setup, tainted))
                    except Exception as exc:  # fail closed per symbol
                        skipped[sym] = str(exc)[:160]
            finally:
                if client_cm:
                    client_cm.__exit__(None, None, None)
            skipped_all[wname] = skipped
            print(f"[{wname}] downloaded {len(jobs)} symbols, skipped {len(skipped)}  elapsed={time.time() - t0:.0f}s", flush=True)
            if not jobs:
                notes.append(f"{wname}: no symbol could be loaded, window skipped")
                continue
            names = tuple(recipes)
            futures = [ex.submit(work, (names, wname, s, d, st, cfg, tn, regime)) for (s, d, st, tn) in jobs]
            done = 0
            for fut in as_completed(futures):
                w, sym, out = fut.result()
                for rn, res in out.items():
                    per_recipe[rn].setdefault(w, []).extend(res["trades"])
                    for key in fills[rn]:
                        fills[rn][key] += res[key]
                done += 1
                if done % 25 == 0 or done == len(futures):
                    print(f"  [{wname}] {done}/{len(futures)} jobs  elapsed={time.time() - t0:.0f}s", flush=True)
    except KeyboardInterrupt:
        ex.shutdown(wait=False, cancel_futures=True)
        print("\nINTERRUPTED. No report written (partial results are not trusted).")
        return 130
    ex.shutdown(wait=True)

    k = register_trials(list(recipes))
    goal = Goal()
    cards = {n: score_recipe(per_recipe[n], goal, trials=k) for n in recipes}
    order = sorted(cards, key=lambda n: (-cards[n]["criteria_met"], -(cards[n]["ci_lower_r"] if cards[n]["ci_lower_r"] is not None else -1e9)))

    lines = [f"STRATEGY LAB  {datetime.now(timezone.utc).isoformat()}  basket={a.basket}  tag={tag}  windows={offsets}  days={a.days}  as_of_ms={as_of_ms}  offline={a.offline}",
             f"goal (provisional): {asdict(goal)}",
             f"recipes tried so far (all runs): {k}  ->  confidence z={z_for_trials(k):.2f} (stricter as more recipes are tried)", ""]
    lines.append("RANKING (closest to goal first)")
    for n in order:
        c = cards[n]
        lines.append(f"  {n:<17} criteria_met={c['criteria_met']}/6 trades={c['trades']:>4} avgR={c['avg_r']:+.3f} "
                     f"ciLower={c['ci_lower_r']} (naive {c['ci_lower_naive_r']}) PF={None if c['profit_factor'] is None else round(c['profit_factor'], 2)} "
                     f"maxDD={c['max_drawdown_r']}R  meets_goal={c['meets_goal']}")
    for n in order:
        c, r = cards[n], recipes[n]
        lines += ["", f"--- {n}: {r.description}", f"    parts: {r.components}",
                  f"    windows: {c['windows']}"]
        win_rate = None if c["win_rate"] is None else f"{c['win_rate']:.1%}"
        be = None if c["breakeven_win_rate"] is None else f"{c['breakeven_win_rate']:.1%}"
        lines.append(f"    win_rate={win_rate} breakeven={be}  avg_fee_r={c['avg_fee_r']:+.3f}  weekly_clusters={c['n_clusters']} "
                     f"se_naive={c['se_naive']} se_clustered={c['se_clustered']}")
        f = fills[n]
        filled = c["trades"]
        lines.append(f"    orders: signals={f['signals']} filled={filled} unfilled={f['unfilled']} "
                     f"(missed winners: price reached the target without touching the limit = {f['missed_winners']}) "
                     f"still_open_at_data_end={f['open_at_end']}")
        lines.append("    MISSING: " + ("; ".join(c["unmet"]) if c["unmet"] else "nothing - meets the goal"))
        lines.append("    WHY: " + ("; ".join(c["causes"]) if c["causes"] else "no dominant cause detected"))
    for w, sk in skipped_all.items():
        if sk:
            lines.append(f"\nskipped in {w} (fail-closed): " + "; ".join(f"{s}={m[:70]}" for s, m in list(sk.items())[:12]))
    lines += notes
    lines.append(f"\nelapsed {time.time() - t0:.0f}s")
    text = "\n".join(lines) + "\n"
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / f"lab_{tag}.txt").write_text(text, encoding="utf-8")
    (ROOT / "reports" / f"lab_{tag}.json").write_text(json.dumps(
        {"meta": {"basket": a.basket, "tag": tag, "as_of_ms": as_of_ms, "offsets": offsets, "days": a.days, "symbols": symbols,
                  "offline": a.offline, "skipped": skipped_all, "notes": notes},
         "cards": cards, "trials": k, "fills": fills, "trades": {n: {w: [asdict(t) for t in ts] for w, ts in per_recipe[n].items()} for n in recipes}},
        indent=1, default=str), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(run_guarded("run_lab", main))
