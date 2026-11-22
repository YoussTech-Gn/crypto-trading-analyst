"""Ping the outside watcher after a cycle (ADR-047). Called by scripts/journal_cycle.py with the scan result.

  python scripts/heartbeat.py ok|fail
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.notify.channels import load_env  # noqa: E402
from packages.notify.heartbeat import send_heartbeat  # noqa: E402


def main(argv: list[str]) -> int:
    scan_ok = len(argv) > 1 and argv[1] == "ok"
    sent, info = send_heartbeat(load_env(ROOT).get("NOTIFY_HEARTBEAT_URL"), scan_ok)
    print(f"heartbeat: {'sent' if sent else 'not sent'} - {info}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
