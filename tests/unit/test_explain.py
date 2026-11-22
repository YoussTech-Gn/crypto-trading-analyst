from types import SimpleNamespace

from packages.signals.explain import cell, daily_trend_short, daily_trend_text, waiting_text


def dec(decision, **checks):
    return SimpleNamespace(decision=decision, checks=checks)


def test_daily_trend_in_plain_words():
    assert daily_trend_text({"bullish": True}) == "UP"
    t = daily_trend_text({"bullish": False, "failed_conditions": ["LAST_HIGH_IS_HH", "CLOSE_ABOVE_EMA_FAST"]})
    assert t.startswith("DOWN: ") and "LOWER" in t and "50-day" in t
    assert daily_trend_short({"bullish": False, "failed_conditions": ["LAST_LOW_IS_HL"]}) == "DOWN (lower lows)"


def test_cells_count_missing_conditions_and_say_what_is_awaited():
    assert cell(dec("SIGNAL", A=True)) == "SIGNAL"
    d = dec("NO_TRADE", DAILY_TREND_BULLISH=False, RECENT_SELL_SIDE_SWEEP=False, ATR_AVAILABLE=True)
    assert cell(d) == "2 missing"
    w = waiting_text(d, 1)
    assert w.startswith("waiting for the daily trend to turn up") and "(+1 more)" in w
    assert "unknown check" in waiting_text(dec("NO_TRADE", UNKNOWN_CHECK=False))
