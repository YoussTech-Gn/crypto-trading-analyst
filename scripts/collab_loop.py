"""Automatic discussion loop between Gemini and Claude through docs/COLLAB.md (ADR-035). Runs on the owner's computer.

Each round: Gemini reviews and appends a block, then Claude reads it, acts (pre-registers, codes, tests, runs the
experiment) and appends its block. The loop stops after --rounds, when a block contains the line `LOOP: STOP`
(an item that needs the owner), or when an assistant appended nothing.

Needs both command-line tools installed and logged in once:
  npm install -g @google/gemini-cli      then run `gemini` once to sign in
  npm install -g @anthropic-ai/claude-code   then run `claude` once to sign in
Usage:
  python scripts/collab_loop.py                 (4 rounds)
  python scripts/collab_loop.py --rounds 8
  python scripts/collab_loop.py --dry-run       (print the commands, run nothing)
  python scripts/collab_loop.py --gemini-model gemini-2.5-flash   (use another Gemini model when the default is overloaded)
A turn that fails (for example Gemini's "503 high demand") is retried --retries times, waiting --wait-min minutes between tries.
Log: reports/collab_loop.log
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLAB = ROOT / "docs" / "COLLAB.md"
LOG = ROOT / "reports" / "collab_loop.log"
TURN_TIMEOUT_S = 45 * 60

COMMON = (
    "You work in this repository with another AI assistant. The shared discussion file is docs/COLLAB.md: read its "
    "Protocol and Roles sections first and follow them exactly (append only, English only, cite files for results, "
    "UNVERIFIED for external claims). docs/DECISIONS.md holds every decision; read the latest ADRs. "
    "If something needs the owner's decision, end your block with a line `OPEN: <question>` and then a line `LOOP: STOP`. "
)

GEMINI_PROMPT = COMMON + (
    "You are Gemini, the researcher and reviewer. Find the latest thread in docs/COLLAB.md. Read every file it cites "
    "(reports, code). Then APPEND exactly one block `### Gemini - <YYYY-MM-DD HH:MM UTC>` that: answers every question "
    "addressed to you; tries hard to break Claude's latest result (bugs, leakage, a missing control, an alternative "
    "explanation) with file and line references; and, if a next experiment is justified, writes a hypothesis card with "
    "fixed parameters and a kill rule. Do not edit any other file and do not write code outside docs/COLLAB.md."
)

CLAUDE_PROMPT = COMMON + (
    "You are Claude, the lab runner. Read Gemini's latest block in docs/COLLAB.md. Accept, reject or change each point "
    "with a reason. If an experiment is agreed: record it in docs/DECISIONS.md as a new pre-registered ADR BEFORE running, "
    "implement it with tests, run the test suite, run the experiment (offline, data/cache only, never place orders, never "
    "download unless the ADR says so), append the result to the ADR, and APPEND one block `### Claude - <YYYY-MM-DD HH:MM UTC>` "
    "to docs/COLLAB.md with the numbers, the files, and your questions for Gemini. Never change a pre-registered rule after "
    "seeing a result. No Arabic in any project file."
)


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


GEMINI_MODEL: str | None = None


def command(agent: str) -> list[str]:
    exe = shutil.which(agent)
    if exe is None:
        raise SystemExit(f"'{agent}' was not found on PATH. Install it (see the top of this file) and sign in once.")
    if agent == "gemini":
        return [exe, "--yolo"] + (["--model", GEMINI_MODEL] if GEMINI_MODEL else []) + ["--prompt", GEMINI_PROMPT]
    return [exe, "-p", CLAUDE_PROMPT, "--permission-mode", "acceptEdits",
            "--allowedTools", "Read,Edit,Write,Glob,Grep,Bash(python *),Bash(python3 *),Bash(pytest *)"]


def turn(agent: str, dry: bool) -> bool:
    before = COLLAB.stat().st_size
    cmd = command(agent)
    if dry:
        log(f"DRY {agent}: {cmd[0]} ... ({len(cmd)} args)")
        return True
    log(f"{agent}: turn started")
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=TURN_TIMEOUT_S)
        out = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        log(f"{agent}: TIMEOUT after {TURN_TIMEOUT_S // 60} min")
        return False
    (ROOT / "reports" / f"collab_last_{agent}.txt").write_text(out, encoding="utf-8")
    grew = COLLAB.stat().st_size > before
    overloaded = "503" in out and "high demand" in out
    log(f"{agent}: exit {r.returncode}, {time.time() - t0:.0f}s, appended={'yes' if grew else 'NO'}"
        + (" (server overloaded: 503 high demand)" if overloaded and not grew else ""))
    return grew


def turn_with_retries(agent: str, dry: bool, retries: int, wait_min: float) -> bool:
    for attempt in range(1, retries + 2):
        if turn(agent, dry):
            return True
        if attempt <= retries:
            log(f"{agent}: retry {attempt}/{retries} in {wait_min:g} min")
            time.sleep(wait_min * 60)
    return False


def stopped(since: int) -> bool:
    return "LOOP: STOP" in COLLAB.read_text(encoding="utf-8")[since:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--start", choices=("gemini", "claude"), default="gemini")
    ap.add_argument("--gemini-model", default=None, help="passed to gemini --model")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--wait-min", type=float, default=10.0)
    a = ap.parse_args()
    global GEMINI_MODEL
    GEMINI_MODEL = a.gemini_model
    order = ["gemini", "claude"] if a.start == "gemini" else ["claude", "gemini"]
    start_size = len(COLLAB.read_text(encoding="utf-8"))
    log(f"loop start: {a.rounds} rounds, {order[0]} first")
    for rnd in range(1, a.rounds + 1):
        for agent in order:
            if not turn_with_retries(agent, a.dry_run, a.retries, a.wait_min):
                log(f"stop: {agent} appended nothing (see reports/collab_last_{agent}.txt)")
                return 1
            if stopped(start_size):
                log(f"stop: LOOP: STOP found after {agent}'s turn in round {rnd}; the owner must decide (see docs/COLLAB.md)")
                return 0
        log(f"round {rnd} done")
    log("loop finished: all rounds done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
