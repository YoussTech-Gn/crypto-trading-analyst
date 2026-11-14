"""Persistence repository for Milestone 1 market data, symbols, and validation runs.

Supports both PostgreSQL (`postgresql://`) and SQLite (`sqlite:///`) using standard
SQL `ON CONFLICT (...) DO UPDATE` upserts and enforces that only validated, closed
candles are persisted.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Sequence

from database.session import DatabaseConnection
from packages.market_data.models import (
    Candle,
    CandleValidationIssue,
    CandleValidationResult,
    DataFreshnessStatus,
    SymbolEvaluation,
)


class MarketDataRepository:
    """Repository for symbols, validated closed candles, and validation audit records."""

    def __init__(self, conn: DatabaseConnection) -> None:
        self._conn = conn

    def upsert_symbol_evaluations(
        self,
        evaluations: Sequence[SymbolEvaluation],
    ) -> int:
        """Idempotently persist symbol evaluations and their exclusion reasons."""
        if not evaluations:
            return 0

        sql = """
        INSERT INTO symbols (
            symbol,
            base_asset,
            quote_asset,
            exchange_status,
            is_spot_trading_allowed,
            is_eligible,
            exclusion_reasons_json,
            evaluated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (symbol) DO UPDATE SET
            base_asset = excluded.base_asset,
            quote_asset = excluded.quote_asset,
            exchange_status = excluded.exchange_status,
            is_spot_trading_allowed = excluded.is_spot_trading_allowed,
            is_eligible = excluded.is_eligible,
            exclusion_reasons_json = excluded.exclusion_reasons_json,
            evaluated_at_utc = excluded.evaluated_at_utc
        """
        params = [
            (
                ev.symbol,
                ev.base_asset,
                ev.quote_asset,
                ev.exchange_status,
                1 if ev.is_spot_trading_allowed else 0,
                1 if ev.is_eligible else 0,
                json.dumps(list(ev.exclusion_reasons)),
                ev.evaluated_at_utc.isoformat(),
            )
            for ev in evaluations
        ]
        self._conn.executemany(sql, params)
        self._conn.commit()
        return len(params)

    def list_symbols(self, eligible_only: bool = False) -> list[SymbolEvaluation]:
        """Retrieve persisted symbol evaluations."""
        if eligible_only:
            sql = """
            SELECT symbol, base_asset, quote_asset, exchange_status,
                   is_spot_trading_allowed, is_eligible, exclusion_reasons_json, evaluated_at_utc
            FROM symbols
            WHERE is_eligible = 1
            ORDER BY symbol ASC
            """
        else:
            sql = """
            SELECT symbol, base_asset, quote_asset, exchange_status,
                   is_spot_trading_allowed, is_eligible, exclusion_reasons_json, evaluated_at_utc
            FROM symbols
            ORDER BY symbol ASC
            """
        rows = self._conn.fetchall_dicts(sql)
        results: list[SymbolEvaluation] = []
        for row in rows:
            reasons = tuple(json.loads(row["exclusion_reasons_json"] or "[]"))
            results.append(
                SymbolEvaluation(
                    symbol=row["symbol"],
                    base_asset=row["base_asset"],
                    quote_asset=row["quote_asset"],
                    exchange_status=row["exchange_status"],
                    is_spot_trading_allowed=bool(row["is_spot_trading_allowed"]),
                    is_eligible=bool(row["is_eligible"]),
                    exclusion_reasons=reasons,
                    evaluated_at_utc=datetime.fromisoformat(row["evaluated_at_utc"]),
                )
            )
        return results

    def upsert_closed_candles(
        self,
        candles: Sequence[Candle],
        ingested_at_utc: datetime | None = None,
    ) -> int:
        """Idempotently persist closed candles for a registered symbol."""
        if not candles:
            return 0

        now_iso = (ingested_at_utc or datetime.now(timezone.utc)).isoformat()
        sql = """
        INSERT INTO candles (
            symbol,
            timeframe,
            open_time_ms,
            close_time_ms,
            open,
            high,
            low,
            close,
            volume,
            quote_volume,
            trade_count,
            ingested_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (symbol, timeframe, open_time_ms) DO UPDATE SET
            close_time_ms = excluded.close_time_ms,
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume,
            quote_volume = excluded.quote_volume,
            trade_count = excluded.trade_count,
            ingested_at_utc = excluded.ingested_at_utc
        """
        params = [
            (
                c.symbol,
                c.timeframe,
                c.open_time_ms,
                c.close_time_ms,
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                c.quote_volume,
                c.trade_count,
                now_iso,
            )
            for c in candles
        ]
        self._conn.executemany(sql, params)
        self._conn.commit()
        return len(params)

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int | None = None,
    ) -> list[Candle]:
        """Retrieve stored candles ordered chronologically by `open_time_ms ASC`."""
        clean_symbol = symbol.strip().upper()
        clean_tf = timeframe.strip().lower()

        if limit is not None:
            sql = """
            SELECT symbol, timeframe, open_time_ms, close_time_ms,
                   open, high, low, close, volume, quote_volume, trade_count
            FROM (
                SELECT symbol, timeframe, open_time_ms, close_time_ms,
                       open, high, low, close, volume, quote_volume, trade_count
                FROM candles
                WHERE symbol = ? AND timeframe = ?
                ORDER BY open_time_ms DESC
                LIMIT ?
            ) sub
            ORDER BY open_time_ms ASC
            """
            rows = self._conn.fetchall_dicts(sql, (clean_symbol, clean_tf, int(limit)))
        else:
            sql = """
            SELECT symbol, timeframe, open_time_ms, close_time_ms,
                   open, high, low, close, volume, quote_volume, trade_count
            FROM candles
            WHERE symbol = ? AND timeframe = ?
            ORDER BY open_time_ms ASC
            """
            rows = self._conn.fetchall_dicts(sql, (clean_symbol, clean_tf))

        return [
            Candle(
                symbol=r["symbol"],
                timeframe=r["timeframe"],
                open_time_ms=int(r["open_time_ms"]),
                close_time_ms=int(r["close_time_ms"]),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=float(r["volume"]),
                quote_volume=float(r["quote_volume"]),
                trade_count=int(r["trade_count"]),
            )
            for r in rows
        ]

    def record_validation_run(
        self,
        result: CandleValidationResult,
        run_id: str | None = None,
    ) -> str:
        """Persist a CandleValidationResult audit record and return its `run_id`."""
        resolved_run_id = run_id or str(uuid.uuid4())
        issues_payload = [
            {
                "code": issue.code,
                "message": issue.message,
                "candle_open_time_ms": issue.candle_open_time_ms,
                "details": issue.details,
            }
            for issue in result.issues
        ]
        sql = """
        INSERT INTO data_validation_runs (
            run_id,
            symbol,
            timeframe,
            evaluated_at_utc,
            is_valid,
            analysis_allowed,
            freshness_status,
            closed_candle_count,
            unfinished_candle_count,
            required_min_closed_candles,
            max_close_delay_seconds,
            expected_latest_closed_open_time_ms,
            actual_latest_closed_open_time_ms,
            close_delay_seconds,
            issues_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self._conn.execute(
            sql,
            (
                resolved_run_id,
                result.symbol,
                result.timeframe,
                result.evaluated_at_utc.isoformat(),
                1 if result.is_valid else 0,
                1 if result.analysis_allowed else 0,
                result.freshness_status.value,
                len(result.closed_candles),
                len(result.unfinished_candles),
                result.required_min_closed_candles,
                result.max_close_delay_seconds,
                result.expected_latest_closed_open_time_ms,
                result.actual_latest_closed_open_time_ms,
                result.close_delay_seconds,
                json.dumps(issues_payload),
            ),
        )
        self._conn.commit()
        return resolved_run_id

    def get_latest_validation_run(
        self,
        symbol: str,
        timeframe: str,
    ) -> dict[str, object] | None:
        """Retrieve the most recent validation audit record for a symbol and timeframe."""
        row = self._conn.fetchone_dict(
            """
            SELECT *
            FROM data_validation_runs
            WHERE symbol = ? AND timeframe = ?
            ORDER BY evaluated_at_utc DESC
            LIMIT 1
            """,
            (symbol.strip().upper(), timeframe.strip().lower()),
        )
        if row is None:
            return None
        row["issues"] = json.loads(str(row.get("issues_json") or "[]"))
        return row
