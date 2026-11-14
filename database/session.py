"""Dual-dialect DatabaseConnection wrapper supporting PostgreSQL (production) and SQLite (automated tests).

Handles parameter placeholder translation (`?` for SQLite vs `%s` for PostgreSQL DB-API 2.0 drivers
like `psycopg` / `psycopg2`) and enforces foreign-key constraints in SQLite so both backends
behave consistently.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Sequence


class DatabaseConnection:
    """Unified DB-API 2.0 connection adapter for PostgreSQL and SQLite."""

    def __init__(
        self,
        raw_connection: Any,
        dialect: str,
        database_url: str,
    ) -> None:
        if dialect not in ("postgresql", "sqlite"):
            raise ValueError(f"Unsupported dialect '{dialect}'")
        self.raw_connection = raw_connection
        self.dialect = dialect
        self.database_url = database_url

    def translate_sql(self, sql: str) -> str:
        """Translate `?` placeholders to `%s` when targeting PostgreSQL."""
        if self.dialect == "postgresql":
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        translated = self.translate_sql(sql)
        cursor = self.raw_connection.cursor()
        cursor.execute(translated, tuple(params))
        return cursor

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> Any:
        translated = self.translate_sql(sql)
        cursor = self.raw_connection.cursor()
        cursor.executemany(translated, [tuple(p) for p in seq_of_params])
        return cursor

    def executescript(self, sql_script: str) -> None:
        """Execute a multi-statement SQL migration script."""
        if self.dialect == "sqlite":
            self.raw_connection.executescript(sql_script)
            self.raw_connection.execute("PRAGMA foreign_keys = ON;")
        else:
            cursor = self.raw_connection.cursor()
            statements = [
                stmt.strip()
                for stmt in self._split_sql_statements(sql_script)
                if stmt.strip()
            ]
            for stmt in statements:
                cursor.execute(stmt)

    @staticmethod
    def _split_sql_statements(sql_script: str) -> list[str]:
        """Split a SQL script into individual statements while stripping line comments."""
        cleaned_lines: list[str] = []
        for line in sql_script.splitlines():
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            cleaned_lines.append(line)
        joined = "\n".join(cleaned_lines)
        return [part.strip() for part in joined.split(";") if part.strip()]

    def fetchall_dicts(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        cursor = self.execute(sql, params)
        rows = cursor.fetchall()
        if not rows:
            return []
        col_names = [desc[0] for desc in cursor.description]
        return [dict(zip(col_names, row)) for row in rows]

    def fetchone_dict(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        rows = self.fetchall_dicts(sql, params)
        return rows[0] if rows else None

    def commit(self) -> None:
        self.raw_connection.commit()

    def rollback(self) -> None:
        self.raw_connection.rollback()

    def close(self) -> None:
        self.raw_connection.close()

    def __enter__(self) -> "DatabaseConnection":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.rollback()
        self.close()


def create_connection(database_url: str, pg_driver_override: Any | None = None) -> DatabaseConnection:
    """Create a DatabaseConnection for either `postgresql://...` or `sqlite:///...`."""
    url = database_url.strip()
    if url.startswith("sqlite:///"):
        db_path = url[len("sqlite:///") :]
        # FastAPI runs sync endpoints in a worker threadpool; allow the single shared connection
        # across threads (SQLite is compiled in serialized mode).
        raw_conn = sqlite3.connect(db_path, check_same_thread=False)
        raw_conn.execute("PRAGMA foreign_keys = ON;")
        return DatabaseConnection(raw_conn, dialect="sqlite", database_url=url)

    if url.startswith("postgresql://") or url.startswith("postgres://"):
        if pg_driver_override is not None:
            raw_conn = pg_driver_override.connect(url)
            return DatabaseConnection(raw_conn, dialect="postgresql", database_url=url)

        for driver_name in ("psycopg", "psycopg2"):
            try:
                driver = __import__(driver_name)
                raw_conn = driver.connect(url)
                return DatabaseConnection(raw_conn, dialect="postgresql", database_url=url)
            except ImportError:
                continue
        raise RuntimeError(
            "PostgreSQL connection requested, but neither 'psycopg' nor 'psycopg2' is installed "
            "in the current Python environment."
        )

    raise ValueError(f"Unsupported database_url scheme: {database_url}")
