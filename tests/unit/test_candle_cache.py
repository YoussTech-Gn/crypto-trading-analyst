"""Candle cache: serves from disk, downloads only the missing pieces, never stores unfinished candles."""
from __future__ import annotations

from packages.backtest.cache import CandleCache
from packages.market_data.models import Candle

H4 = 4 * 3_600_000


def mk(i):
    t = i * H4
    return Candle("T", "4h", t, t + H4 - 1, 1.0, 2.0, 0.5, 1.5, 10.0, 15.0, 3)


class Downloader:
    def __init__(self):
        self.calls = []

    def __call__(self, client, symbol, timeframe, a, b):
        self.calls.append((a, b))
        return [mk(i) for i in range(a // H4, b // H4 + 1) if mk(i).open_time_ms >= a and mk(i).open_time_ms <= b]


def test_second_identical_request_is_served_from_disk(tmp_path):
    dl = Downloader()
    cache = CandleCache(tmp_path, now_ms=lambda: 1000 * H4)
    f = cache.history(dl)
    first = f(object(), "T", "4h", 10 * H4, 20 * H4)
    assert len(first) == 11 and len(dl.calls) == 1
    second = f(object(), "T", "4h", 12 * H4, 18 * H4)
    assert [c.open_time_ms for c in second] == [i * H4 for i in range(12, 19)] and len(dl.calls) == 1


def test_only_missing_head_and_tail_are_downloaded(tmp_path):
    dl = Downloader()
    cache = CandleCache(tmp_path, now_ms=lambda: 1000 * H4)
    f = cache.history(dl)
    f(object(), "T", "4h", 10 * H4, 20 * H4)
    out = f(object(), "T", "4h", 5 * H4, 30 * H4)
    assert len(out) == 26
    assert dl.calls[1:] == [(5 * H4, 10 * H4 - 1), (20 * H4 + 1, 30 * H4)]


def test_unfinished_candles_are_not_stored_and_coverage_stops_before_now(tmp_path):
    dl = Downloader()
    now = 15 * H4 + 100  # candle 15 is still running at this moment
    cache = CandleCache(tmp_path, now_ms=lambda: now)
    f = cache.history(dl)
    out = f(object(), "T", "4h", 10 * H4, 20 * H4)
    assert out[-1].open_time_ms == 14 * H4
    assert cache.coverage("T", "4h")[1] == now - 1


def test_offline_returns_cached_part_without_a_client(tmp_path):
    dl = Downloader()
    cache = CandleCache(tmp_path, now_ms=lambda: 1000 * H4)
    cache.history(dl)(object(), "T", "4h", 10 * H4, 20 * H4)
    offline = CandleCache(tmp_path).history(None)
    out = offline(None, "T", "4h", 8 * H4, 40 * H4)
    assert [c.open_time_ms for c in out] == [i * H4 for i in range(10, 21)]
    assert offline(None, "T", "4h", 500 * H4, 600 * H4) == []
