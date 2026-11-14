"""ONE command that does the whole unattended research pass and writes reports/MORNING_REPORT.txt.

  python scripts/overnight.py                 (needs internet for stage 0 only)
  python scripts/overnight.py --resume        (same anchor date, skips finished stages, safe to rerun after a crash)
  python scripts/overnight.py --skip-download (use the existing cache, no network at all)

Stages (each one is isolated: a failure writes reports/failure_overnight_<stage>.txt and the run goes on):
  0 cache    download all closed candles (1d, 4h) of every symbol of both baskets once, into data/cache
  1 lab      run every recipe on the main basket (offline, from the cache) -> reports/lab_main.*
  2 freeze   apply the PRE-REGISTERED freeze rule (packages/strategies/freeze.py) -> knowledge/frozen_candidates.json
  3 alt      run ONLY the frozen recipes on the alt basket, once (ADR-026) -> reports/lab_alt.*, knowledge/alt_gate.json
  4 report   reports/MORNING_REPORT.txt
Public data only. No orders. Paper only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.backtest.cache import CandleCache  # noqa: E402
from packages.backtest.data import fetch_history  # noqa: E402
from packages.config.settings import load_config  # noqa: E402
from packages.market_data.client import BinancePublicClient  # noqa: E402
from packages.reporting import write_failure_report  # noqa: E402
from packages.strategies import Goal, build_recipes, score_recipe  # noqa: E402
from packages.strategies.freeze import (ALT_MAX_NEGATIVE_WINDOWS, ALT_MIN_TRADES, ALT_PASS_AVG_R, ALT_PASS_PF, FREEZE_COUNT,  # noqa: E402
                                        FREEZE_MAX_PER_FAMILY, FREEZE_MIN_TRADES, alt_verdict, overall_verdict, select_frozen)
from packages.strategies.portfolio import combine, overlap_report, trades_from_json  # noqa: E402
from scripts.run_lab import BASKETS, FIRST_CLEAN_DATA_MS  # noqa: E402

REPORTS, KNOW, CACHE = ROOT / "reports", ROOT / "knowledge", ROOT / "data" / "cache"
STATUS = KNOW / "overnight_status.json"
ANCHOR = KNOW / "overnight_as_of.json"
GATE = KNOW / "alt_gate.json"
FROZEN = KNOW / "frozen_candidates.json"
H4_MS = 4 * 3_600_000


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log(msg: str) -> None:
    line = f"[{now_utc()}] {msg}"
    print(line, flush=True)
    REPORTS.mkdir(exist_ok=True)
    with open(REPORTS / "overnight.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_json(p: Path, default=None):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def set_status(stage: str, state: str, note: str = "") -> None:
    st = load_json(STATUS, {})
    st[stage] = {"state": state, "note": note, "at": now_utc()}
    KNOW.mkdir(exist_ok=True)
    STATUS.write_text(json.dumps(st, indent=1), encoding="utf-8")


def guarded(stage: str, fn) -> bool:
    set_status(stage, "RUNNING")
    t0 = time.time()
    try:
        note = fn() or ""
        set_status(stage, "DONE", f"{note} ({time.time() - t0:.0f}s)".strip())
        log(f"stage {stage}: DONE {note}")
        return True
    except BaseException as exc:  # noqa: BLE001 - one stage must never stop the others
        if isinstance(exc, KeyboardInterrupt):
            set_status(stage, "INTERRUPTED")
            raise
        p = write_failure_report(f"overnight_{stage}", exc, context=f"overnight stage {stage}")
        set_status(stage, "FAILED", f"{type(exc).__name__}: {str(exc)[:160]} (see {p.name})")
        log(f"stage {stage}: FAILED {type(exc).__name__}: {str(exc)[:160]}")
        return False


# ---------------------------------------------------------------------------------------------------- stage 0
def stage_cache(as_of_ms: int, symbols: list[str]) -> str:
    cfg = load_config()
    cache = CandleCache(CACHE)
    fetcher = cache.history(fetch_history)
    failed: list[str] = []
    with BinancePublicClient(cfg.exchange) as client:
        for i, sym in enumerate(symbols, 1):
            for tf in ("1d", "4h"):
                for attempt in (1, 2, 3):
                    try:
                        fetcher(client, sym, tf, FIRST_CLEAN_DATA_MS, as_of_ms)
                        break
                    except Exception as exc:  # noqa: BLE001
                        if attempt == 3:
                            failed.append(f"{sym}/{tf}: {str(exc)[:80]}")
                        else:
                            time.sleep(5 * attempt)
            if i % 5 == 0 or i == len(symbols):
                log(f"  cache {i}/{len(symbols)} symbols")
    if failed:
        raise RuntimeError(f"network error requesting {len(failed)} series: " + "; ".join(failed[:6]))
    return f"{len(symbols)} symbols cached"


# ---------------------------------------------------------------------------------------------------- stage 1/3
def run_lab(args: list[str], logname: str) -> None:
    cmd = [sys.executable, str(ROOT / "scripts" / "run_lab.py"), "--offline", *args]
    with open(REPORTS / logname, "w", encoding="utf-8") as f:
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT)).returncode
    if rc != 0:
        tail = "\n".join((REPORTS / logname).read_text(encoding="utf-8", errors="replace").splitlines()[-8:])
        raise RuntimeError(f"run_lab exited with code {rc}: {tail}")


def stage_lab(as_of_ms: int, workers: int, force: bool) -> str:
    cur = load_json(REPORTS / "lab_main.json")
    if cur and not force and cur.get("meta", {}).get("as_of_ms") == as_of_ms:
        return "reused existing lab_main for this anchor"
    if cur and "meta" not in cur and not (REPORTS / "lab_main_m6b.json").exists():  # keep the first (live-data) M6b result
        for ext in ("txt", "json"):
            shutil.copy(REPORTS / f"lab_main.{ext}", REPORTS / f"lab_main_m6b.{ext}")
    run_lab(["--basket", "main", "--as-of", str(as_of_ms), "--tag", "main", "--workers", str(workers)], "overnight_lab_main.log")
    return "main basket done"


def cards_to_trades(js: dict) -> dict:
    return {n: {w: trades_from_json(ts) for w, ts in per.items()} for n, per in js["trades"].items()}


def stage_freeze(as_of_ms: int) -> str:
    js = load_json(REPORTS / "lab_main.json")
    if not js or js.get("meta", {}).get("as_of_ms") != as_of_ms:
        raise RuntimeError("lab_main.json is missing or belongs to another anchor date; stage 1 must finish first")
    if FROZEN.exists() and load_json(FROZEN).get("as_of_ms") == as_of_ms:
        return "already frozen for this anchor (kept)"
    cards = js["cards"]
    chosen = select_frozen(cards)
    per = cards_to_trades(js)
    port = None
    if chosen:
        merged = combine(per, chosen)
        port = score_recipe(merged, Goal(), trials=js["trials"])
        port["overlap"] = overlap_report(per, chosen)
    KNOW.mkdir(exist_ok=True)
    FROZEN.write_text(json.dumps({
        "frozen_at": now_utc(), "as_of_ms": as_of_ms,
        "rule": {"min_trades": FREEZE_MIN_TRADES, "count": FREEZE_COUNT, "max_per_family": FREEZE_MAX_PER_FAMILY,
                 "rank_by": "ci_lower_r (week-clustered, Bonferroni z for all recipes tried)"},
        "recipes": chosen, "main_cards": {n: cards[n] for n in chosen}, "main_portfolio": port,
    }, indent=1, default=str), encoding="utf-8")
    return f"frozen {chosen}" if chosen else "no recipe has >= %d trades; nothing frozen" % FREEZE_MIN_TRADES


def stage_alt(as_of_ms: int, workers: int) -> str:
    gate = load_json(GATE)
    if gate and gate.get("status") == "DONE":
        return "alt gate already used (ADR-026); not run again"
    fz = load_json(FROZEN)
    if not fz or fz.get("as_of_ms") != as_of_ms:
        raise RuntimeError("frozen_candidates.json missing for this anchor; stage 2 must finish first")
    names = fz["recipes"]
    if not names:
        return "nothing frozen, alt gate not spent"
    run_lab(["--basket", "alt", "--as-of", str(as_of_ms), "--tag", "alt", "--recipes", ",".join(names), "--workers", str(workers)],
            "overnight_lab_alt.log")
    js = load_json(REPORTS / "lab_alt.json")
    if not js or js.get("meta", {}).get("as_of_ms") != as_of_ms:
        raise RuntimeError("lab_alt.json was not written")
    per = cards_to_trades(js)
    verdicts = {n: alt_verdict(js["cards"][n], fz["main_cards"][n]) for n in names}
    merged = combine(per, names)
    port = score_recipe(merged, Goal(), trials=js["trials"])
    port_v = alt_verdict(port, (fz.get("main_portfolio") or None))
    GATE.write_text(json.dumps({
        "status": "DONE", "run_at": now_utc(), "as_of_ms": as_of_ms, "frozen": names, "verdicts": verdicts,
        "portfolio_verdict": port_v, "portfolio": port, "alt_cards": {n: js["cards"][n] for n in names},
        "overall": overall_verdict({**verdicts, "portfolio": port_v}),
    }, indent=1, default=str), encoding="utf-8")
    return f"alt verdicts {verdicts}, portfolio {port_v}"


# ---------------------------------------------------------------------------------------------------- stage 4
def fmt_card(n: str, c: dict) -> str:
    pf = None if c.get("profit_factor") is None else round(c["profit_factor"], 2)
    return (f"{n:<22} met={c['criteria_met']}/6 trades={c['trades']:>4} avgR={c['avg_r']:+.3f} ciLow={c['ci_lower_r']} "
            f"PF={pf} DD={c['max_drawdown_r']}R neg_windows={len(c['negative_windows'])}")


def stage_report(as_of_ms: int) -> str:
    st = load_json(STATUS, {})
    L = ["MORNING REPORT  (AI Crypto Trading Analyst - paper only, public data only)",
         f"written {now_utc()}   data anchor {datetime.fromtimestamp(as_of_ms / 1000, timezone.utc):%Y-%m-%d %H:%M UTC}", ""]
    L.append("STAGES")
    for s in ("cache", "lab", "freeze", "alt"):
        v = st.get(s, {"state": "NOT_RUN", "note": ""})
        L.append(f"  {s:<7} {v['state']:<9} {v.get('note', '')}")
    js = load_json(REPORTS / "lab_main.json")
    if js and js.get("meta", {}).get("as_of_ms") == as_of_ms:
        cards = js["cards"]
        order = sorted(cards, key=lambda n: (-cards[n]["criteria_met"], -(cards[n]["ci_lower_r"] if cards[n]["ci_lower_r"] is not None else -1e9)))
        k = js["trials"]
        L += ["", f"1) MAIN BASKET - {len(cards)} recipes, {k} tried so far (confidence bar is stricter with every recipe)",
              "   goal (provisional): avg R >= 0.20, PF >= 1.3, <= 1 negative window, DD <= 20R, >= 100 trades, CI lower bound > 0"]
        for n in order:
            L.append("   " + fmt_card(n, cards[n]))
        meeting = [n for n in order if cards[n]["meets_goal"]]
        L.append(f"   recipes meeting the full goal: {meeting if meeting else 'NONE'}")
        best = order[0]
        L += ["", f"   closest to the goal: {best}", "   missing: " + "; ".join(cards[best]["unmet"]),
              "   why: " + ("; ".join(cards[best]["causes"]) or "no dominant cause detected")]
        fams: dict[str, list] = {}
        from packages.strategies.freeze import family_of
        for n in cards:
            fams.setdefault(family_of(n), []).append(cards[n]["avg_r"])
        L += ["", "   best avg R per family (which source of edge looks most promising):"]
        for fam, xs in sorted(fams.items(), key=lambda kv: -max(kv[1])):
            L.append(f"     {fam:<9} best {max(xs):+.3f}   mean of family {sum(xs) / len(xs):+.3f}   ({len(xs)} recipes)")
    else:
        L += ["", "1) MAIN BASKET: no result for this anchor (stage lab did not finish)."]
    fz = load_json(FROZEN)
    if fz and fz.get("as_of_ms") == as_of_ms:
        L += ["", f"2) FROZEN (pre-registered rule: top {FREEZE_COUNT} by clustered lower bound, >= {FREEZE_MIN_TRADES} trades, "
                  f"max {FREEZE_MAX_PER_FAMILY} per family): {fz['recipes'] or 'none'}"]
        for n in fz["recipes"]:
            L.append("   " + fmt_card(n, fz["main_cards"][n]))
        if fz.get("main_portfolio"):
            L.append("   " + fmt_card("PORTFOLIO(frozen)", fz["main_portfolio"]) + f"   overlap={fz['main_portfolio']['overlap']}")
    gate = load_json(GATE)
    if gate and gate.get("as_of_ms") == as_of_ms:
        L += ["", f"3) ALT GATE (25 symbols the recipes never saw; same dates, same market beta) -> OVERALL: {gate['overall']}",
              f"   rule: PASS needs >= {ALT_MIN_TRADES} trades, avg R >= {ALT_PASS_AVG_R}, PF >= {ALT_PASS_PF}, <= {ALT_MAX_NEGATIVE_WINDOWS} negative window, main avg R > 0"]
        for n in gate["frozen"]:
            L.append(f"   {gate['verdicts'][n]:<12}" + fmt_card(n, gate["alt_cards"][n]))
        L.append(f"   {gate['portfolio_verdict']:<12}" + fmt_card("PORTFOLIO(frozen)", gate["portfolio"]))
        L.append("   PASS is NOT proof of an edge: it only earns forward paper trading. FAIL closes that idea for now.")
    elif gate is None:
        L += ["", "3) ALT GATE: not run."]
    L += ["", "FILES: reports/lab_main.txt (every recipe in detail), reports/lab_alt.txt, knowledge/frozen_candidates.json, knowledge/alt_gate.json,",
          "       reports/overnight.log, reports/failure_overnight_*.txt (only if a stage failed), docs/DECISIONS.md (ADR-028).",
          "NEXT: read this file, then choose between (a) forward paper trading of the PASS/WEAK candidate, (b) a new component family."]
    (REPORTS / "MORNING_REPORT.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    return "MORNING_REPORT.txt written"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true", help="reuse the saved anchor date")
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--force-lab", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    a = ap.parse_args()
    KNOW.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    anc = load_json(ANCHOR)
    if a.resume and anc:
        as_of_ms = anc["as_of_ms"]
    else:
        now = int(time.time() * 1000)
        as_of_ms = now - now % H4_MS
        ANCHOR.write_text(json.dumps({"as_of_ms": as_of_ms, "chosen_at": now_utc()}), encoding="utf-8")
    log(f"overnight start, anchor {as_of_ms} ({datetime.fromtimestamp(as_of_ms / 1000, timezone.utc):%Y-%m-%d %H:%M UTC})")
    symbols = sorted(set(BASKETS["main"].split(",")) | set(BASKETS["alt"].split(",")) | {"BTCUSDT"})
    if not a.skip_download:
        guarded("cache", lambda: stage_cache(as_of_ms, symbols))
    else:
        set_status("cache", "SKIPPED", "--skip-download")
    ok = guarded("lab", lambda: stage_lab(as_of_ms, a.workers, a.force_lab))
    ok = ok and guarded("freeze", lambda: stage_freeze(as_of_ms))
    if ok:
        guarded("alt", lambda: stage_alt(as_of_ms, a.workers))
    guarded("report", lambda: stage_report(as_of_ms))
    print((REPORTS / "MORNING_REPORT.txt").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
