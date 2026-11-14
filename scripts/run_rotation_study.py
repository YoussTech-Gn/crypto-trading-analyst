"""Hypothesis H1 (ADR-032): daily relative-strength rotation, top 3, weekly, against BTC-EMA50. Offline, cache only.

  python scripts/run_rotation_study.py
Output: reports/rotation_h1.txt and .json. No download, no orders.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.backtest.cache import CandleCache  # noqa: E402
from packages.reporting import run_guarded  # noqa: E402
from packages.strategies.rotation import (DAY_MS, WEEKDAYS, RotationParams, block_bootstrap_mean_ci, cagr,  # noqa: E402
                                          max_drawdown, sharpe, simulate)
from scripts.run_lab import BASKETS  # noqa: E402

START = datetime(2020, 7, 1, tzinfo=timezone.utc)


def day_str(d: int) -> str:
    return datetime.fromtimestamp(d * 86400, timezone.utc).strftime("%Y-%m-%d")


def load(cache: CandleCache, sym: str, last_day: int) -> dict[int, float]:
    candles, _ = cache.load(sym, "1d")
    return {c.open_time_ms // DAY_MS: c.close for c in candles.values() if c.open_time_ms // DAY_MS <= last_day}


def stats(rets):
    return {"weeks": len(rets), "cagr": cagr(rets), "sharpe": sharpe(rets), "max_dd": max_drawdown(rets),
            "mean_week": sum(rets) / len(rets) if rets else 0.0}


def main() -> int:
    anchor = json.loads((ROOT / "knowledge" / "overnight_as_of.json").read_text())["as_of_ms"]
    last_day = anchor // DAY_MS - 1                     # last fully closed daily candle before the anchor
    first_day = int(START.timestamp()) // 86400
    cache = CandleCache(ROOT / "data" / "cache")
    syms = BASKETS["main"].split(",")
    panel = {s: load(cache, s, last_day) for s in syms}
    missing = [s for s, c in panel.items() if not c]
    panel = {s: c for s, c in panel.items() if c}
    btc = panel["BTCUSDT"]
    base, stress = RotationParams(), RotationParams(fee=0.0020)
    out, L = {}, []
    L.append(f"H1 ROTATION STUDY (ADR-032, pre-registered)  {day_str(first_day)} .. {day_str(last_day)}  symbols={len(panel)} missing={missing}")
    L.append(f"params: {base}")
    L.append("Bias: the cache holds only coins still listed in Nov 2026 (survivorship) -> any positive result is an UPPER BOUND.\n")
    L.append(f"{'day':<4} {'H1 CAGR':>8} {'H1 Shp':>7} {'H1 DD':>6} | {'B CAGR':>7} {'B Shp':>6} {'B DD':>6} | "
             f"{'excess/wk':>9} {'95% CI (block bootstrap)':>26} | {'excess 2x cost':>14} {'in mkt':>6} {'turn/wk':>7}")
    verdict_rows = {}
    for wd in range(7):
        h = simulate(panel, btc, first_day, last_day, wd, base, "rotation")
        b = simulate(panel, btc, first_day, last_day, wd, base, "btc_gate")
        hs = simulate(panel, btc, first_day, last_day, wd, stress, "rotation")
        bs = simulate(panel, btc, first_day, last_day, wd, stress, "btc_gate")
        ex = [x - y for x, y in zip(h.returns, b.returns)]
        ex2 = [x - y for x, y in zip(hs.returns, bs.returns)]
        lo, hi = block_bootstrap_mean_ci(ex)
        sh, sb = stats(h.returns), stats(b.returns)
        inm = sum(1 for w in h.weeks if w.weights) / len(h.weeks)
        turn = sum(w.turnover for w in h.weeks) / len(h.weeks)
        m_ex, m_ex2 = sum(ex) / len(ex), sum(ex2) / len(ex2)
        verdict_rows[WEEKDAYS[wd]] = {"h1": sh, "bench": sb, "excess_mean": m_ex, "ci": [lo, hi], "excess_mean_2x": m_ex2,
                                      "in_market": inm, "turnover": turn}
        L.append(f"{WEEKDAYS[wd]:<4} {sh['cagr']:>+8.1%} {sh['sharpe']:>7.2f} {sh['max_dd']:>6.1%} | {sb['cagr']:>+7.1%} "
                 f"{sb['sharpe']:>6.2f} {sb['max_dd']:>6.1%} | {m_ex:>+9.4f} [{lo:>+10.4f}, {hi:>+10.4f}] | "
                 f"{m_ex2:>+14.4f} {inm:>6.0%} {turn:>7.2f}")
        if wd == 0:
            hold = stats(simulate(panel, btc, first_day, last_day, 0, base, "btc_hold").returns)
            by_year: dict[str, list[float]] = {}
            for w, e in zip(h.weeks, ex):
                by_year.setdefault(day_str(w.day)[:4], []).append(e)
            picks: dict[str, int] = {}
            for w in h.weeks:
                for s_ in w.weights:
                    picks[s_] = picks.get(s_, 0) + 1
    mon = verdict_rows["Mon"]
    signs = {r["excess_mean"] > 0 for r in verdict_rows.values()}
    kills = []
    if mon["ci"][0] <= 0:
        kills.append(f"(1) Monday 95% lower bound of weekly excess {mon['ci'][0]:+.4f} <= 0")
    if mon["h1"]["sharpe"] <= mon["bench"]["sharpe"]:
        kills.append(f"(2) H1 Sharpe {mon['h1']['sharpe']:.2f} <= benchmark {mon['bench']['sharpe']:.2f}")
    if len(signs) > 1:
        kills.append("(3) the sign of mean excess return differs across rebalance weekdays")
    if mon["excess_mean_2x"] <= 0:
        kills.append(f"(4) mean excess at doubled costs {mon['excess_mean_2x']:+.4f} <= 0")
    # ---- robustness checks added after seeing the pre-registered pass (ADR-032); they only make the test stricter
    L += ["", "ROBUSTNESS (ADR-032 addendum; Monday, same parameters)"]
    h0 = simulate(panel, btc, first_day, last_day, 0, base, "rotation")
    b0 = simulate(panel, btc, first_day, last_day, 0, base, "btc_gate")
    ex_no21 = [x - y for w, x, y in zip(h0.weeks, h0.returns, b0.returns) if not day_str(w.day).startswith("2021")]
    lo21, hi21 = block_bootstrap_mean_ci(ex_no21)
    r1_ok = lo21 > 0
    L.append(f"  R1 main without 2021: weeks={len(ex_no21)} excess/wk {sum(ex_no21) / len(ex_no21):+.4f} CI [{lo21:+.4f}, {hi21:+.4f}] -> {'ok' if r1_ok else 'FAIL'}")
    if not r1_ok:
        kills.append(f"R1 without 2021 the lower bound {lo21:+.4f} <= 0")
    alt = {s_: c for s_ in BASKETS["alt"].split(",") if (c := load(cache, s_, last_day))}
    for tag, uni in (("R2 alt basket", alt), ("R3 main+alt", {**panel, **alt})):
        h_ = simulate(uni, btc, first_day, last_day, 0, base, "rotation")
        b_ = simulate(uni, btc, first_day, last_day, 0, base, "btc_gate")
        h2 = simulate(uni, btc, first_day, last_day, 0, stress, "rotation")
        b2 = simulate(uni, btc, first_day, last_day, 0, stress, "btc_gate")
        e_ = [x - y for x, y in zip(h_.returns, b_.returns)]
        e2 = [x - y for x, y in zip(h2.returns, b2.returns)]
        lo_, hi_ = block_bootstrap_mean_ci(e_)
        sh_, sb_ = stats(h_.returns), stats(b_.returns)
        yrs: dict[str, list[float]] = {}
        for w, e in zip(h_.weeks, e_):
            yrs.setdefault(day_str(w.day)[:4], []).append(e)
        fails = []
        if lo_ <= 0:
            fails.append(f"lower bound {lo_:+.4f} <= 0")
        if sh_["sharpe"] <= sb_["sharpe"]:
            fails.append(f"Sharpe {sh_['sharpe']:.2f} <= benchmark {sb_['sharpe']:.2f}")
        if sum(e2) / len(e2) <= 0:
            fails.append("excess <= 0 at doubled costs")
        L.append(f"  {tag} ({len(uni)} symbols): H1 CAGR {sh_['cagr']:+.1%} Sharpe {sh_['sharpe']:.2f} DD {sh_['max_dd']:.1%} | bench Sharpe {sb_['sharpe']:.2f} | "
                 f"excess/wk {sum(e_) / len(e_):+.4f} CI [{lo_:+.4f}, {hi_:+.4f}] 2x-cost {sum(e2) / len(e2):+.4f} -> {'ok' if not fails else 'FAIL: ' + '; '.join(fails)}")
        L.append("     by year: " + ", ".join(f"{y} {sum(v) / len(v):+.4f}" for y, v in sorted(yrs.items())))
        if fails:
            kills.append(f"{tag}: " + "; ".join(fails))
    verdict = "REJECTED" if kills else "SURVIVES (provisional, survivorship-biased upper bound)"
    L += ["", f"Context, BTC buy and hold (Mon): CAGR {hold['cagr']:+.1%} Sharpe {hold['sharpe']:.2f} maxDD {hold['max_dd']:.1%}",
          "Monday weekly excess by year: " + ", ".join(f"{y} {sum(v) / len(v):+.4f} ({len(v)}w)" for y, v in sorted(by_year.items())),
          "Most held (Monday, weeks): " + ", ".join(f"{s} {n}" for s, n in sorted(picks.items(), key=lambda x: -x[1])[:10]),
          "", f"VERDICT: {verdict}"] + [f"  KILL {k}" for k in kills]
    text = "\n".join(L) + "\n"
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "rotation_h1.txt").write_text(text, encoding="utf-8")
    (ROOT / "reports" / "rotation_h1.json").write_text(json.dumps({"verdict": verdict, "kills": kills, "rows": verdict_rows,
                                                                   "btc_hold": hold}, indent=1), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(run_guarded("run_rotation_study", main))
