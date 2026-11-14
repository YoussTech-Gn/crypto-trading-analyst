"""One command: scan, then signals. Output is printed AND saved to reports/latest_run.txt."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.reporting import write_failure_report  # noqa: E402


def main() -> int:
    out = [f"run at {datetime.now(timezone.utc).isoformat()}"]
    code = 0
    for script in ("run_scan.py", "run_signals.py"):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], capture_output=True, text=True, cwd=ROOT)
        out.append(f"=== {script} (exit {r.returncode}) ===")
        out.append(r.stdout.rstrip())
        if r.stderr.strip():
            out.append("--- stderr (last 15 lines) ---")
            out.extend(r.stderr.strip().splitlines()[-15:])
        code = code or r.returncode
        if r.returncode:
            write_failure_report(script.replace('.py', ''), r.stderr or r.stdout, context='run_all')
            break
    text = "\n".join(out) + "\n"
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "latest_run.txt").write_text(text, encoding="utf-8")
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
