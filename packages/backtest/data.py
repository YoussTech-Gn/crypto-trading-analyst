"""Historical public kline download (paginated, closed candles only)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from packages.market_data.client import BinancePublicClient
from packages.market_data.models import Candle
from packages.market_data.validator import TIMEFRAME_INTERVAL_MS, CandleValidator


def fetch_history(client: BinancePublicClient, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> list[Candle]:
    step = TIMEFRAME_INTERVAL_MS[timeframe]
    out: dict[int, Candle] = {}
    cursor = start_ms
    while cursor < end_ms:
        batch = client.fetch_klines(symbol, timeframe, limit=1000, start_time_ms=cursor, end_time_ms=end_ms)
        if not batch:
            break
        for c in batch:
            out[c.open_time_ms] = c
        nxt = batch[-1].open_time_ms + step
        if len(batch) < 1000 or nxt <= cursor:
            break
        cursor = nxt
    return [out[k] for k in sorted(out)]


def load_validated(client, validator, symbol: str, timeframe: str, start_ms: int, end_ms: int, fetcher=None):
    """Download + validate one series for a backtest window. Returns (closed_candles, tainted_open_times).

    Known source defect: truncated 4h candles (duration shorter than 4h) in 2020-2021. Tolerated ONLY when the duration is the
    sole problem of that candle; their times are returned so the backtester can skip every step near them.
    `fetcher` replaces the downloader (used by the on-disk cache, see packages/backtest/cache.py).
    """
    raw = (fetcher or fetch_history)(client, symbol, timeframe, start_ms, end_ms)
    step = TIMEFRAME_INTERVAL_MS[timeframe]
    tainted: list[int] = []
    if timeframe == "4h":
        fixed = []
        for c in raw:
            issues = CandleValidator._validate_single_candle(c, step)
            if issues and all(i.message.startswith("Unexpected candle duration") for i in issues):
                tainted.append(c.open_time_ms)
                c = replace(c, close_time_ms=c.open_time_ms + step - 1)
            fixed.append(c)
        raw = fixed
    res = validator.validate(symbol, timeframe, raw, reference_time_utc=datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc))
    if not res.analysis_allowed:
        codes = ",".join(sorted({i.code for i in res.issues})) or "INVALID"
        first = next((i.message for i in res.issues if i.code != "STALE_DATA"), res.issues[0].message if res.issues else "")
        raise ValueError(f"{timeframe}:{codes} | first issue: {first}")
    return list(res.closed_candles), tuple(tainted)
