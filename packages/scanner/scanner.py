"""Deterministic scanner core.

Ranking rule (scanner-1.0): eligible symbols that pass every filter are ordered by
24h quote volume (descending), ties broken by symbol (ascending). The 24h percentage
change is displayed only; it never affects rank, eligibility, or any signal.

Every symbol receives either a rank or explicit exclusion reasons. Missing, stale,
or invalid market data excludes the symbol (fail closed).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from packages.config.settings import UniverseConfig
from packages.market_data.models import BookTicker, SymbolEvaluation, Ticker24h
from packages.scanner.models import (
    SCANNER_VERSION,
    STATUS_EXCLUDED,
    STATUS_RANKED,
    STATUS_SHORTLISTED,
    ScanEntry,
    ScanSnapshot,
)


def compute_entries(
    inputs: dict[str, Any],
    params: dict[str, Any],
    scanned_at_utc: datetime,
) -> tuple[ScanEntry, ...]:
    """Pure function: same inputs + params + time => identical entries."""
    tickers: dict[str, dict[str, Any]] = inputs["tickers"]
    book: dict[str, dict[str, Any]] = inputs["book"]
    now_ms = scanned_at_utc.timestamp() * 1000.0

    categories: dict[str, str] = params.get("asset_categories", {})
    ranked: list[tuple[str, float, float | None, float | None, str]] = []
    excluded: list[ScanEntry] = []

    for ev in sorted(inputs["evaluations"], key=lambda e: e["symbol"]):
        symbol = ev["symbol"]
        category = categories.get(ev.get("base_asset", ""), "CRYPTO")
        reasons: list[str] = []
        ticker = tickers.get(symbol)
        quote_volume = ticker["quote_volume"] if ticker else None
        change = ticker["price_change_percent"] if ticker else None
        spread_bps: float | None = None

        if not ev["is_eligible"]:
            reasons.extend(ev["exclusion_reasons"])
        else:
            if ticker is None:
                reasons.append("NO_TICKER_DATA")
            else:
                age_seconds = (now_ms - ticker["close_time_ms"]) / 1000.0
                if abs(age_seconds) > params["max_ticker_age_seconds"]:
                    reasons.append("STALE_TICKER_DATA")
                if ticker["quote_volume"] < params["min_quote_volume_24h"]:
                    reasons.append("BELOW_MIN_QUOTE_VOLUME")

            quote = book.get(symbol)
            if quote is None:
                reasons.append("NO_BOOK_TICKER")
            else:
                bid, ask = quote["bid"], quote["ask"]
                if not (bid > 0 and ask >= bid):
                    reasons.append("INVALID_BOOK_TICKER")
                else:
                    mid = (bid + ask) / 2.0
                    spread_bps = (ask - bid) / mid * 10_000.0
                    if spread_bps > params["max_spread_bps"]:
                        reasons.append("SPREAD_TOO_WIDE")

        if reasons:
            excluded.append(
                ScanEntry(symbol, STATUS_EXCLUDED, None, quote_volume, change, spread_bps, tuple(reasons), category)
            )
        else:
            ranked.append((symbol, quote_volume, change, spread_bps, category))  # type: ignore[arg-type]

    ranked.sort(key=lambda r: (-r[1], r[0]))
    entries: list[ScanEntry] = []
    for idx, (symbol, qv, change, spread, category) in enumerate(ranked, start=1):
        status = STATUS_SHORTLISTED if idx <= params["max_candidates"] else STATUS_RANKED
        entries.append(ScanEntry(symbol, status, idx, qv, change, spread, (), category))
    entries.extend(excluded)
    return tuple(entries)


class MarketScanner:
    """Builds a ScanSnapshot from symbol evaluations and public ticker data."""

    def __init__(self, universe: UniverseConfig, quote_asset: str = "USDT") -> None:
        self._universe = universe
        self._quote_asset = quote_asset.strip().upper()

    def params(self) -> dict[str, Any]:
        return {
            "quote_asset": self._quote_asset,
            "max_candidates": self._universe.max_candidates,
            "min_quote_volume_24h": self._universe.min_quote_volume_24h,
            "max_spread_bps": self._universe.max_spread_bps,
            "max_ticker_age_seconds": self._universe.max_ticker_age_seconds,
            "ranking": "quote_volume_desc_then_symbol_asc",
            "asset_categories": {
                asset: name
                for name, assets in sorted(self._universe.asset_categories.items())
                for asset in assets
            },
        }

    def scan(
        self,
        evaluations: Iterable[SymbolEvaluation],
        tickers: Iterable[Ticker24h],
        book_tickers: Iterable[BookTicker],
        scanned_at_utc: datetime | None = None,
    ) -> ScanSnapshot:
        now = scanned_at_utc or datetime.now(timezone.utc)
        all_evals = list(evaluations)
        target = [e for e in all_evals if e.quote_asset == self._quote_asset]
        skipped = len(all_evals) - len(target)

        symbols = {e.symbol for e in target}
        inputs: dict[str, Any] = {
            "evaluations": [
                {
                    "symbol": e.symbol,
                    "base_asset": e.base_asset,
                    "is_eligible": e.is_eligible,
                    "exclusion_reasons": list(e.exclusion_reasons),
                }
                for e in target
            ],
            "tickers": {
                t.symbol: {
                    "last_price": t.last_price,
                    "price_change_percent": t.price_change_percent,
                    "quote_volume": t.quote_volume,
                    "close_time_ms": t.close_time_ms,
                }
                for t in tickers
                if t.symbol in symbols
            },
            "book": {
                b.symbol: {"bid": b.bid_price, "ask": b.ask_price}
                for b in book_tickers
                if b.symbol in symbols
            },
        }
        params = self.params()
        return ScanSnapshot(
            snapshot_id=uuid.uuid4().hex,
            created_at_utc=now,
            scanner_version=SCANNER_VERSION,
            params=params,
            inputs=inputs,
            entries=compute_entries(inputs, params, now),
            non_target_quote_skipped=skipped,
        )

    @staticmethod
    def replay(snapshot: ScanSnapshot) -> tuple[ScanEntry, ...]:
        """Recompute entries from the stored inputs (reproducibility check)."""
        return compute_entries(snapshot.inputs, snapshot.params, snapshot.created_at_utc)
