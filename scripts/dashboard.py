"""Write reports/dashboard.html (ADR-045): system health, market view, signals waiting for a decision, journal, review.
Public data only, no orders. If the live fetch fails, the last saved market view is shown and marked as old.

  python scripts/dashboard.py              live
  python scripts/dashboard.py --offline    market view from data/cache (testing)
Then open reports/dashboard.html in a browser (it refreshes itself every 5 minutes).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.analysis import AnalysisEngine  # noqa: E402
from packages.config.settings import load_config  # noqa: E402
from packages.journal.forward import TRACKED, review, verify_chain  # noqa: E402
from packages.reporting import run_guarded  # noqa: E402
from packages.reporting.dashboard import render  # noqa: E402
from packages.signals.market_view import market_view  # noqa: E402
from packages.strategies import build_recipes  # noqa: E402
from scripts.trader_view import load_series  # noqa: E402

KNOW = ROOT / "knowledge"
VIEW = KNOW / "market_view.json"
HEALTH = KNOW / "cycle_health.json"
JOURNAL = KNOW / "forward_journal.jsonl"
OUT = ROOT / "reports" / "dashboard.html"


def read_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing or half-written file must not break the page
        return default


def read_journal() -> list[dict]:
    if not JOURNAL.exists():
        return []
    return [json.loads(l) for l in JOURNAL.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    now = int(time.time() * 1000)
    view, stale = None, False
    try:
        series, _ = load_series(cfg, a.offline)
        if "BTCUSDT" in series:
            view = market_view(AnalysisEngine(cfg.analysis), build_recipes(cfg, list(TRACKED)), series,
                               cfg.backtest.analysis_window_1d, cfg.backtest.analysis_window_4h)
            view["offline"] = a.offline
            KNOW.mkdir(exist_ok=True)
            VIEW.write_text(json.dumps(view), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - fall back to the last saved view
        print(f"live market view failed: {str(exc)[:120]}")
    if view is None:
        view = read_json(VIEW, None)
        stale = view is not None
    recs = read_journal()
    state = read_json(KNOW / "forward_scan_state.json", {"gaps": []})
    html = render(view, stale or bool(view and view.get("offline")), recs, read_json(HEALTH, {}),
                  review(recs, cfg.backtest.fee_pct_per_side, state.get("gaps", [])), verify_chain(recs), now)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"dashboard written: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(run_guarded("dashboard", main))
