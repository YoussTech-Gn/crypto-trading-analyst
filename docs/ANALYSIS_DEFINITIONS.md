# Analysis Definitions (Milestone 3, analysis-1.0)

All values are provisional engineering defaults in `config/default.yaml` (`analysis:`). They are NOT validated trading edge. Only CLOSED candles are used. Output is analysis, not a signal.

| Concept | Definition |
|---|---|
| Swing high/low | High (low) strictly greater (lower) than the `swing_lookback` (3) candles on each side. Known only after candle `i+N` closes (`confirmed_index`). |
| Labels | HH/LH/EQH, HL/LL/EQL versus the previous swing of the same kind. FIRST if none. |
| BOS | First candle CLOSE beyond a confirmed swing level after confirmation. Wicks do not count. CHoCH not included. |
| EMA | Seed = SMA of first N values, k = 2/(N+1). |
| RSI / ATR | Wilder smoothing, period 14. |
| Relative volume | volume / mean(previous 20 volumes), current candle excluded. |
| Daily bullish | ALL of: enough swings (>=2 each kind), last swing high is HH, last swing low is HL, close > EMA50, EMA50 > EMA200, close >= latest swing low. Missing data = not bullish. Failed conditions are listed. |
| Liquidity levels | Swing lows/highs, equal lows/highs (within 0.1%), previous UTC day low/high. |
| Sell-side sweep | First candle whose low is below the level by >= 0.05%. SWEEP if it closes back above the level, otherwise the level is BROKEN (no sweep). Smaller penetrations are touches. A level is spent after its first sweep or break. |
| Bullish FVG | low(C3) > high(C1). Gap = [high(C1), low(C3)], known at C3 close. Status: UNTOUCHED, ENTERED (low <= upper), FILLED (low <= lower), INVALIDATED (close < lower). |

No-look-ahead guarantee: analysing a prefix of the series returns exactly the confirmed items of the full series (tested).
- Sweeps are grouped per candle (sweep_events); same-price levels merged (PREV_DAY_LOW > EQUAL_LOWS > SWING_LOW).
- PREV_DAY_LOW/HIGH apply only during the UTC day after the reference day (expires_index); older days' levels never carry over.
