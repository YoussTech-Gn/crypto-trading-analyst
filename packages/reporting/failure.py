"""Failure classification and guarded script execution (writes reports/failure_<script>.txt)."""

from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]

# (needles, category, expected, cause, advice)  - first match wins, needles are lower-case
_RULES = [
    (("authentication failed", "password authentication", "operationalerror", "could not connect", "connection refused"),
     "DATABASE_CONNECTION", True, "could not connect to the database, or credentials were rejected",
     "Check DATABASE_URL (or use sqlite:///paper.db). No new data was saved."),
    (("binanceapierror", "httperror", "connecterror", "readtimeout", "connecttimeout", "proxyerror", "timeout", "429", "418", "network error requesting", "forbidden"),
     "EXTERNAL_NETWORK", True, "network or Binance did not respond (outage, rate limit, or block)",
     "Retry in a few minutes. The error is unrelated to the analysis logic. Nothing changed."),
    (("insufficient_history", "missing_candles", "stale", "invalid_ohlc", "not valid for analysis", "data_invalid",
     "malformed_candle_data", "duplicate_candles", "out_of_order", "no symbol could be downloaded"),
     "DATA_QUALITY", True, "candle data is not valid for analysis (too short, incomplete, or stale)",
     "This is an intentional fail-closed exclusion: the symbol is skipped, it is not a code bug."),
    (("configvalidationerror", "validationerror", "extra inputs are not permitted", "invalid yaml"),
     "CONFIG_INVALID", True, "config file contains a disallowed value", "Fix config/default.yaml according to the message."),
]


def classify_message(text: str) -> dict:
    low = text.lower()
    for needles, cat, expected, cause, advice in _RULES:
        if any(n in low for n in needles):
            return {"category": cat, "expected": expected, "cause": cause, "advice": advice}
    return {
        "category": "UNEXPECTED_BUG", "expected": False,
        "cause": "unexpected error in the code or in assumptions about the data",
        "advice": "Do not trust any result from this run. Share reports/failure_*.txt to fix the root cause.",
    }


def write_failure_report(script: str, exc: BaseException | str, context: str = "") -> Path:
    if isinstance(exc, BaseException):
        names = " ".join(c.__name__ for c in type(exc).__mro__)
        text = f"{names} {exc}"
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-2500:]
    else:
        text, tb = str(exc), str(exc)[-2500:]
    info = classify_message(text)
    lines = [
        f"FAILURE REPORT  {datetime.now(timezone.utc).isoformat()}  script={script}",
        f"Category: {info['category']}   Expected? {'yes' if info['expected'] else 'NO (unexpected defect)'}",
        f"Cause: {info['cause']}",
        f"What to do: {info['advice']}",
        f"Message: {str(exc)[:300]}",
    ]
    if context:
        lines.append(f"Context: {context}")
    if not info["expected"]:
        lines += ["--- traceback (last lines) ---", tb]
    path = ROOT / "reports" / f"failure_{script}.txt"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:6]), file=sys.stderr)
    print(f"(full failure report: {path})", file=sys.stderr)
    return path


def run_guarded(script: str, fn: Callable[[], int]) -> int:
    try:
        return fn()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("Interrupted by user (expected). Nothing was saved.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - report, then exit non-zero
        write_failure_report(script, exc)
        return 2
