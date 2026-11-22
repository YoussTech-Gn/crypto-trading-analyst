"""Send notifications (ADR-045): new paper signals, a morning summary, and a health alert. No orders, ever.

  python scripts/notify.py            send whatever is due (run every hour by journal_cycle.py)
  python scripts/notify.py --test     send one test notification now, to check the channels
Channels: Windows toast (always on Windows); phone via ntfy (set NTFY_TOPIC in .env); Telegram (TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID in .env). NOTIFY_SUMMARY_HOUR in .env (UTC, default 7) sets the morning summary time.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.notify.channels import load_env, send  # noqa: E402
from packages.notify.planner import plan  # noqa: E402
from packages.reporting import run_guarded  # noqa: E402

KNOW = ROOT / "knowledge"
STATE = KNOW / "notify_state.json"


def read_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    env = load_env(ROOT)
    if a.test:
        res = send(env, "Test - crypto analyst", "If you can read this, notifications work. Paper only, not advice.")
        for ch, ok, info in res:
            print(f"  {ch:<9} {'SENT' if ok else 'off'}  {info}")
        return 0 if any(ok for _, ok, _ in res) else 1
    journal = KNOW / "forward_journal.jsonl"
    recs = [json.loads(l) for l in journal.read_text(encoding="utf-8").splitlines() if l.strip()] if journal.exists() else []
    hour = int(env.get("NOTIFY_SUMMARY_HOUR", "7") or 7)
    msgs, new_state = plan(recs, read_json(STATE, {}), read_json(KNOW / "market_view.json", None),
                           read_json(KNOW / "cycle_health.json", {}), int(time.time() * 1000), hour)
    for kind, title, body in msgs:
        res = send(env, title, body, urgent=kind in ("signal", "health"))
        print(f"notify {kind}: {title} -> " + ", ".join(f"{ch} {'ok' if ok else 'off'}" for ch, ok, _ in res))
    KNOW.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(new_state, indent=1), encoding="utf-8")
    tmp.replace(STATE)
    if not msgs:
        print("notify: nothing due")
    return 0


if __name__ == "__main__":
    sys.exit(run_guarded("notify", main))
