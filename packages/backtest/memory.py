"""Pattern memory: what the backtests taught us, saved across runs so the same mistake is not repeated.

Every backtest records, per entry-time flag (TIGHT_STOP, TINY_FVG, ...), how trades WITH the flag did against trades
WITHOUT it. Evidence is grouped by independent WINDOW (a time period). Re-running the same window replaces, never adds.

Status of a flag (computed from windows only, never from one big pooled run):
  RECURRING_HAZARD : hurt in >= 3 independent windows and never helped. Strong candidate for a veto (needs user approval).
  WATCH            : hurt in >= 2 independent windows and never helped. Shown as an advisory warning on new signals.
  MIXED            : helped in at least one window or inconsistent. No action.
  INSUFFICIENT     : fewer than 2 windows with enough trades on both sides.

Only runs without vetoes and without experiments count as evidence (a veto changes what the flag means).
The memory never changes the strategy by itself: it advises. Turning a hazard into a veto stays a user decision.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.backtest.postmortem import ENTRY_FLAGS

MIN_N_PER_SIDE = 5          # trades needed with AND without the flag in a window
HURT_MARGIN_R = 0.10        # avg R must be worse by at least this to count as "hurt" (or better = "helped")
WATCH_WINDOWS = 2
HAZARD_WINDOWS = 3
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "pattern_memory.json"


def _weighted(entries: list[tuple[int, float]]) -> float:
    n = sum(e[0] for e in entries)
    return sum(e[0] * e[1] for e in entries) / n if n else 0.0


class PatternMemory:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data: dict[str, Any] = data or {"version": 1, "windows": {}}

    # ---- persistence ----
    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "PatternMemory":
        if path.exists():
            return cls(json.loads(path.read_text(encoding="utf-8")))
        return cls()

    def save(self, path: Path = DEFAULT_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, indent=1, sort_keys=True), encoding="utf-8")

    # ---- recording ----
    def record_run(self, window: str, run_label: str, lessons: list[dict], categories: dict[str, int],
                   n_trades: int, avg_r: float | None) -> None:
        """Idempotent per (window, run_label): recording the same run again replaces it."""
        w = self.data["windows"].setdefault(window, {"runs": {}})
        w["runs"][run_label] = {
            "n_trades": n_trades, "avg_r": avg_r, "categories": categories,
            "flags": {ls["flag"]: {"n_with": ls["all"]["n_with"], "avg_r_with": ls["all"]["avg_r_with"],
                                   "n_without": ls["all"]["n_without"], "avg_r_without": ls["all"]["avg_r_without"]}
                      for ls in lessons},
        }

    # ---- analysis ----
    def _window_evidence(self, flag: str) -> dict[str, dict]:
        """Per window: the best run (most trades) that has enough data on both sides."""
        out: dict[str, dict] = {}
        for wname, w in self.data["windows"].items():
            best = None
            for run in w["runs"].values():
                f = run["flags"].get(flag)
                if not f or f["n_with"] < MIN_N_PER_SIDE or f["n_without"] < MIN_N_PER_SIDE:
                    continue
                if best is None or f["n_with"] + f["n_without"] > best["n_with"] + best["n_without"]:
                    best = f
            if best:
                out[wname] = best
        return out

    def assess(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for flag in ENTRY_FLAGS:
            ev = self._window_evidence(flag)
            hurt = [w for w, f in ev.items() if f["avg_r_with"] <= f["avg_r_without"] - HURT_MARGIN_R]
            helped = [w for w, f in ev.items() if f["avg_r_with"] >= f["avg_r_without"] + HURT_MARGIN_R]
            if len(ev) < WATCH_WINDOWS:
                status = "INSUFFICIENT"
            elif helped or len(hurt) < len(ev):
                status = "MIXED"
            elif len(hurt) >= HAZARD_WINDOWS:
                status = "RECURRING_HAZARD"
            else:
                status = "WATCH"
            result[flag] = {
                "status": status, "windows_used": len(ev), "windows_hurt": len(hurt),
                "pooled_avg_r_with": round(_weighted([(f["n_with"], f["avg_r_with"]) for f in ev.values()]), 3),
                "pooled_avg_r_without": round(_weighted([(f["n_without"], f["avg_r_without"]) for f in ev.values()]), 3),
                "n_with": sum(f["n_with"] for f in ev.values()), "n_without": sum(f["n_without"] for f in ev.values()),
            }
        return result

    def loss_modes(self) -> dict[str, int]:
        """How often each outcome category happened across the best run of every window."""
        tot: dict[str, int] = {}
        for w in self.data["windows"].values():
            if not w["runs"]:
                continue
            best = max(w["runs"].values(), key=lambda r: r["n_trades"])
            for k, v in best["categories"].items():
                tot[k] = tot.get(k, 0) + v
        return tot

    # ---- prediction (advisory only) ----
    def advise(self, context: dict) -> dict:
        """Which known weak patterns does a NEW signal carry, and how bad did they historically do?"""
        assessed = self.assess()
        active = []
        for name, (test, desc, _s) in ENTRY_FLAGS.items():
            if test(context or {}):
                a = assessed[name]
                if a["status"] in ("WATCH", "RECURRING_HAZARD"):
                    active.append({"flag": name, "status": a["status"], "description": desc,
                                   "avg_r_with": a["pooled_avg_r_with"], "avg_r_without": a["pooled_avg_r_without"]})
        hazards = sum(1 for a in active if a["status"] == "RECURRING_HAZARD")
        level = "HIGH" if hazards else ("MEDIUM" if len(active) >= 2 else ("LOW" if active else "CLEAN"))
        return {"risk_level": level, "active": active}

    def render(self) -> str:
        lines = ["PATTERN MEMORY (what past backtests taught us; advisory, never auto-tunes the strategy)",
                 f"windows recorded: {sorted(self.data['windows'])}"]
        for flag, a in self.assess().items():
            desc = ENTRY_FLAGS[flag][1]
            lines.append(f"  {flag:<11} {a['status']:<17} windows={a['windows_used']} hurt_in={a['windows_hurt']} "
                         f"pooled avgR with={a['pooled_avg_r_with']:+.2f} (n={a['n_with']}) / without={a['pooled_avg_r_without']:+.2f} "
                         f"(n={a['n_without']})  | {desc}")
        lines.append(f"  outcome categories across windows: {self.loss_modes()}")
        lines.append(f"  promotion rule: RECURRING_HAZARD needs >= {HAZARD_WINDOWS} independent windows, hurt in all of them. "
                     "Becoming a veto still needs the user's approval.")
        return "\n".join(lines) + "\n"
