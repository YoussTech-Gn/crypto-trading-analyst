"""Hourly cycle with a watchdog (ADR-045): scan, settle, dashboard, notify. Each step runs in its own process with a hard
time limit, so one frozen network call (as on 2026-11-21 20:05) can never block the following hours. Writes
knowledge/cycle_health.json (last good scan, failures in the last 24 hours) for the dashboard and the health alert.

  python scripts/journal_cycle.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEALTH = ROOT / "knowledge" / "cycle_health.json"
STEPS = (  # (name, arguments, time limit in seconds)
    ("scan", ["scripts/forward_journal.py", "scan"], 900),
    ("settle", ["scripts/forward_journal.py", "settle"], 600),
    ("dashboard", ["scripts/dashboard.py"], 600),
    ("notify", ["scripts/notify.py"], 180),
)
DAY_MS = 86_400_000


def run_step(name: str, args: list[str], limit: int) -> dict:
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, *args], cwd=str(ROOT), capture_output=True, text=True, timeout=limit,
                           encoding="utf-8", errors="replace")
        out, rc, timed_out = (r.stdout or "") + (r.stderr or ""), r.returncode, False
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        rc, timed_out = -1, True
    print(out.rstrip())
    if timed_out:
        print(f"WATCHDOG: step '{name}' killed after {limit} s")
    host = "data-api.binance.vision" if "data-api.binance.vision" in out else None
    return {"rc": rc, "seconds": round(time.time() - t0, 1), "timed_out": timed_out, "host": host}


def main() -> int:
    now = int(time.time() * 1000)
    print(f"cycle {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
    try:
        health = json.loads(HEALTH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        health = {}
    runs = [r for r in health.get("runs", []) if now - r["at"] < DAY_MS]
    steps = {}
    for name, args, limit in STEPS:
        steps[name] = run_step(name, args, limit)
        if name == "scan" and steps[name]["rc"] == 0:
            health["last_scan_ok_ms"] = now
            # written before dashboard/notify so they see this run's result
            HEALTH.parent.mkdir(exist_ok=True)
            HEALTH.write_text(json.dumps({**health, "runs": runs}, indent=1), encoding="utf-8")
    runs.append({"at": now, "ok": all(s["rc"] == 0 for s in steps.values()), "steps": steps})
    health["runs"] = runs
    health["failures_24h"] = sum(1 for r in runs if not r["ok"])
    if steps["scan"].get("host"):
        health["host"] = steps["scan"]["host"]
    tmp = HEALTH.with_suffix(".tmp")
    tmp.write_text(json.dumps(health, indent=1), encoding="utf-8")
    tmp.replace(HEALTH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
