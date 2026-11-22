"""Forward paper journal (ADR-036). Public Binance data only. No orders, ever.

  python scripts/forward_journal.py scan            run after each 4H close (00,04,08,12,16,20 UTC): new signals;
                                                    also every closed candle missed since the last scan, up to 7 days
                                                    back (ADR-038); older misses are recorded as coverage gaps
  python scripts/forward_journal.py settle          update open signals with the candles seen since
  python scripts/forward_journal.py list            pending decisions and open signals
  python scripts/forward_journal.py decide ID taken --price 1.234 --mood 4 --note "why"
  python scripts/forward_journal.py decide ID skipped --mood 2 --note "why not"
  python scripts/forward_journal.py decide ID absent                (you were not there; ADR-037)
Decisions are accepted only within 4 hours of the signal candle's close; after that the signal is marked
"absent" automatically by any command and can no longer be changed (ADR-037).
  python scripts/forward_journal.py review          weekly review (also written to reports/forward_review.txt)
  python scripts/forward_journal.py verify          check that no past signal or sealed decision was edited (ADR-041)
Journal: knowledge/forward_journal.jsonl (one JSON object per line).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.analysis import AnalysisEngine  # noqa: E402
from packages.config.settings import load_config  # noqa: E402
from packages.backtest.engine import closed_daily_count  # noqa: E402
from packages.journal.forward import (BACKFILL_MAX_MS, DECISIONS, H4, TRACKED, auto_absent,  # noqa: E402
                                      backfill_plan, chain_append, decision_window_open, new_record, review, seal_owner,
                                      settle, utc, verify_chain)
from packages.market_data.client import BinancePublicClient  # noqa: E402
from packages.market_data.validator import CandleValidator  # noqa: E402
from packages.reporting import run_guarded  # noqa: E402
from packages.strategies import build_recipes  # noqa: E402
from scripts.run_lab import BASKETS  # noqa: E402

JOURNAL = ROOT / "knowledge" / "forward_journal.jsonl"
STATE = ROOT / "knowledge" / "forward_scan_state.json"  # last analysed 4H candle per symbol + coverage gaps (ADR-038)


@contextmanager
def journal_lock():
    """Serialize local file operations across CLI processes (ADR-044). Closing releases the OS lock."""
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(JOURNAL.with_suffix(".lock.sqlite3"), timeout=30)) as lock:
        lock.execute("BEGIN IMMEDIATE")
        yield


def load() -> list[dict]:
    if not JOURNAL.exists():
        return []
    return [json.loads(l) for l in JOURNAL.read_text(encoding="utf-8").splitlines() if l.strip()]


def save(recs: list[dict]) -> None:
    JOURNAL.parent.mkdir(exist_ok=True)
    tmp = JOURNAL.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=True) + "\n" for r in recs), encoding="utf-8")
    tmp.replace(JOURNAL)


def mark_absent(recs: list[dict], now_ms: int) -> int:
    """ADR-037: signals without a decision 4 hours after the candle close become 'absent'. Updates in place."""
    n = 0
    for i, r in enumerate(recs):
        new = auto_absent(r, now_ms)
        if new is not r:
            n += 1
            print(f"  {r['id']}: no decision within 4 hours -> absent")
        sealed = seal_owner(new, now_ms)  # ADR-041: decisions are sealed once their window is closed
        if sealed is not r:
            recs[i] = sealed
            n += 1
    return n


def load_marked() -> list[dict]:
    """Read and persist expired owner decisions while the caller holds journal_lock."""
    recs = load()
    if mark_absent(recs, int(time.time() * 1000)):
        save(recs)
    return recs


def fetch(client, validator, sym: str, tf: str, limit: int):
    res = validator.validate(sym, tf, client.fetch_klines(sym, tf, limit=limit))
    if not res.analysis_allowed:
        raise ValueError(f"{sym} {tf}: " + ",".join(sorted({i.code for i in res.issues})))
    return list(res.closed_candles)


def load_state() -> dict:
    if not STATE.exists():
        return {"last_open_ms": {}, "gaps": []}
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, ensure_ascii=True), encoding="utf-8")
    tmp.replace(STATE)


@journal_lock()
def commit_scan(sym, open_times, candidates, now, window_4h):
    """Recheck the cursor after analysis: another scanner may have committed in the meantime."""
    state = load_state()
    idx, gap = backfill_plan(open_times, state["last_open_ms"].get(sym), now, window_4h)
    if not idx:
        return [], None

    recs = load()
    start = len(recs)
    known = {r["id"] for r in recs}
    for rec in candidates:
        if rec["candle_open_ms"] >= open_times[idx[0]] and rec["id"] not in known:
            chain_append(recs, rec)
            known.add(rec["id"])
    marked = mark_absent(recs, int(time.time() * 1000))
    if len(recs) > start or marked or not JOURNAL.exists():
        save(recs)

    gap_record = None
    if gap:
        gap_record = {"symbol": sym, "from_ms": gap[0], "to_ms": gap[1], "noted": utc(now)}
        state["gaps"].append(gap_record)
    # A crash before the cursor replacement replays the same interval and deduplicates its IDs.
    state["last_open_ms"][sym] = open_times[idx[-1]]
    save_state(state)
    return recs[start:], gap_record


def cmd_scan(cfg) -> int:
    """ADR-038: analyse every closed 4H candle not analysed yet (at most 7 days back), each with the data that was
    closed at that candle's close, exactly as the backtester slices it."""
    lab = json.loads((ROOT / "reports" / "lab_main.json").read_text(encoding="utf-8"))["cards"] if (ROOT / "reports" / "lab_main.json").exists() else {}
    gate = json.loads((ROOT / "knowledge" / "alt_gate.json").read_text(encoding="utf-8")) if (ROOT / "knowledge" / "alt_gate.json").exists() else {}
    alt = gate.get("alt_cards", {})
    recipes = build_recipes(cfg, list(TRACKED))
    engine = AnalysisEngine(cfg.analysis)
    validator = CandleValidator(cfg.timeframes)
    w4, w1 = cfg.backtest.analysis_window_4h, cfg.backtest.analysis_window_1d
    extra_4h = BACKFILL_MAX_MS // H4 + 2
    extra_1d = BACKFILL_MAX_MS // 86_400_000 + 20
    with journal_lock():
        load_marked()
        last_open = load_state()["last_open_ms"]
    now = int(time.time() * 1000)
    added, skipped, analysed, new_gaps = [], [], 0, []
    with BinancePublicClient(cfg.exchange) as client:
        btc_daily = fetch(client, validator, "BTCUSDT", "1d", w1 + extra_1d)
        btc_cache: dict[int, bool] = {}
        for sym in BASKETS["main"].split(","):
            try:
                daily = fetch(client, validator, sym, "1d", w1 + extra_1d)
                setup = fetch(client, validator, sym, "4h", w4 + extra_4h)
            except Exception as exc:  # fail closed per symbol; its state is not advanced, so the next scan backfills it
                skipped.append(f"{sym}: {str(exc)[:60]}")
                continue
            open_times = [c.open_time_ms for c in setup]
            idx, _ = backfill_plan(open_times, last_open.get(sym), now, w4)
            if not idx:
                continue
            candidates = []
            for t in idx:
                close_ms = setup[t].close_time_ms
                k = closed_daily_count(daily, close_ms)
                kb = closed_daily_count(btc_daily, close_ms)
                if kb not in btc_cache:
                    btc_cache[kb] = engine.daily_assessment(btc_daily[max(0, kb - w1): kb])[0].bullish
                a = engine.analyze(sym, daily[max(0, k - w1): k], setup[t + 1 - w4: t + 1]).to_dict()
                a["regime"] = {"btc_daily_bullish": btc_cache[kb]}
                analysed += 1
                for name, rcp in recipes.items():
                    dec = rcp.decide(a)
                    if dec.decision == "SIGNAL":
                        candidates.append(new_record(name, dec, getattr(rcp, "exit_plan", None), lab, alt,
                                                     now, close_ms + 1, backfilled=t != len(setup) - 1))
            committed, gap = commit_scan(sym, open_times, candidates, now, w4)
            added.extend(committed)
            if gap:
                new_gaps.append(gap)
    print(f"scan {utc(now)} UTC: {analysed} candles analysed, {len(added)} new signals "
          f"({sum(r['backfilled'] for r in added)} by backfill), {len(skipped)} symbols skipped (fail-closed)")
    for r in added:
        print(f"\n  ID {r['id']}\n  {r['recipe']} {r['symbol']} candle {r['candle']} UTC (scan lag {r['scan_lag_min']} min)"
              + ("  BACKFILLED" if r["backfilled"] else "") + f"  decision: {r['owner']['decision'] or 'open for you'}")
        print(f"  entry {r['entry']:.6g}  stop {r['stop']:.6g}  target {r['target']:.6g}  planned RR {r['planned_rr']:.2f}"
              + ("  (trailing stop, no fixed target)" if r["plan"] and r["plan"].get("trail_after_r") else ""))
        print("  FOR:     " + "; ".join(r["reasons_for"]))
        print("  AGAINST: " + "; ".join(r["reasons_against"]))
    for s in skipped:
        print("  skipped " + s)
    for g in new_gaps:
        print(f"  GAP {g['symbol']}: candles {utc(g['from_ms'])} .. {utc(g['to_ms'])} UTC were never scanned (over 7 days)")
    return 0


def cmd_settle(cfg) -> int:
    with journal_lock():
        recs = load_marked()
        todo = sorted({r["symbol"] for r in recs if r["status"] in ("PENDING", "OPEN")})
    validator = CandleValidator(cfg.timeframes)
    changed = 0
    with BinancePublicClient(cfg.exchange) as client:
        for sym in todo:
            setup = fetch(client, validator, sym, "4h", 1000)
            with journal_lock():
                recs = load()
                updated = 0
                for i, r in enumerate(recs):
                    if r["symbol"] != sym or r["status"] not in ("PENDING", "OPEN"):
                        continue
                    if setup and r["candle_open_ms"] > setup[-1].open_time_ms:
                        continue  # another scan recorded this signal after our fetch
                    new = settle(r, setup, cfg.signals.expiry_candles, cfg.backtest.max_hold_candles,
                                 cfg.backtest.fee_pct_per_side, cfg.backtest.stop_slippage_pct)
                    if new != r and not (r["status"] == "OPEN" and new["status"] == "PENDING"):
                        recs[i] = new
                        updated += 1
                        if new["status"] in ("CLOSED", "UNFILLED"):
                            print(f"  {new['id']}: {new['status']} {new.get('exit_reason') or ''} R={new.get('result_r')}")
                if updated:
                    save(recs)
                    changed += updated
    print(f"settle: {changed} records updated, {sum(r['status'] in ('PENDING', 'OPEN') for r in recs)} still open")
    return 0


@journal_lock()
def cmd_list(_cfg) -> int:
    for r in load_marked():
        if r["owner"]["decision"] is None or r["status"] in ("PENDING", "OPEN"):
            print(f"{r['id']:<42} {r['status']:<8} decision={r['owner']['decision']}  entry {r['entry']:.6g} stop {r['stop']:.6g}")
    return 0


@journal_lock()
def cmd_decide(_cfg, a) -> int:
    recs = load_marked()
    hit = [i for i, r in enumerate(recs) if r["id"] == a.id]
    if not hit:
        print(f"unknown id {a.id} (see: python scripts/forward_journal.py list)")
        return 1
    if a.decision == "taken" and a.price is None:
        print("taken needs --price (your real entry price)")
        return 1
    r = recs[hit[0]]
    if not decision_window_open(r, int(time.time() * 1000)):
        print(f"{a.id}: more than 4 hours after the candle close; decision is frozen as "
              f"'{r['owner']['decision']}' (ADR-037)")
        return 1
    r["owner"] = {"decision": a.decision, "price": a.price, "mood": a.mood, "note": a.note, "at": utc(int(time.time() * 1000))}
    save(recs)
    print(f"recorded: {a.id} {a.decision}")
    return 0


@journal_lock()
def cmd_review(cfg) -> int:
    recs = load_marked()
    lines = [f"FORWARD JOURNAL REVIEW {utc(int(time.time() * 1000))} UTC (ADR-036; paper only)", ""] + review(recs, cfg.backtest.fee_pct_per_side, load_state()["gaps"])
    chk = verify_chain(recs)
    lines += ["", f"Journal integrity (ADR-041): {'OK' if chk['ok'] else 'BROKEN'}; {chk['chained']} chained signals"
              + (f", {chk['unchained']} recorded before the chain existed" if chk["unchained"] else "")
              + f"; chain head {chk['head']}"]
    lines += [f"  PROBLEM: {p}" for p in chk["problems"]]
    lines += ["", "Rules: verdicts only at 100 and 200 closed signals per recipe. Do not change a rule after a loss."]
    text = "\n".join(lines) + "\n"
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "forward_review.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


@journal_lock()
def cmd_verify(_cfg) -> int:
    chk = verify_chain(load())
    print(f"journal integrity: {'OK' if chk['ok'] else 'BROKEN'}; chained {chk['chained']}, before the chain {chk['unchained']}; "
          f"head {chk['head']}")
    for p in chk["problems"]:
        print("  PROBLEM: " + p)
    return 0 if chk["ok"] else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("scan", "settle", "list", "review", "verify"):
        sub.add_parser(c)
    d = sub.add_parser("decide")
    d.add_argument("id")
    d.add_argument("decision", choices=DECISIONS)
    d.add_argument("--price", type=float)
    d.add_argument("--mood", type=int, choices=range(1, 6))
    d.add_argument("--note", default="")
    a = ap.parse_args()
    cfg = load_config()
    if a.cmd == "decide":
        return cmd_decide(cfg, a)
    return {"scan": cmd_scan, "settle": cmd_settle, "list": cmd_list, "review": cmd_review, "verify": cmd_verify}[a.cmd](cfg)


if __name__ == "__main__":
    sys.exit(run_guarded("forward_journal", main))
