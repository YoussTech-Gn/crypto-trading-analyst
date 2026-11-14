"""Rebuild knowledge/pattern_memory.json from the saved reports/backtest_*.json (history already run).

Window and variant are read from the file name:  backtest_target_<mode>[_offset<N>].json , backtest_latest.json.
Experiment and veto files are skipped (not independent evidence). Assumes days=730 (the default used so far).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.backtest.memory import PatternMemory


def main() -> int:
    mem = PatternMemory()
    used, skipped = [], []
    for f in sorted((ROOT / "reports").glob("backtest_*.json")):
        name = f.stem
        if "experiment" in name or "vetoes" in name:
            skipped.append(name)
            continue
        m = re.search(r"offset(\d+)", name)
        offset = int(m.group(1)) if m else 0
        mode = re.search(r"target_(nearest|first_meeting_rr)", name)
        label = mode.group(1) if mode else "nearest"
        d = json.loads(f.read_text(encoding="utf-8"))
        pm, sm = d["postmortem"], d["summary"]
        if not sm.get("filled_trades"):
            skipped.append(name)
            continue
        mem.record_run(f"offset{offset}_days730", label, pm["lessons"], pm["categories"], sm["filled_trades"], sm["avg_r"])
        used.append(name)
    mem.save()
    text = mem.render()
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "pattern_memory.txt").write_text(text, encoding="utf-8")
    print(f"used={used}\nskipped={skipped}\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
