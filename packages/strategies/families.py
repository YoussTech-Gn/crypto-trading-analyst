"""Structurally different strategy families (M6c). Each is a pure function of the analysis dict, like every recipe.

  trend breakout : close above the highest high of the previous N candles, trailing stop, no profit target
  EMA pullback   : in an uptrend, price dips to the 4H EMA20 and closes back above it
  RSI dip        : in a daily uptrend, RSI crosses back up through an oversold level; quick fixed target
  regime filter  : the near-edge FVG recipe plus "BTC daily trend is bullish"
  combos         : near-edge FVG entry combined with parts that showed a positive marginal contribution

All constants are PROVISIONAL lab parameters (chosen BEFORE seeing results of these families), not tuned values.
The trend recipes have no profit target: they carry a far cap (50 R) so only the trailing stop, the time limit or the
stop ends a trade, and `planned_rr` of those trades is meaningless.
"""

from __future__ import annotations

from packages.backtest.engine import ExitPlan
from packages.strategies.base import Recipe, make_context
from packages.strategies.recipes import FvgOnlyRecipe

TREND_STOP_ATR = 2.0          # PROVISIONAL: stop = entry - 2 ATR (so 1 R is about 2 ATR)
TREND_HOLD_CANDLES = 120      # PROVISIONAL: 20 days on the 4H chart
TREND_TARGET_CAP_R = 50.0     # a cap that is never reached; the trade ends by trail, stop or time
BREAKOUT_MIN_REL_VOLUME = 1.5 # PROVISIONAL (breakout volume variant)
PULLBACK_MIN_STOP_ATR = 1.0   # PROVISIONAL: structural stop is never closer than this
PULLBACK_LOW_BUFFER_ATR = 0.25
RSI_STOP_ATR = 1.5            # PROVISIONAL
RSI_TARGET_R = 2.0           # PROVISIONAL (the project minimum reward-to-risk)
RSI_HOLD_CANDLES = 12         # PROVISIONAL


def _features(analysis: dict) -> dict:
    return analysis.get("features") or {}


class TrendBreakout(Recipe):
    name = "brk20_trail"
    description = "close above the 20-candle high in a daily uptrend, 2 ATR stop, trailing stop, no profit target"
    components = {"context": "daily_bullish", "trigger": "breakout_20", "entry": "close", "stop": "entry_minus_2atr",
                  "exit": "trailing_1r_after_1r"}
    lookback_key = "prior_high_20"
    min_rel_volume: float | None = None
    require_btc_bullish = False
    exit_plan = ExitPlan(trail_after_r=1.0, trail_distance_r=1.0, max_hold_candles=TREND_HOLD_CANDLES)

    def decide(self, analysis):
        last, close, atr, checks, ev = self._prepare(analysis)
        f = _features(analysis)
        level, ema50 = f.get(self.lookback_key), f.get("setup_ema_50")
        checks["BREAKOUT"] = bool(level) and close is not None and close > level
        checks["ABOVE_EMA50"] = bool(ema50) and close is not None and close > ema50
        if self.min_rel_volume is not None:
            rv = analysis["indicators"].get("setup_relative_volume")
            checks["RELATIVE_VOLUME_OK"] = rv is not None and rv >= self.min_rel_volume
        if self.require_btc_bullish:
            checks["BTC_REGIME_BULLISH"] = (analysis.get("regime") or {}).get("btc_daily_bullish") is True
        entry = stop = target = rr = None
        if checks["ATR_AVAILABLE"]:
            entry = close
            stop = entry - TREND_STOP_ATR * atr
            target, rr = entry + TREND_TARGET_CAP_R * (entry - stop), TREND_TARGET_CAP_R
            checks["STOP_BELOW_ENTRY"] = stop < entry
            ev["context"] = make_context(analysis, entry, stop, atr, rr, None, None, checks["DAILY_TREND_BULLISH"])
        return self._finish(analysis, checks, entry, stop, target, rr, ev)


class TrendBreakout55(TrendBreakout):
    name = "brk55_trail"
    description = "close above the 55-candle high in a daily uptrend, 2 ATR stop, trailing stop"
    components = {**TrendBreakout.components, "trigger": "breakout_55"}
    lookback_key = "prior_high_55"


class TrendBreakoutVolume(TrendBreakout):
    name = "brk20_vol_trail"
    description = "20-candle breakout with relative volume >= 1.5"
    components = {**TrendBreakout.components, "filter": "relative_volume_ge_1_5"}
    min_rel_volume = BREAKOUT_MIN_REL_VOLUME


class TrendBreakoutBtc(TrendBreakout):
    name = "brk20_btc_trail"
    description = "20-candle breakout only when the BTC daily trend is bullish"
    components = {**TrendBreakout.components, "filter": "btc_daily_bullish"}
    require_btc_bullish = True


class EmaPullback(Recipe):
    name = "pullback_ema20"
    description = "uptrend (4H EMA20 > EMA50), the candle dipped to the EMA20 and closed back above it; structural target"
    components = {"context": "daily_bullish", "trigger": "ema20_pullback", "entry": "close", "stop": "recent_low_5",
                  "exit": "first_swing_high_meeting_rr"}
    exit_plan: ExitPlan | None = None
    trailing = False

    def decide(self, analysis):
        last, close, atr, checks, ev = self._prepare(analysis)
        f = _features(analysis)
        e20, e50, lo, op = f.get("setup_ema_20"), f.get("setup_ema_50"), f.get("setup_last_low"), f.get("setup_last_open")
        have = None not in (e20, e50, lo, op) and close is not None
        checks["EMA_UPTREND"] = have and e20 > e50 and close > e50
        checks["TOUCHED_EMA20_AND_RECLAIMED"] = have and lo <= e20 < close and close > op
        entry = stop = target = rr = None
        if checks["ATR_AVAILABLE"] and have and f.get("recent_low_5") is not None:
            entry = close
            stop = min(f["recent_low_5"] - PULLBACK_LOW_BUFFER_ATR * atr, entry - PULLBACK_MIN_STOP_ATR * atr)
            if self.trailing:
                target, rr = entry + TREND_TARGET_CAP_R * (entry - stop), TREND_TARGET_CAP_R
                checks["STOP_BELOW_ENTRY"] = stop < entry
                ev["context"] = make_context(analysis, entry, stop, atr, rr, None, None, checks["DAILY_TREND_BULLISH"])
            else:
                target, rr = self._risk_block(analysis, checks, ev, entry, stop, close, atr)
        return self._finish(analysis, checks, entry, stop, target, rr, ev)


class EmaPullbackTrail(EmaPullback):
    name = "pullback_ema20_trail"
    description = "same pullback trigger, trailing stop instead of a profit target"
    components = {**EmaPullback.components, "exit": "trailing_1r_after_1r"}
    trailing = True
    exit_plan = ExitPlan(trail_after_r=1.0, trail_distance_r=1.0, max_hold_candles=TREND_HOLD_CANDLES)


class RsiDip(Recipe):
    name = "rsi_dip_30"
    description = "daily uptrend, 4H RSI crosses back up through 30 (oversold bounce), 1.5 ATR stop, 2 R target"
    components = {"context": "daily_bullish", "trigger": "rsi_cross_up_30", "entry": "close", "stop": "entry_minus_1_5atr",
                  "exit": "fixed_2r_12_candles"}
    level = 30.0
    exit_plan = ExitPlan(max_hold_candles=RSI_HOLD_CANDLES)

    def decide(self, analysis):
        last, close, atr, checks, ev = self._prepare(analysis)
        rsi_now, rsi_prev = analysis["indicators"].get("setup_rsi"), _features(analysis).get("setup_rsi_prev")
        checks["RSI_CROSSED_UP"] = None not in (rsi_now, rsi_prev) and rsi_prev <= self.level < rsi_now
        entry = stop = target = rr = None
        if checks["ATR_AVAILABLE"]:
            entry = close
            stop = entry - RSI_STOP_ATR * atr
            target, rr = entry + RSI_TARGET_R * (entry - stop), RSI_TARGET_R
            checks["STOP_BELOW_ENTRY"] = stop < entry
            ev["context"] = make_context(analysis, entry, stop, atr, rr, None, None, checks["DAILY_TREND_BULLISH"])
        return self._finish(analysis, checks, entry, stop, target, rr, ev)


class RsiDip35(RsiDip):
    name = "rsi_dip_35"
    description = "same as rsi_dip_30 with the level at 35"
    components = {**RsiDip.components, "trigger": "rsi_cross_up_35"}
    level = 35.0


def _fvg(name: str, description: str, components: dict, **attrs):
    return type(name, (FvgOnlyRecipe,), {"name": name, "description": description,
                                          "components": {**FvgOnlyRecipe.components, **components}, **attrs})


FvgBtc = _fvg("fvg_btc", "fvg_only, only when the BTC daily trend is bullish", {"filter": "btc_daily_bullish"},
              require_btc_bullish=True)
ComboUpper2Atr = _fvg("combo_upper_2atr", "near-edge entry + stop gap low minus 2 ATR",
                      {"entry": "fvg_upper_edge", "stop": "fvg_lower_minus_2atr"}, entry_mode="upper", stop_atr=2.0)
ComboUpperVol = _fvg("combo_upper_vol", "near-edge entry + relative volume >= 1",
                     {"entry": "fvg_upper_edge", "filter": "relative_volume_ge_1"}, entry_mode="upper", min_rel_volume=1.0)
ComboUpper2AtrVol = _fvg("combo_upper_2atr_vol", "near-edge entry + 2 ATR stop + relative volume >= 1",
                         {"entry": "fvg_upper_edge", "stop": "fvg_lower_minus_2atr", "filter": "relative_volume_ge_1"},
                         entry_mode="upper", stop_atr=2.0, min_rel_volume=1.0)
ComboUpperBtc = _fvg("combo_upper_btc", "near-edge entry + BTC daily trend bullish",
                     {"entry": "fvg_upper_edge", "filter": "btc_daily_bullish"}, entry_mode="upper", require_btc_bullish=True)
ComboUpper2AtrBtc = _fvg("combo_upper_2atr_btc", "near-edge entry + 2 ATR stop + BTC daily trend bullish",
                         {"entry": "fvg_upper_edge", "stop": "fvg_lower_minus_2atr", "filter": "btc_daily_bullish"},
                         entry_mode="upper", stop_atr=2.0, require_btc_bullish=True)

FAMILY_RECIPES = (
    TrendBreakout, TrendBreakout55, TrendBreakoutVolume, TrendBreakoutBtc, EmaPullback, EmaPullbackTrail,
    RsiDip, RsiDip35, FvgBtc, ComboUpper2Atr, ComboUpperVol, ComboUpper2AtrVol, ComboUpperBtc, ComboUpper2AtrBtc,
)
