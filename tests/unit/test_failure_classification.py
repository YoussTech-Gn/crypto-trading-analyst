from packages.reporting.failure import classify_message


def test_malformed_candle_data_is_expected_data_quality():
    msg = "No symbol could be downloaded or validated. BTCUSDT: 4h:MALFORMED_CANDLE_DATA | first issue: Unexpected candle duration"
    r = classify_message(msg)
    assert r["category"] == "DATA_QUALITY" and r["expected"] is True


def test_real_bug_stays_unexpected():
    r = classify_message("KeyError 'risk_atr' in analyze_trade")
    assert r["category"] == "UNEXPECTED_BUG" and r["expected"] is False
