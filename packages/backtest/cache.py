"""On-disk cache of public candles, so experiments can be repeated exactly and offline.

One file per (symbol, timeframe): data/cache/<SYMBOL>_<tf>.json holding the candles and ONE contiguous covered range.
Only candles that were already CLOSED when they were downloaded are stored (an unfinished candle would be stale).
A request inside the covered range is answered from disk; missing head/tail pieces are downloaded if a client is given,
otherwise (offline) the cached part is returned and the partial coverage is reported by `coverage()`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from packages.market_data.models import Candle

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "data" / "cache"


class CandleCache:
    def __init__(self, root: Path | str = DEFAULT_ROOT, now_ms: Callable[[], int] | None = None) -> None:
        self.root = Path(root)
        self._now = now_ms or (lambda: int(time.time() * 1000))

    # ------------------------------------------------------------------ storage
    def _path(self, symbol: str, timeframe: str) -> Path:
        return self.root / f"{symbol}_{timeframe}.json"

    def load(self, symbol: str, timeframe: str) -> tuple[dict[int, Candle], tuple[int, int] | None]:
        p = self._path(symbol, timeframe)
        if not p.exists():
            return {}, None
        raw = json.loads(p.read_text(encoding="utf-8"))
        candles = {
            row[0]: Candle(symbol, timeframe, row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], int(row[8]))
            for row in raw["candles"]
        }
        cov = tuple(raw["covered"]) if raw.get("covered") else None
        return candles, cov

    def save(self, symbol: str, timeframe: str, candles: dict[int, Candle], covered: tuple[int, int]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        rows = [[c.open_time_ms, c.close_time_ms, c.open, c.high, c.low, c.close, c.volume, c.quote_volume, c.trade_count]
                for _, c in sorted(candles.items())]
        tmp = self._path(symbol, timeframe).with_suffix(".tmp")
        tmp.write_text(json.dumps({"covered": list(covered), "candles": rows}), encoding="utf-8")
        tmp.replace(self._path(symbol, timeframe))

    def coverage(self, symbol: str, timeframe: str) -> tuple[int, int] | None:
        return self.load(symbol, timeframe)[1]

    # ------------------------------------------------------------------ the fetcher
    def history(self, download: Callable[..., list[Candle]] | None):
        """Return a function with the signature of `fetch_history(client, symbol, timeframe, start_ms, end_ms)`.

        `download` is the real `fetch_history` (or None for offline use).
        """

        def fetch(client, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> list[Candle]:
            candles, cov = self.load(symbol, timeframe)
            if download is not None and client is not None:
                now = self._now()
                want_end = min(end_ms, now - 1)
                if cov is None or want_end < cov[0] or start_ms > cov[1] + 1:
                    lo, hi = (start_ms, want_end) if cov is None else (min(start_ms, cov[0]), max(want_end, cov[1]))
                    pieces = [(lo, hi)]
                else:
                    pieces = []
                    if start_ms < cov[0]:
                        pieces.append((start_ms, cov[0] - 1))
                    if want_end > cov[1]:
                        pieces.append((cov[1] + 1, want_end))
                for a, b in pieces:
                    if a >= b:
                        continue
                    for c in download(client, symbol, timeframe, a, b):
                        if c.close_time_ms < now:  # only candles that are already closed
                            candles[c.open_time_ms] = c
                if pieces:
                    new_lo = min([start_ms] + ([cov[0]] if cov else []))
                    new_hi = max([want_end] + ([cov[1]] if cov else []))
                    self.save(symbol, timeframe, candles, (new_lo, new_hi))
            return [c for k, c in sorted(candles.items()) if start_ms <= k <= end_ms]

        return fetch
