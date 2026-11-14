"""Database migration runner for PostgreSQL and SQLite."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from database.session import DatabaseConnection

MIGRATIONS_DIR = Path(__file__).resolve().parent


def apply_migrations(
    conn: DatabaseConnection,
    migrations_dir: Path | None = None,
) -> list[str]:
    """Apply all unapplied `.sql` migrations in lexical order and record them in `schema_migrations`."""
    target_dir = migrations_dir or MIGRATIONS_DIR
    sql_files = sorted(target_dir.glob("*.sql"))
    if not sql_files:
        raise FileNotFoundError(f"No SQL migration files found in {target_dir}")

    # Ensure schema_migrations exists before querying applied versions
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(64) PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at_utc VARCHAR(64) NOT NULL
        )
        """
    )
    conn.commit()

    applied = set(get_applied_migrations(conn))
    newly_applied: list[str] = []

    for sql_file in sql_files:
        version = sql_file.stem
        if version in applied:
            continue
        script = sql_file.read_text(encoding="utf-8")
        conn.executescript(script)
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO schema_migrations (version, description, applied_at_utc)
            VALUES (?, ?, ?)
            ON CONFLICT (version) DO NOTHING
            """,
            (version, f"Applied {sql_file.name}", now_iso),
        )
        conn.commit()
        newly_applied.append(version)

    return newly_applied


def get_applied_migrations(conn: DatabaseConnection) -> list[str]:
    """Return list of applied migration versions ordered by version."""
    rows = conn.fetchall_dicts(
        "SELECT version FROM schema_migrations ORDER BY version ASC"
    )
    return [str(r["version"]) for r in rows]
