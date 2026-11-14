"""The first recipes. Each isolates ONE component so the lab can measure what that component is worth.

  sweep_fvg   : baseline. Trigger = sell-side sweep, entry = midpoint of the FVG that formed after it.
  sweep_only  : same trigger, entry at the current close (no FVG)       -> value of the FVG.
  fvg_only    : recent open FVG with no sweep requirement               -> value of the sweep.
  bos_retest  : break of structure up, entry = retest of the broken level (different idea).
Context (daily bullish), target (first swing high meeting min RR) and stop buffer are shared on purpose.
Provisional constants are marked PROVISIONAL and are lab parameters, not tuned results.

M6b variants (all built on fvg_only, each changes ONE part so the lab can attribute any difference to that part):
  entry  : fvg_entry_upper / fvg_entry_lower          (limit at the near edge / the far edge of the gap, not the midpoint)
  stop   : fvg_stop_half / fvg_stop_2atr / fvg_stop_struct
  exit   : fvg_exit_1r / fvg_exit_1_5r / fvg_exit_be / fvg_exit_partial / fvg_exit_time
           (same setups as fvg_only, which still need a structural target that pays 2R; only the management changes)
  filter : fvg_volume   (requires relative volume >= 1.0; this idea came from looking at earlier windows, so it counts as a
           data-informed trial and needs unseen-data validation before anyone trusts it)
"""

from __future__ import annotations

from packages.backtest.engine import ExitPlan
from packages.signals.generator import SignalGenerator
from packages.strategies.base import OPEN_FVG_STATUSES, Recipe

FVG_ONLY_RECENT_CANDLES = 6      # PROVISIONAL: the FVG must have formed within the last 6 candles
FVG_ONLY_STOP_ATR = 1.0          # PROVISIONAL: stop = FVG lower edge minus 1 ATR (no sweep low exists here)
BOS_RECENT_CANDLES = 6           # PROVISIONAL: the break must be within the last 6 candles
STRUCT_STOP_ATR_BUFFER = 0.25    # PROVISIONAL: structural stop = last swing low before the gap minus this many ATR
STRUCT_STOP_MIN_ATR = 1.0        # PROVISIONAL: but never closer than this many ATR to the entry
MIN_REL_VOLUME = 1.0             # PROVISIONAL: fvg_volume needs the setup candle volume at least average


class BaselineRecipe(Recipe):
    name = "sweep_fvg"
    description = "sweep of a low, then enter at the midpoint of the FVG formed after it (current strategy)"
    components = {"context": "daily_bullish", "trigger": "sell_side_sweep", "entry": "fvg_midpoint", "exit": "first_swing_high_meeting_rr"}

    def __init__(self, cfg, min_rr) -> None:
        super().__init__(cfg, min_rr)
        self.gen = SignalGenerator(cfg, min_rr)

    def decide(self, analysis):
        return self.gen.decide(analysis)


class SweepOnlyRecipe(Recipe):
    name = "sweep_only"
    description = "sweep of a low, enter at the current close (no FVG)"
    components = {"context": "daily_bullish", "trigger": "sell_side_sweep", "entry": "close", "exit": "first_swing_high_meeting_rr"}

    def decide(self, analysis):
        cfg = self.cfg
        last, close, atr, checks, ev = self._prepare(analysis)
        recent = [e for e in analysis["sweep_events"] if e["sweep_index"] >= last - cfg.sweep_window_candles + 1]
        sweep = max(recent, key=lambda e: e["sweep_index"]) if recent else None
        checks["RECENT_SELL_SIDE_SWEEP"] = sweep is not None
        entry = stop = target = rr = None
        if sweep is not None and checks["ATR_AVAILABLE"]:
            ev["sweep"] = sweep
            entry = close
            stop = sweep["sweep_low"] - cfg.stop_atr_buffer * atr
            target, rr = self._risk_block(analysis, checks, ev, entry, stop, close, atr, sweep=sweep)
        return self._finish(analysis, checks, entry, stop, target, rr, ev)


class FvgOnlyRecipe(Recipe):
    """Base for every FVG recipe. The class attributes below are the ONLY things the variants change."""

    name = "fvg_only"
    description = "recent open bullish FVG in a daily uptrend, no sweep required"
    components = {"context": "daily_bullish", "trigger": "recent_open_fvg", "entry": "fvg_midpoint", "stop": "fvg_lower_minus_1atr",
                  "exit": "first_swing_high_meeting_rr"}
    entry_mode = "mid"                    # mid | upper | lower   (position of the limit inside the gap)
    stop_mode = "fvg_atr"                 # fvg_atr | structural
    stop_atr = FVG_ONLY_STOP_ATR          # used by fvg_atr
    min_rel_volume: float | None = None   # optional volume filter
    require_btc_bullish = False           # optional market-regime filter (needs the Backtester's regime series)
    exit_plan: ExitPlan | None = None     # optional exit management (read by the backtester)

    def _entry(self, fvg: dict) -> float:
        if self.entry_mode == "upper":
            return fvg["upper"]
        if self.entry_mode == "lower":
            return fvg["lower"]
        return (fvg["lower"] + fvg["upper"]) / 2.0

    def _stop(self, analysis: dict, checks: dict, fvg: dict, entry: float, atr: float) -> float | None:
        if self.stop_mode == "structural":
            lows = [x for x in analysis["setup_swings"] if x["kind"] == "LOW" and x["index"] < fvg["index"]]
            checks["SWING_LOW_FOR_STOP"] = bool(lows)
            if not lows:
                return None
            stop = max(lows, key=lambda x: x["index"])["price"] - STRUCT_STOP_ATR_BUFFER * atr
            return min(stop, entry - STRUCT_STOP_MIN_ATR * atr)
        return fvg["lower"] - self.stop_atr * atr

    def decide(self, analysis):
        last, close, atr, checks, ev = self._prepare(analysis)
        cands = [g for g in analysis["fair_value_gaps"]
                 if g["status"] in OPEN_FVG_STATUSES and g["index"] >= last - FVG_ONLY_RECENT_CANDLES + 1]
        fvg = max(cands, key=lambda g: g["index"]) if cands else None
        checks["RECENT_OPEN_FVG"] = fvg is not None
        if self.min_rel_volume is not None:
            rv = analysis["indicators"].get("setup_relative_volume")
            checks["RELATIVE_VOLUME_OK"] = rv is not None and rv >= self.min_rel_volume
        if self.require_btc_bullish:
            checks["BTC_REGIME_BULLISH"] = (analysis.get("regime") or {}).get("btc_daily_bullish") is True
        entry = stop = target = rr = None
        if fvg is not None and checks["ATR_AVAILABLE"]:
            ev["fvg"] = {k: fvg[k] for k in ("index", "lower", "upper", "status", "formed_time_ms")}
            entry = self._entry(fvg)
            stop = self._stop(analysis, checks, fvg, entry, atr)
            if stop is not None:
                target, rr = self._risk_block(analysis, checks, ev, entry, stop, close, atr, fvg=fvg)
        return self._finish(analysis, checks, entry, stop, target, rr, ev)


def _variant(name: str, description: str, part: str, change: dict, **attrs):
    """Build a recipe class that differs from fvg_only in exactly one part."""
    comps = {**FvgOnlyRecipe.components, **change}
    return type(name, (FvgOnlyRecipe,), {"name": name, "description": description, "components": comps, **attrs})


FvgEntryUpper = _variant("fvg_entry_upper", "fvg_only, limit at the NEAR edge of the gap (fills more often, shallower)", "entry",
                         {"entry": "fvg_upper_edge"}, entry_mode="upper")
FvgEntryLower = _variant("fvg_entry_lower", "fvg_only, limit at the FAR edge of the gap (fills rarely, deepest)", "entry",
                         {"entry": "fvg_lower_edge"}, entry_mode="lower")
FvgStopHalf = _variant("fvg_stop_half", "fvg_only, stop = gap low minus 0.5 ATR (tighter)", "stop",
                       {"stop": "fvg_lower_minus_0_5atr"}, stop_atr=0.5)
FvgStop2Atr = _variant("fvg_stop_2atr", "fvg_only, stop = gap low minus 2 ATR (wider)", "stop",
                       {"stop": "fvg_lower_minus_2atr"}, stop_atr=2.0)
FvgStopStruct = _variant("fvg_stop_struct", "fvg_only, stop under the last swing low before the gap (at least 1 ATR from entry)", "stop",
                         {"stop": "structural_swing_low"}, stop_mode="structural")
FvgExit1R = _variant("fvg_exit_1r", "fvg_only, fixed target at +1R", "exit",
                     {"exit": "fixed_1r"}, exit_plan=ExitPlan(fixed_target_r=1.0))
FvgExit15R = _variant("fvg_exit_1_5r", "fvg_only, fixed target at +1.5R", "exit",
                      {"exit": "fixed_1_5r"}, exit_plan=ExitPlan(fixed_target_r=1.5))
FvgExitBe = _variant("fvg_exit_be", "fvg_only, stop moves to the entry once +1R is reached", "exit",
                     {"exit": "breakeven_after_1r"}, exit_plan=ExitPlan(breakeven_after_r=1.0))
FvgExitPartial = _variant("fvg_exit_partial", "fvg_only, sell half at +1R, then break-even stop, rest to the structural target", "exit",
                          {"exit": "half_at_1r_then_structure"},
                          exit_plan=ExitPlan(partial_at_r=1.0, partial_fraction=0.5, breakeven_after_partial=True))
FvgExitTime = _variant("fvg_exit_time", "fvg_only, exit at the close after 8 candles if the best excursion is below +0.5R", "exit",
                       {"exit": "time_decay_8_candles"}, exit_plan=ExitPlan(time_exit_bars=8, time_exit_min_mfe_r=0.5))
FvgVolume = _variant("fvg_volume", "fvg_only, only when the setup candle volume is at least average", "filter",
                     {"filter": "relative_volume_ge_1"}, min_rel_volume=MIN_REL_VOLUME)


class BosRetestRecipe(Recipe):
    name = "bos_retest"
    description = "close above a swing high (break of structure), enter on the retest of the broken level"
    components = {"context": "daily_bullish", "trigger": "break_of_structure_up", "entry": "retest_of_broken_level", "exit": "first_swing_high_meeting_rr"}

    def decide(self, analysis):
        cfg = self.cfg
        last, close, atr, checks, ev = self._prepare(analysis)
        breaks = [b for b in analysis["structure_breaks"]
                  if b["direction"] == "UP" and b["break_index"] >= last - BOS_RECENT_CANDLES + 1]
        brk = max(breaks, key=lambda b: b["break_index"]) if breaks else None
        checks["RECENT_BREAK_OF_STRUCTURE"] = brk is not None
        entry = stop = target = rr = None
        if brk is not None and checks["ATR_AVAILABLE"]:
            lows = [s for s in analysis["setup_swings"] if s["kind"] == "LOW" and s["index"] < brk["break_index"]]
            checks["SWING_LOW_FOR_STOP"] = bool(lows)
            if lows:
                ev["break"] = {k: brk[k] for k in ("level", "break_index", "broken_swing_index")}
                entry = brk["level"]
                stop = max(lows, key=lambda s: s["index"])["price"] - cfg.stop_atr_buffer * atr
                target, rr = self._risk_block(analysis, checks, ev, entry, stop, close, atr)
        return self._finish(analysis, checks, entry, stop, target, rr, ev)

BASE_RECIPES = (
    BaselineRecipe, SweepOnlyRecipe, FvgOnlyRecipe, BosRetestRecipe,
    FvgEntryUpper, FvgEntryLower, FvgStopHalf, FvgStop2Atr, FvgStopStruct,
    FvgExit1R, FvgExit15R, FvgExitBe, FvgExitPartial, FvgExitTime, FvgVolume,
)
