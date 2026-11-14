"""Walk-forward backtest on public Binance history (no keys, no orders).

Usage:
  python scripts/run_backtest.py                       (default liquid basket, 730 days)
  python scripts/run_backtest.py --days 1000 --symbols BTCUSDT,ETHUSDT
Output is printed AND saved to reports/backtest_latest.txt and reports/backtest_latest.json
A result with fewer trades than backtest.min_trades_for_confidence (30) is labelled INSUFFICIENT_SAMPLE.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.reporting import run_guarded, write_failure_report
from packages.backtest import Backtester, summarize
from packages.backtest.data import fetch_history
from packages.backtest.memory import PatternMemory
from packages.backtest.postmortem import build_postmortem
from packages.config.settings import load_config
from packages.market_data.client import BinancePublicClient
from packages.market_data.validator import TIMEFRAME_INTERVAL_MS, CandleValidator

DEFAULT_SYMBOLS = (
    "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,LINKUSDT,AVAXUSDT,LTCUSDT,"
    "TRXUSDT,SUIUSDT,UNIUSDT,NEARUSDT,ARBUSDT,INJUSDT,DOTUSDT,ATOMUSDT,AAVEUSDT,FILUSDT,"
    "APTUSDT,OPUSDT,TAOUSDT,ENAUSDT,HBARUSDT"
)
DAY_MS = 86_400_000
FIRST_CLEAN_DATA_MS = 1_588_291_200_000  # 2020-05-01 00:00 UTC


def work(args):
    symbol, daily, setup, cfg, experiment, tainted = args
    bt = Backtester(cfg.analysis, cfg.signals, cfg.strategy.minimum_reward_to_risk, cfg.backtest,
                    ignore_daily_gate=experiment, tainted_open_times=tainted)
    return bt.run(symbol, daily, setup)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    ap.add_argument("--days", type=int, default=730)
    ap.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--target-mode", default=None, choices=["nearest", "first_meeting_rr"],
                    help="override signals.target_mode for this run (a variant to compare, not the default)")
    ap.add_argument("--end-offset-days", type=int, default=0,
                    help="end the window N days before today. 730 with --days 730 = the OLDER two years (a true hold-out never examined)")
    ap.add_argument("--min-fvg-size-atr", type=float, default=None, help="enable veto signals.min_fvg_size_atr for this run")
    ap.add_argument("--min-relative-volume", type=float, default=None, help="enable veto signals.min_relative_volume for this run")
    ap.add_argument("--experiment-no-daily-gate", action="store_true",
                    help="EXPERIMENT: ignore the daily-trend filter to measure its value. Not the strategy.")
    a = ap.parse_args()
    cfg = load_config()
    if a.target_mode:
        cfg = cfg.model_copy(update={"signals": cfg.signals.model_copy(update={"target_mode": a.target_mode})})
    veto = {k: v for k, v in (("min_fvg_size_atr", a.min_fvg_size_atr), ("min_relative_volume", a.min_relative_volume)) if v is not None}
    if veto:
        cfg = cfg.model_copy(update={"signals": cfg.signals.model_copy(update=veto)})
    symbols = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    now_ms -= a.end_offset_days * DAY_MS
    start_ms = now_ms - (a.days + 220) * DAY_MS  # +220 days so EMA200 is warm at the start
    # Binance 4h history before 2020-05-01 has irregular candle durations (a 2-hour "4h" candle on 2020-04-25).
    # The validator rightly rejects it, so the window never starts earlier than the first clean day.
    start_ms = max(start_ms, FIRST_CLEAN_DATA_MS)
    validator = CandleValidator(cfg.timeframes)
    jobs, skipped = [], {}
    t0 = time.time()
    with BinancePublicClient(cfg.exchange) as client:
        for sym in symbols:
            try:
                series, tainted_by_tf = {}, {}
                for tf in ("1d", "4h"):
                    raw = fetch_history(client, sym, tf, start_ms, now_ms)
                    bad_times = []
                    if tf == "4h":
                        # Known source defect: truncated candles (duration shorter than 4h) in 2020-2021. Tolerated ONLY if the
                        # duration is the sole problem. Their times are handed to the backtester, which skips every step near them.
                        fixed = []
                        for c in raw:
                            issues = CandleValidator._validate_single_candle(c, TIMEFRAME_INTERVAL_MS[tf])
                            if issues and all(i.message.startswith("Unexpected candle duration") for i in issues):
                                bad_times.append(c.open_time_ms)
                                c = replace(c, close_time_ms=c.open_time_ms + TIMEFRAME_INTERVAL_MS[tf] - 1)
                            fixed.append(c)
                        raw = fixed
                    tainted_by_tf[tf] = tuple(bad_times)
                    res = validator.validate(sym, tf, raw, reference_time_utc=datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc))
                    if not res.analysis_allowed:
                        codes = ",".join(sorted({i.code for i in res.issues})) or "INVALID"
                        first = next((i.message for i in res.issues if i.code != "STALE_DATA"), res.issues[0].message if res.issues else "")
                        raise ValueError(f"{tf}:{codes} | first issue: {first}")
                    series[tf] = list(res.closed_candles)
                jobs.append((sym, series["1d"], series["4h"], cfg, a.experiment_no_daily_gate, tainted_by_tf.get("4h", ())))
                print(f"downloaded {sym}: 1d={len(series['1d'])} 4h={len(series['4h'])} truncated_4h_candles_tolerated={len(tainted_by_tf.get('4h', ()))}", flush=True)
            except Exception as exc:  # fail closed per symbol, keep going
                skipped[sym] = str(exc)[:260]
                print(f"SKIPPED {sym}: {skipped[sym]}", flush=True)
    if not jobs:
        detail = "; ".join(f"{k}: {v}" for k, v in skipped.items())
        write_failure_report("run_backtest", f"No symbol could be downloaded or validated. {detail}", context=f"days={a.days}")
        return 2
    print(f"running backtest on {len(jobs)} symbols with {a.workers} workers (about 2-4 min, 5-12 min in experiment mode) ...", flush=True)
    results = []
    ex = ProcessPoolExecutor(max_workers=a.workers)
    try:
        futures = {ex.submit(work, j): j[0] for j in jobs}
        for n, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            results.append(r)
            print(f"  [{n}/{len(jobs)}] {futures[fut]:<10} trades={len(r.trades)} signals={r.signals}  "
                  f"elapsed={time.time() - t0:.0f}s", flush=True)
    except KeyboardInterrupt:
        ex.shutdown(wait=False, cancel_futures=True)
        print(f"\nINTERRUPTED by user after {len(results)}/{len(jobs)} symbols. No report written (partial results are not trusted).")
        return 130
    ex.shutdown(wait=True)
    results.sort(key=lambda r: r.symbol)

    trades = [t for r in results for t in r.trades]
    unfilled = [u for r in results for u in r.unfilled]
    signals = sum(r.signals for r in results)
    summary = summarize(trades, unfilled, signals, cfg.backtest.min_trades_for_confidence)

    lines = [
        f"BACKTEST  {datetime.now(timezone.utc).isoformat()}  days={a.days}  symbols_ok={len(jobs)}  skipped={len(skipped)}",
        f"target_mode={cfg.signals.target_mode}  assumptions: fee={cfg.backtest.fee_pct_per_side}%/side slippage_on_stop={cfg.backtest.stop_slippage_pct}% "
        f"max_hold={cfg.backtest.max_hold_candles} candles, stop wins ties, one position per symbol",
        f"VERDICT: {summary['verdict']}   (trades={summary['filled_trades']}, required>={summary['min_trades_required']})",
        f"signals={summary['signals']}  filled={summary['filled_trades']}  unfilled={summary['unfilled']}  "
        f"fill_rate={summary['fill_rate'] if summary['fill_rate'] is None else round(summary['fill_rate'], 3)}  "
        f"unfilled_that_would_have_hit_target={summary['unfilled_missed_winners']}",
    ]
    if summary["filled_trades"]:
        lo, hi = summary["win_rate_wilson95"]
        lines += [
            f"win_rate={summary['win_rate']:.1%}  95%CI=[{lo:.1%}, {hi:.1%}]  breakeven_win_rate="
            f"{summary['breakeven_win_rate'] if summary['breakeven_win_rate'] is None else round(summary['breakeven_win_rate'], 3)}",
            f"avg_R={summary['avg_r']:.3f}  total_R={summary['total_r']:.2f}  avg_win_R={summary['avg_win_r']:.2f}  "
            f"avg_loss_R={summary['avg_loss_r']:.2f}  profit_factor="
            f"{summary['profit_factor'] if summary['profit_factor'] is None else round(summary['profit_factor'], 2)}",
            f"max_drawdown_R={summary['max_drawdown_r']:.2f}  max_consecutive_losses={summary['max_consecutive_losses']}  "
            f"avg_bars_held={summary['avg_bars_held']:.1f}",
            f"exit_reasons={summary['exit_reasons']}",
        ]
    if a.experiment_no_daily_gate:
        lines.insert(0, "*** EXPERIMENT: daily-trend filter DISABLED. This is NOT the strategy. It measures the filter's value. ***")
    funnel: dict[str, list[int]] = {}
    for r in results:
        for name, (ev, ok) in r.funnel.items():
            row = funnel.setdefault(name, [0, 0])
            row[0] += ev
            row[1] += ok
    analysed = sum(r.analysed_steps for r in results)
    lines.insert(1, f"data defects: truncated 4h candles tolerated={sum(len(j[5]) for j in jobs)}  steps skipped near them={sum(r.steps_skipped_data_defect for r in results)}")
    lines.insert(1, f"window: ends {a.end_offset_days} days before today  vetoes_enabled={veto or 'none'}")
    lines += ["", f"FUNNEL (analysed steps={analysed}; check: evaluated -> passed):"]
    for name, (ev, ok) in funnel.items():
        lines.append(f"  {name:<24} {ev:>7} -> {ok:>7}  ({(ok / ev if ev else 0):.1%})")
    groups = {"daily_bullish=True": [], "daily_bullish=False": []}
    for t in trades:
        groups["daily_bullish=True" if t.context.get("daily_bullish") else "daily_bullish=False"].append(t)
    lines.append("TRADES BY DAILY REGIME AT ENTRY (does the daily filter add value?):")
    for name, g in groups.items():
        if g:
            w = sum(1 for t in g if t.r_multiple > 0)
            lines.append(f"  {name:<20} n={len(g):>3} win_rate={w / len(g):.0%} avg_R={sum(t.r_multiple for t in g) / len(g):+.2f}")
        else:
            lines.append(f"  {name:<20} n=  0")
    pm = build_postmortem(trades)
    lines += ["", "POST-MORTEM (per-trade failure and success analysis):",
              f"  losses={pm['losses']}  expected(rational risk)={pm['expected_losses']}  unexpected(risk-estimate defect)="
              f"{pm['unexpected_losses']}  losses_with_avoidable_pattern={pm['losses_with_avoidable_flags']}  lucky_wins={pm['lucky_wins']}",
              f"  categories: {pm['categories']}"]
    lines.append("  LESSONS (adopted only if confirmed out of the training sample):")
    for ls in pm["lessons"]:
        lines.append(f"   - {ls['flag']} [{ls['verdict']}] {ls['description']} | all trades: with n={ls['all']['n_with']} "
                     f"avgR={ls['all']['avg_r_with']:+.2f} / without n={ls['all']['n_without']} avgR={ls['all']['avg_r_without']:+.2f}"
                     f" | suggested change if confirmed: {ls['suggested_change']}")
    shown = [i for i in pm["items"] if i["outcome"] == "LOSS"]
    shown.sort(key=lambda i: (i["expected"], -len(i["entry_flags"]), i["r"]))
    lines.append("  TOP LOSSES (unexpected first):")
    for i in shown[:12]:
        lines.append(f"   * {i['symbol']} {i['category']} R={i['r']} expected={'yes' if i['expected'] else 'NO'} "
                     f"flags={i['entry_flags']} | {i['why']}" + (f" | {'; '.join(i['notes'])}" if i.get("notes") else ""))
    lines.append("per symbol (trades, total_R, signals, steps_evaluated):")
    for r in sorted(results, key=lambda r: -len(r.trades)):
        tr = sum(t.r_multiple for t in r.trades)
        lines.append(f"  {r.symbol:<10} trades={len(r.trades):>3} R={tr:+7.2f} signals={r.signals:>3} "
                     f"steps={r.steps} skipped_not_bullish={r.steps_skipped_not_bullish}")
    if skipped:
        lines.append("skipped symbols (fail-closed): " + "; ".join(f"{k}={v}" for k, v in skipped.items()))
    lines += ["WARNINGS:"] + [f"  - {w}" for w in summary["warnings"]]
    lines.append(f"elapsed {time.time() - t0:.0f}s")
    text = "\n".join(lines) + "\n"
    tag = "_".join(x for x in ("experiment_no_daily_gate" if a.experiment_no_daily_gate else "",
                               f"target_{a.target_mode}" if a.target_mode else "",
                               "vetoes" if veto else "", f"offset{a.end_offset_days}" if a.end_offset_days else "") if x) or "latest"
    OUT_TXT = f"backtest_{tag}.txt"
    OUT_JSON = OUT_TXT.replace(".txt", ".json")
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / OUT_TXT).write_text(text, encoding="utf-8")
    (ROOT / "reports" / OUT_JSON).write_text(
        json.dumps({"summary": summary, "postmortem": pm, "trades": [asdict(t) for t in trades], "skipped": skipped}, indent=1, default=str),
        encoding="utf-8",
    )
    if not a.experiment_no_daily_gate and not veto and summary["filled_trades"]:
        mem = PatternMemory.load()
        mem.record_run(f"offset{a.end_offset_days}_days{a.days}", cfg.signals.target_mode, pm["lessons"], pm["categories"],
                       summary["filled_trades"], summary["avg_r"])
        mem.save()
        (ROOT / "reports" / "pattern_memory.txt").write_text(mem.render(), encoding="utf-8")
        text += "\n" + mem.render()
    else:
        text += "\n(pattern memory not updated: experiments and veto runs are not independent evidence)\n"
    (ROOT / "reports" / OUT_TXT).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(run_guarded("run_backtest", main))
