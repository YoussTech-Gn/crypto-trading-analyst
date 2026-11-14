"""PRE-REGISTERED freeze rule and alt-gate verdict (ADR-028). Written BEFORE the first run that uses them.

Freeze rule (applied once to the main-basket lab result, no human choice):
  1. keep recipes with at least FREEZE_MIN_TRADES pooled trades;
  2. rank them by the week-clustered lower confidence bound of avg R (`ci_lower_r`, already penalised for the number of
     recipes tried), best first;
  3. take the top FREEZE_COUNT, at most FREEZE_MAX_PER_FAMILY from one family (so the gate is not spent on near-copies).
Alt verdict per frozen recipe (and for their portfolio), on symbols the recipes never saw (same dates, same market beta):
  PASS          >= ALT_MIN_TRADES trades, avg R >= ALT_PASS_AVG_R, profit factor >= ALT_PASS_PF, at most 1 negative window,
                AND avg R on the main basket > 0
  WEAK          >= ALT_MIN_TRADES trades and avg R > 0, but not PASS
  FAIL          >= ALT_MIN_TRADES trades and avg R <= 0
  INCONCLUSIVE  fewer than ALT_MIN_TRADES trades
PASS is NOT proof of an edge (the dates are shared with the training windows); it only earns forward paper trading.
All numbers are PROVISIONAL and fixed here, not tuned after seeing results.
"""

from __future__ import annotations

from typing import Mapping

FREEZE_MIN_TRADES = 100
FREEZE_COUNT = 3
FREEZE_MAX_PER_FAMILY = 2
ALT_MIN_TRADES = 100
ALT_PASS_AVG_R = 0.10
ALT_PASS_PF = 1.15
ALT_MAX_NEGATIVE_WINDOWS = 1


def family_of(name: str) -> str:
    if name.startswith(("fvg", "combo")):
        return "fvg"
    if name.startswith("brk"):
        return "breakout"
    if name.startswith("pullback"):
        return "pullback"
    if name.startswith("rsi"):
        return "rsi"
    return "smc"  # baseline, sweep_*, bos_retest


def select_frozen(cards: Mapping[str, Mapping]) -> list[str]:
    eligible = [n for n, c in cards.items() if c["trades"] >= FREEZE_MIN_TRADES and c.get("ci_lower_r") is not None]
    eligible.sort(key=lambda n: (-cards[n]["ci_lower_r"], -cards[n]["avg_r"], n))
    chosen: list[str] = []
    per_family: dict[str, int] = {}
    for n in eligible:
        fam = family_of(n)
        if per_family.get(fam, 0) >= FREEZE_MAX_PER_FAMILY:
            continue
        chosen.append(n)
        per_family[fam] = per_family.get(fam, 0) + 1
        if len(chosen) == FREEZE_COUNT:
            break
    return chosen


def alt_verdict(alt: Mapping, main: Mapping | None) -> str:
    if alt["trades"] < ALT_MIN_TRADES:
        return "INCONCLUSIVE"
    if alt["avg_r"] <= 0:
        return "FAIL"
    pf = alt.get("profit_factor")
    neg = len(alt.get("negative_windows", []))
    main_ok = main is None or main["avg_r"] > 0
    if alt["avg_r"] >= ALT_PASS_AVG_R and pf is not None and pf >= ALT_PASS_PF and neg <= ALT_MAX_NEGATIVE_WINDOWS and main_ok:
        return "PASS"
    return "WEAK"


_ORDER = ["PASS", "WEAK", "INCONCLUSIVE", "FAIL"]


def overall_verdict(verdicts: Mapping[str, str]) -> str:
    """Best verdict among the frozen candidates (the gate asks: does ANY frozen idea survive unseen symbols?)."""
    if not verdicts:
        return "NOT_RUN"
    return min(verdicts.values(), key=_ORDER.index)
