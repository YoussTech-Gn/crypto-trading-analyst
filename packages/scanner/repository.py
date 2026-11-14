"""Persistence for scan snapshots and rankings (SQLite for tests, PostgreSQL for production)."""

from __future__ import annotations

import json
from datetime import datetime

from database.session import DatabaseConnection
from packages.scanner.models import ScanEntry, ScanSnapshot


class ScannerRepository:
    def __init__(self, conn: DatabaseConnection) -> None:
        self._conn = conn

    def save_snapshot(self, snap: ScanSnapshot) -> str:
        shortlisted = len(snap.shortlisted)
        eligible = sum(1 for e in snap.entries if e.rank is not None)
        self._conn.execute(
            """
            INSERT INTO scan_snapshots (
                snapshot_id, created_at_utc, scanner_version, params_json, inputs_json,
                evaluated_count, ranked_count, shortlisted_count, non_target_quote_skipped
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snap.snapshot_id,
                snap.created_at_utc.isoformat(),
                snap.scanner_version,
                json.dumps(snap.params, sort_keys=True),
                json.dumps(snap.inputs, sort_keys=True),
                len(snap.entries),
                eligible,
                shortlisted,
                snap.non_target_quote_skipped,
            ),
        )
        self._conn.executemany(
            """
            INSERT INTO scan_rankings (
                snapshot_id, symbol, status, rank, quote_volume,
                price_change_percent, spread_bps, exclusion_reasons_json, category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snap.snapshot_id, e.symbol, e.status, e.rank, e.quote_volume,
                    e.price_change_percent, e.spread_bps, json.dumps(list(e.exclusion_reasons)), e.category,
                )
                for e in snap.entries
            ],
        )
        self._conn.commit()
        return snap.snapshot_id

    def get_snapshot(self, snapshot_id: str | None = None) -> ScanSnapshot | None:
        """Return the given snapshot, or the most recent one when `snapshot_id` is None."""
        if snapshot_id is None:
            row = self._conn.fetchone_dict(
                "SELECT * FROM scan_snapshots ORDER BY created_at_utc DESC, snapshot_id DESC LIMIT 1"
            )
        else:
            row = self._conn.fetchone_dict(
                "SELECT * FROM scan_snapshots WHERE snapshot_id = ?", (snapshot_id,)
            )
        if row is None:
            return None
        rows = self._conn.fetchall_dicts(
            """
            SELECT symbol, status, rank, quote_volume, price_change_percent, spread_bps,
                   exclusion_reasons_json, category
            FROM scan_rankings WHERE snapshot_id = ?
            ORDER BY CASE WHEN rank IS NULL THEN 1 ELSE 0 END, rank ASC, symbol ASC
            """,
            (row["snapshot_id"],),
        )
        entries = tuple(
            ScanEntry(
                symbol=r["symbol"],
                status=r["status"],
                rank=r["rank"],
                quote_volume=r["quote_volume"],
                price_change_percent=r["price_change_percent"],
                spread_bps=r["spread_bps"],
                exclusion_reasons=tuple(json.loads(r["exclusion_reasons_json"] or "[]")),
                category=r["category"],
            )
            for r in rows
        )
        return ScanSnapshot(
            snapshot_id=row["snapshot_id"],
            created_at_utc=datetime.fromisoformat(row["created_at_utc"]),
            scanner_version=row["scanner_version"],
            params=json.loads(row["params_json"]),
            inputs=json.loads(row["inputs_json"]),
            entries=entries,
            non_target_quote_skipped=int(row["non_target_quote_skipped"]),
        )
