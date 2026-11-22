"""Plain-language explanations of the engine's checks, for the trader view (ADR-042). Pure functions, no I/O.

Every sentence describes what the rule is WAITING FOR, never a recommendation.
"""

from __future__ import annotations

DAILY = {
    "ENOUGH_SWINGS": "not enough daily swing points yet",
    "LAST_HIGH_IS_HH": "the last daily high was LOWER than the one before (no higher high)",
    "LAST_LOW_IS_HL": "the last daily low was LOWER than the one before (no higher low)",
    "NOT_INVALIDATED": "price broke below the last daily higher low",
    "EMA_AVAILABLE": "not enough daily history for the averages",
    "CLOSE_ABOVE_EMA_FAST": "the daily close is BELOW the 50-day average",
    "EMA_FAST_ABOVE_SLOW": "the 50-day average is BELOW the 200-day average",
}

WAITING_FOR = {
    "DAILY_TREND_BULLISH": "the daily trend to turn up",
    "BTC_REGIME_BULLISH": "Bitcoin's daily trend to turn up",
    "ATR_AVAILABLE": "enough recent candles",
    "RECENT_SELL_SIDE_SWEEP": "a false break of a low (a wick below a low that closes back above it)",
    "OPEN_FVG_AFTER_SWEEP": "an open fair value gap after the false break",
    "RECENT_OPEN_FVG": "an open fair value gap",
    "RECENT_BREAK_OF_STRUCTURE": "a break of structure upward",
    "BREAKOUT": "a 4H close above the recent highest high",
    "ABOVE_EMA50": "price back above its 4H 50-candle average",
    "EMA_UPTREND": "the 4H 20 average above the 50 average",
    "TOUCHED_EMA20_AND_RECLAIMED": "a dip to the 4H 20 average that closes back above it",
    "RSI_CROSSED_UP": "RSI to cross back up from oversold",
    "RELATIVE_VOLUME_OK": "more volume than usual",
    "REWARD_TO_RISK_OK": "a target at least 2 times the risk",
    "TARGET_AVAILABLE": "a clear target above",
    "SWING_LOW_FOR_STOP": "a swing low to place the stop under",
    "STOP_BELOW_ENTRY": "a valid stop below the entry",
    "PRICE_ABOVE_STOP": "price to stay above the stop level",
    "PRICE_NEAR_ENTRY": "price to come close to the entry",
}

DAILY_SHORT = {
    "ENOUGH_SWINGS": "too little history",
    "LAST_HIGH_IS_HH": "lower highs",
    "LAST_LOW_IS_HL": "lower lows",
    "NOT_INVALIDATED": "broke a higher low",
    "EMA_AVAILABLE": "too little history",
    "CLOSE_ABOVE_EMA_FAST": "below 50-day avg",
    "EMA_FAST_ABOVE_SLOW": "50-day avg below 200-day",
}

RULE_SHORT = {"brk55_trail": "BREAKOUT55", "brk20_btc_trail": "BREAKOUT20+BTC", "sweep_only": "FALSE-BREAK"}

RULE_NAMES = {
    "brk55_trail": "Breakout 55",
    "brk20_btc_trail": "Breakout 20 + BTC up",
    "sweep_only": "False break of a low",
}


def daily_trend_text(daily_trend: dict) -> str:
    if daily_trend.get("bullish"):
        return "UP"
    reasons = [DAILY.get(c, c.lower()) for c in daily_trend.get("failed_conditions", [])]
    return "DOWN: " + "; ".join(reasons[:2]) if reasons else "DOWN"


def daily_trend_short(daily_trend: dict) -> str:
    if daily_trend.get("bullish"):
        return "UP"
    c = list(daily_trend.get("failed_conditions", []))
    return "DOWN (" + DAILY_SHORT.get(c[0], c[0].lower()) + ")" if c else "DOWN"


def cell(decision) -> str:
    """Table cell: SIGNAL, or how many conditions are still missing."""
    n = len(missing_checks(decision)) if decision.decision != "SIGNAL" else 0
    return "SIGNAL" if n == 0 else f"{n} missing"


def missing_checks(decision) -> list[str]:
    return [k for k, ok in decision.checks.items() if not ok]


def waiting_text(decision, limit: int = 2) -> str:
    if decision.decision == "SIGNAL":
        return "SIGNAL"
    miss = missing_checks(decision)
    words = [WAITING_FOR.get(m, m.lower().replace("_", " ")) for m in miss[:limit]]
    more = f" (+{len(miss) - limit} more)" if len(miss) > limit else ""
    return "waiting for " + " and ".join(words) + more


def breakout_gap_pct(analysis: dict, key: str) -> float | None:
    """How far the close is below the breakout level, in percent (negative = already above)."""
    level = (analysis.get("features") or {}).get(key)
    close = analysis["indicators"].get("setup_last_close")
    if not level or not close:
        return None
    return (level - close) / close * 100.0
