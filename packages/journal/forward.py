"""Forward paper journal (ADR-036). Pure functions: no network and no file I/O (the script does those).

A record is created when a tracked recipe says SIGNAL on the last CLOSED 4H candle. It is settled later with the SAME
function the backtester uses (`simulate_order`: limit/market fill window, stop wins ties, fees, slippage, exit plan), so
a live result and a backtest result mean exactly the same thing. The owner's own decision (taken or skipped, his
price, his mood) is stored next to it, so "the system versus me" can be measured.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from packages.backtest.engine import ExitPlan, fee_r_of, net_r, simulate_order
from packages.market_data.models import Candle

H4 = 14_400_000
WEEK = 7 * 86_400_000

# PRE-REGISTERED (ADR-036): which recipes are tracked, and the verdict rule. Change only with a new ADR, and never
# after a recipe's first settled signal.
TRACKED = ("brk55_trail", "brk20_btc_trail", "sweep_only")
VERDICT_FIRST_LOOK = 100
VERDICT_LAST_LOOK = 200

# ADR-037: the owner's decision is one of these. "absent" = he was not there; the system's R still counts for the
# verdict, but the record is left out of the taken-versus-skipped comparison. A signal with no decision more than
# DECISION_WINDOW_MS after its candle CLOSED becomes "absent" automatically, and its decision is then frozen.
DECISIONS = ("taken", "skipped", "absent")
DECISION_WINDOW_MS = 4 * 3_600_000

# ADR-038: scan re-analyses every closed 4H candle it has not analysed yet (computer asleep or off), at most 7 days
# back, and never before the candle the first live scan analysed (2026-11-14 12:00 UTC open), so the backtest sample
# (anchor 2026-11-14 08:00 UTC) is never re-entered. Candles that fall outside the 7 days are recorded as a gap.
BACKFILL_MAX_MS = 7 * 86_400_000
JOURNAL_START_OPEN_MS = int(datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)


def utc(ms: int | None) -> str:
    return "" if ms is None else datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


def record_id(recipe: str, symbol: str, candle_open_ms: int) -> str:
    return f"{recipe}:{symbol}:{candle_open_ms}"


def reasons_for(dec) -> list[str]:
    out = [k for k, v in dec.checks.items() if v]
    ev = dec.evidence or {}
    if "sweep" in ev:
        s = ev["sweep"]
        out.append(f"swept {s.get('deepest_level_kind', '?')} by {s.get('deepest_penetration_pct', 0):.2f}% and closed back above")
    if "fvg" in ev:
        out.append(f"open FVG {ev['fvg'].get('lower', 0):.6g}-{ev['fvg'].get('upper', 0):.6g}")
    return out


def reasons_against(recipe: str, lab_cards: Mapping, alt_cards: Mapping) -> list[str]:
    """What the history already says against this recipe (shown with every signal, on purpose)."""
    out = []
    c = lab_cards.get(recipe)
    if c:
        out.append(f"backtest main: avg R {c['avg_r']:+.3f}, 95% lower bound {c['ci_lower_r']}, {c['trades']} trades")
    a = alt_cards.get(recipe)
    if a:
        out.append(f"unseen coins (alt): avg R {a['avg_r']:+.3f}, verdict FAIL")
    out.append("no recipe has a proven edge yet (ADR-031); this signal is a measurement, not advice")
    return out


def backfill_plan(open_times: Sequence[int], last_done_open_ms: int | None, now_ms: int,
                  window_4h: int) -> tuple[list[int], tuple[int, int] | None]:
    """ADR-038. open_times: open times of the CLOSED 4H candles fetched for one symbol, ascending.

    Returns the indices to analyse (not analysed yet, closed within the last 7 days, with a full analysis window) and the
    gap (first_open_ms, last_open_ms) of candles that should have been analysed but are now out of reach, or None.
    """
    expected = JOURNAL_START_OPEN_MS if last_done_open_ms is None else max(last_done_open_ms + H4, JOURNAL_START_OPEN_MS)
    floor = now_ms - BACKFILL_MAX_MS
    idx = [i for i, o in enumerate(open_times) if o >= expected and o + H4 >= floor and i + 1 >= window_4h]
    gap = None
    if idx and open_times[idx[0]] > expected:
        gap = (expected, open_times[idx[0]] - H4)
    return idx, gap


def new_record(recipe: str, dec, plan: ExitPlan | None, lab_cards: Mapping, alt_cards: Mapping, scanned_ms: int,
               last_close_ms: int, backfilled: bool = False) -> dict:
    return {
        "id": record_id(recipe, dec.symbol, dec.setup_candle_open_time_ms), "recipe": recipe, "symbol": dec.symbol,
        "candle_open_ms": dec.setup_candle_open_time_ms, "candle": utc(dec.setup_candle_open_time_ms),
        "scanned": utc(scanned_ms), "scan_lag_min": round((scanned_ms - last_close_ms) / 60_000, 1),
        "backfilled": backfilled,
        "entry": dec.entry, "stop": dec.stop, "target": dec.target, "planned_rr": dec.risk_reward,
        "plan": asdict(plan) if plan is not None else None,
        "reasons_for": reasons_for(dec), "reasons_against": reasons_against(recipe, lab_cards, alt_cards),
        "status": "PENDING", "result_r": None, "exit_reason": None, "fill_time": None, "exit_time": None, "exit_price": None,
        "owner": {"decision": None, "price": None, "mood": None, "note": None, "at": None},
    }


def settle(rec: dict, setup: Sequence[Candle], expiry: int, max_hold: int, fee_pct: float, slip_pct: float) -> dict:
    """Re-run the backtest exit rules on candles observed since the signal. Returns an updated copy."""
    if rec["status"] in ("CLOSED", "UNFILLED"):
        return rec
    idx = {c.open_time_ms: i for i, c in enumerate(setup)}
    t = idx.get(rec["candle_open_ms"])
    out = dict(rec)
    if t is None:
        out["status_note"] = "signal candle not in the fetched window (fetch more candles)"
        return out
    plan = ExitPlan(**rec["plan"]) if rec.get("plan") else None
    kind, payload, _ = simulate_order(setup, t, rec["entry"], rec["stop"], rec["target"], expiry, max_hold, fee_pct, slip_pct, plan)
    if kind == "UNFILLED":
        out["status"] = "UNFILLED"
    elif kind == "TRADE":
        if len(payload) == 6:
            fill, ex, px, reason, r, _fee = payload
        else:
            fill, ex, px, reason = payload
            r = net_r(rec["entry"], rec["stop"], px, fee_pct)
        out.update(status="CLOSED", result_r=round(r, 4), exit_reason=reason, exit_price=px,
                   fill_time=utc(setup[fill].open_time_ms), exit_time=utc(setup[ex].open_time_ms))
    else:
        fill = next((k for k in range(t + 1, len(setup)) if setup[k].low <= rec["entry"]), None)
        out["status"] = "OPEN" if fill is not None else "PENDING"
        if fill is not None:
            out["fill_time"] = utc(setup[fill].open_time_ms)
    return out


def candle_close_ms(rec: dict) -> int:
    return rec["candle_open_ms"] + H4


def decision_window_open(rec: dict, now_ms: int) -> bool:
    """True while the owner may still record or change his decision (ADR-037)."""
    return now_ms - candle_close_ms(rec) <= DECISION_WINDOW_MS


def auto_absent(rec: dict, now_ms: int) -> dict:
    """ADR-037: no decision more than 4 hours after the candle closed -> 'absent'. Returns an updated copy or rec itself."""
    if rec["owner"].get("decision") is not None or decision_window_open(rec, now_ms):
        return rec
    out = dict(rec)
    out["owner"] = {"decision": "absent", "price": None, "mood": None, "auto": True, "at": utc(now_ms),
                    "note": "auto: no decision within 4 hours of the candle close"}
    return out


# ADR-041: tamper-evident journal (idea from ai-hedge-fund's hash-chained ledger; our own implementation).
# Each new signal is hashed together with the previous signal's hash, so editing, inserting or deleting any past signal
# breaks every later link. The owner's decision is sealed (hashed) once its 4-hour window has closed. Settlement results
# are not hashed: they are re-computable from public candles. Publishing the chain head (it is printed in
# reports/forward_review.txt, which is committed) anchors the journal in Git history, so a rewritten chain is detectable.
GENESIS = "0" * 64
CHAIN_FIELDS = ("id", "recipe", "symbol", "candle_open_ms", "entry", "stop", "target", "planned_rr", "plan", "scanned")


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def signal_hash(rec: dict, prev_hash: str) -> str:
    return _digest({**{f: rec.get(f) for f in CHAIN_FIELDS}, "prev_hash": prev_hash})


def chain_head(recs: Sequence[dict]) -> str:
    return next((r["hash"] for r in reversed(recs) if r.get("hash")), GENESIS)


def chain_append(recs: list, rec: dict) -> dict:
    """Append a NEW signal record to the journal, linked to the previous one."""
    prev = chain_head(recs)
    rec["prev_hash"] = prev
    rec["hash"] = signal_hash(rec, prev)
    recs.append(rec)
    return rec


def seal_owner(rec: dict, now_ms: int) -> dict:
    """Once the decision window is closed, hash the owner's decision so a later edit is detectable. Returns a copy or rec."""
    if "owner_seal" in rec or rec["owner"].get("decision") is None or decision_window_open(rec, now_ms):
        return rec
    out = dict(rec)
    out["owner_seal"] = _digest({"hash": rec.get("hash"), "owner": rec["owner"]})
    return out


def verify_chain(recs: Sequence[dict]) -> dict:
    """Check every link and every seal. Records written before ADR-041 (no hash) are allowed only at the start."""
    problems, unchained, chained, prev = [], 0, 0, GENESIS
    for i, r in enumerate(recs):
        if "hash" not in r:
            if chained:
                problems.append(f"line {i + 1} {r.get('id')}: unchained record after the chain started (inserted?)")
            unchained += 1
            continue
        chained += 1
        if r.get("prev_hash") != prev:
            problems.append(f"line {i + 1} {r['id']}: link broken (a record before it was edited, removed or inserted)")
        if signal_hash(r, r.get("prev_hash", "")) != r["hash"]:
            problems.append(f"line {i + 1} {r['id']}: signal fields changed after it was recorded")
        if "owner_seal" in r and _digest({"hash": r["hash"], "owner": r["owner"]}) != r["owner_seal"]:
            problems.append(f"line {i + 1} {r['id']}: owner decision changed after it was sealed")
        prev = r["hash"]
    return {"ok": not problems, "chained": chained, "unchained": unchained, "problems": problems, "head": prev}


def owner_r(rec: dict, fee_pct: float) -> float | None:
    """R the owner actually got: his own entry price, the system's stop distance and exit (manual slippage included)."""
    o = rec["owner"]
    if o.get("decision") != "taken" or o.get("price") is None or rec["status"] != "CLOSED":
        return None
    risk = rec["entry"] - rec["stop"]
    px = rec["exit_price"]
    return (px - o["price"]) / risk - fee_pct / 100.0 * (o["price"] + px) / risk


def clustered_ci(rs: Sequence[float], times_ms: Sequence[int], z: float = 1.96):
    n = len(rs)
    if n < 2:
        return None
    m = sum(rs) / n
    groups: dict[int, float] = {}
    for r, t in zip(rs, times_ms):
        groups[t // WEEK] = groups.get(t // WEEK, 0.0) + (r - m)
    G = len(groups)
    se_cl = math.sqrt(G / max(G - 1, 1) * sum(s * s for s in groups.values())) / n
    sd = math.sqrt(sum((r - m) ** 2 for r in rs) / (n - 1))
    se = max(se_cl, sd / math.sqrt(n))
    return m, m - z * se, m + z * se, G


def verdict(rs: Sequence[float], times_ms: Sequence[int]) -> str:
    """PRE-REGISTERED (ADR-036). Judged only at 100 and at 200 settled trades, never in between."""
    n = len(rs)
    if n < VERDICT_FIRST_LOOK:
        return f"COLLECTING ({n}/{VERDICT_FIRST_LOOK})"
    look = rs[:VERDICT_LAST_LOOK] if n >= VERDICT_LAST_LOOK else rs[:VERDICT_FIRST_LOOK]
    tt = times_ms[:len(look)]
    m, lo, hi, _ = clustered_ci(look, tt)
    if hi < 0:
        return f"KILLED at {len(look)}: 95% upper bound {hi:+.3f} < 0"
    if lo > 0:
        return f"PASSED at {len(look)}: 95% lower bound {lo:+.3f} > 0 (earns the tiny-real-money stage, owner decides)"
    if n >= VERDICT_LAST_LOOK:
        return f"KILLED at {VERDICT_LAST_LOOK}: interval [{lo:+.3f}, {hi:+.3f}] still includes 0"
    return f"UNDECIDED at 100: interval [{lo:+.3f}, {hi:+.3f}]; continue to 200"


def review(records: Iterable[dict], fee_pct: float, gaps: Sequence[Mapping] = ()) -> list[str]:
    recs = sorted(records, key=lambda r: r["candle_open_ms"])
    L = []
    if gaps:
        L.append(f"COVERAGE GAPS (ADR-038): {len(gaps)} periods were never scanned (more than 7 days late); "
                 "signals in them are missing from every recipe:")
        L += [f"  {g['symbol']}: candles {utc(g['from_ms'])} .. {utc(g['to_ms'])} UTC" for g in gaps]
    for recipe in sorted({r["recipe"] for r in recs}):
        rr = [r for r in recs if r["recipe"] == recipe]
        closed = [r for r in rr if r["status"] == "CLOSED"]
        rs = [r["result_r"] for r in closed]
        ts = [r["candle_open_ms"] for r in closed]
        taken = [r for r in closed if r["owner"]["decision"] == "taken"]
        skipped = [r for r in closed if r["owner"]["decision"] == "skipped"]
        absent = [r for r in closed if r["owner"]["decision"] == "absent"]
        undecided = [r for r in rr if r["owner"]["decision"] is None]
        ci = clustered_ci(rs, ts)
        late = sum(bool(r.get("backfilled")) for r in rr)
        L.append(f"{recipe}: signals {len(rr)} ({late} found by backfill), closed {len(closed)}, unfilled {sum(r['status'] == 'UNFILLED' for r in rr)}, "
                 f"open/pending {sum(r['status'] in ('OPEN', 'PENDING') for r in rr)}")
        if ci:
            L.append(f"  system avg R {ci[0]:+.3f}, week-clustered 95% [{ci[1]:+.3f}, {ci[2]:+.3f}], {ci[3]} weeks")
        L.append(f"  verdict: {verdict(rs, ts)}")
        if taken or skipped:
            avg = lambda xs: sum(xs) / len(xs) if xs else float('nan')
            own = [x for x in (owner_r(r, fee_pct) for r in taken) if x is not None]
            L.append(f"  you: taken {len(taken)} (system R {avg([r['result_r'] for r in taken]):+.3f}, your R {avg(own):+.3f}), "
                     f"skipped {len(skipped)} (system R {avg([r['result_r'] for r in skipped]):+.3f})")
            L.append("  -> your choices add value only if 'taken' beats 'skipped' over many signals; your R minus system R = execution cost")
        if absent:
            avg_abs = sum(r["result_r"] for r in absent) / len(absent)
            L.append(f"  absent {len(absent)} (system R {avg_abs:+.3f}; counted in the verdict, left out of taken vs skipped)")
        if undecided:
            L.append(f"  {len(undecided)} signals have no decision from you yet (record skipped ones too)")
    return L if recs or gaps else ["no signals yet"]
