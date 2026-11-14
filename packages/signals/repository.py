"""Persistence for signal decisions (SQLite for tests, PostgreSQL for production)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from database.session import DatabaseConnection
from packages.signals.generator import SignalDecision


class SignalRepository:
    def __init__(self, conn: DatabaseConnection) -> None:
        self._conn = conn

    def save(self, d: SignalDecision, created_at_utc: datetime) -> bool:
        """Idempotent: a decision for the same symbol and 4H candle is stored once. Returns True if inserted."""
        if self._conn.fetchone_dict("SELECT 1 AS x FROM signal_decisions WHERE signal_id = ?", (d.signal_id,)):
            return False
        self._conn.execute(
            """
            INSERT INTO signal_decisions (
                signal_id, symbol, decision, created_at_utc, setup_candle_open_time_ms,
                signal_version, analysis_version, entry_price, stop_price, target_price,
                risk_reward, signal_time_ms, valid_until_ms,
                reasons_json, checks_json, evidence_json, params_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                d.signal_id, d.symbol, d.decision, created_at_utc.isoformat(), d.setup_candle_open_time_ms,
                d.signal_version, d.analysis_version, d.entry, d.stop, d.target, d.risk_reward,
                d.signal_time_ms, d.valid_until_ms,
                json.dumps(list(d.reasons)), json.dumps(d.checks, sort_keys=True),
                json.dumps(d.evidence, sort_keys=True, default=str), json.dumps(d.params, sort_keys=True),
            ),
        )
        self._conn.commit()
        return True

    def list_recent(self, decision: str | None = None, symbol: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        where, args = [], []
        if decision:
            where.append("decision = ?"); args.append(decision)
        if symbol:
            where.append("symbol = ?"); args.append(symbol.upper())
        sql = "SELECT * FROM signal_decisions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at_utc DESC, symbol ASC LIMIT ?"
        args.append(limit)
        rows = self._conn.fetchall_dicts(sql, tuple(args))
        for r in rows:
            r["reasons"] = json.loads(r.pop("reasons_json"))
            r["checks"] = json.loads(r.pop("checks_json"))
            r["evidence"] = json.loads(r.pop("evidence_json"))
            r["params"] = json.loads(r.pop("params_json"))
        return rows
