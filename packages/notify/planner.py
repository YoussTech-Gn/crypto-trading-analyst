"""Decide WHAT to notify (ADR-045). Pure function: no network, no files, no clock.

Three kinds of message:
  1. a new journal signal (once per signal id), with the exact command to record the owner's decision;
  2. a morning summary once per day (even when there is no signal, so the owner always sees the system is alive);
  3. a health alert when no scan has succeeded for HEALTH_ALERT_MS (two missed hourly runs; repeated at most every
     HEALTH_REPEAT_MS), and one "back online" message when a scan succeeds again after an alert (ADR-046).
"""

from __future__ import annotations

from datetime import datetime, timezone

HEALTH_ALERT_MS = 110 * 60_000  # two failed hourly runs (ADR-046; was 6 hours)
HEALTH_REPEAT_MS = 6 * 3_600_000
DECISION_WINDOW_MS = 4 * 3_600_000
H4 = 14_400_000


def _utc(ms: int | None) -> str:
    return "never" if not ms else datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def signal_message(rec: dict) -> tuple[str, str]:
    coin = rec["symbol"].replace("USDT", "")
    deadline = _utc(rec["candle_open_ms"] + H4 + DECISION_WINDOW_MS)
    title = f"PAPER SIGNAL {coin} - {rec['recipe']}"
    body = (f"entry {rec['entry']:.6g}  stop {rec['stop']:.6g}  target {rec['target']:.6g}. "
            f"Decide before {deadline}: python scripts/forward_journal.py decide {rec['id']} taken --price P (or skipped). "
            "Paper only, not advice.")
    return title, body


def summary_message(view: dict | None, health: dict, journal: dict) -> tuple[str, str]:
    title = "Morning summary - crypto analyst"
    parts = []
    if view:
        parts.append(f"BTC daily trend {'UP' if view.get('btc_up') else 'DOWN'}; {len(view.get('up', []))}/{view.get('coins', 0)} coins up.")
        parts.append(f"Signals now: {len(view.get('signals', []))}. One step away: "
                     + (", ".join(f"{c['coin']} ({c['rule']})" for c in view.get("close_calls", [])[:4]) or "none") + ".")
    else:
        parts.append("Market view unavailable (no data).")
    parts.append(f"Journal: {journal.get('signals', 0)} signals, {journal.get('open', 0)} open, "
                 f"{journal.get('waiting_decision', 0)} waiting for your decision.")
    parts.append(f"Last good scan: {_utc(health.get('last_scan_ok_ms'))}; failed runs in 24h: {health.get('failures_24h', 0)}.")
    return title, " ".join(parts)


def plan(records: list[dict], state: dict, view: dict | None, health: dict, now_ms: int, summary_hour_utc: int = 7):
    """Return (messages, new_state). messages: list of (kind, title, body)."""
    st = {"notified_ids": list(state.get("notified_ids", [])), "last_summary_day": state.get("last_summary_day", ""),
          "last_health_alert_ms": int(state.get("last_health_alert_ms", 0)), "initialized": state.get("initialized", False)}
    msgs = []
    seen = set(st["notified_ids"])
    for r in records:
        if r["id"] in seen:
            continue
        expired = now_ms > r["candle_open_ms"] + H4 + DECISION_WINDOW_MS
        if not st["initialized"] and expired:  # first run: do not flood with old, already-decided signals
            st["notified_ids"].append(r["id"])
            continue
        msgs.append(("signal",) + signal_message(r))
        st["notified_ids"].append(r["id"])
    st["initialized"] = True
    now = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
    today = now.strftime("%Y-%m-%d")
    if now.hour >= summary_hour_utc and st["last_summary_day"] != today:
        open_ = sum(1 for r in records if r.get("status") in ("PENDING", "OPEN"))
        waiting = sum(1 for r in records if (r.get("owner") or {}).get("decision") is None
                      and now_ms <= r["candle_open_ms"] + H4 + DECISION_WINDOW_MS)
        msgs.append(("summary",) + summary_message(view, health, {"signals": len(records), "open": open_, "waiting_decision": waiting}))
        st["last_summary_day"] = today
    last_ok = health.get("last_scan_ok_ms") or 0
    if st["last_health_alert_ms"] and last_ok > st["last_health_alert_ms"]:
        msgs.append(("health", "Market data is back",
                     f"Last successful scan: {_utc(last_ok)}. Missed candles were backfilled (up to 7 days)."))
        st["last_health_alert_ms"] = 0
    if last_ok and now_ms - last_ok > HEALTH_ALERT_MS and now_ms - st["last_health_alert_ms"] > HEALTH_REPEAT_MS:
        hours = (now_ms - last_ok) / 3_600_000
        msgs.append(("health", "No market data for %.0f hours" % hours,
                     f"Last successful scan: {_utc(last_ok)}. Check the internet connection and that the computer is awake. "
                     "Missed candles are backfilled for up to 7 days."))
        st["last_health_alert_ms"] = now_ms
    return msgs, st
