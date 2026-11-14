"""Portfolio combiner: merge the trades of several recipes into one strategy, one open position per symbol.

Rules (all deterministic):
  * trades of the chosen recipes are merged per window and sorted by fill time; ties go to the recipe listed first;
  * a trade is dropped when the same symbol already has an open position (its exit time is not before the new fill);
  * the same setup found by two recipes therefore counts once, and a recipe never "stacks" on top of another.
No position-size or concurrency cap is applied: every trade is one unit of risk (R), as everywhere else in the lab.
The result is scored with the same scorecard as a single recipe, so "integrated performance" is measured, not assumed.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Mapping, Sequence

from packages.backtest.engine import Trade

_TRADE_FIELDS = {f.name for f in fields(Trade)}


def trades_from_json(rows: Sequence[Mapping]) -> list[Trade]:
    """Rebuild Trade objects from the lab's JSON report (unknown keys are ignored)."""
    return [Trade(**{k: v for k, v in r.items() if k in _TRADE_FIELDS}) for r in rows]


def combine(per_recipe: Mapping[str, Mapping[str, Sequence[Trade]]], names: Sequence[str]) -> dict[str, list[Trade]]:
    """per_recipe[recipe][window] -> trades. Returns {window: merged trades} for the recipes in `names`."""
    windows = sorted({w for n in names for w in per_recipe.get(n, {})})
    out: dict[str, list[Trade]] = {}
    for w in windows:
        pool = [(t.fill_time_ms, rank, t) for rank, n in enumerate(names) for t in per_recipe.get(n, {}).get(w, ())]
        pool.sort(key=lambda x: (x[0], x[1]))
        free_after: dict[str, int] = {}
        kept: list[Trade] = []
        for fill_ms, _, t in pool:
            if free_after.get(t.symbol, -1) >= fill_ms:
                continue  # that symbol is still in a position
            kept.append(t)
            free_after[t.symbol] = t.exit_time_ms
        out[w] = kept
    return out


def overlap_report(per_recipe: Mapping[str, Mapping[str, Sequence[Trade]]], names: Sequence[str]) -> dict:
    """How much do the chosen recipes trade the same setups? (shared signal times / all signal times)"""
    keys = {n: {(t.symbol, t.signal_time_ms) for ts in per_recipe.get(n, {}).values() for t in ts} for n in names}
    union = set().union(*keys.values()) if keys else set()
    return {"setups_union": len(union), "setups_per_recipe": {n: len(k) for n, k in keys.items()},
            "setups_in_more_than_one": sum(1 for s in union if sum(s in k for k in keys.values()) > 1)}
