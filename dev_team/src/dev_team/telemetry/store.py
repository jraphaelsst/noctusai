"""Telemetry SQLite store — schema + connection helpers.

Schema (verbatim from PROJECT.md §5.4):

    CREATE TABLE events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       TEXT NOT NULL,
        project         TEXT,
        config_name     TEXT NOT NULL,
        agent_name      TEXT NOT NULL,
        sub_team        TEXT,
        turn_index      INTEGER NOT NULL,
        input_tokens    INTEGER NOT NULL,
        output_tokens   INTEGER NOT NULL,
        total_cost_usd  REAL NOT NULL,
        latency_ms      INTEGER NOT NULL,
        tool_calls      TEXT,
        outcome         TEXT NOT NULL,
        output_chars    INTEGER NOT NULL,
        task_hash       TEXT
    );

Plus indexes on agent_name / project / timestamp, and a
``schema_version`` table that drives idempotent migrations.

Default DB path is
``dev_team/src/dev_team/memory/store/telemetry.sqlite`` (sibling to
the project memory). Tests override via :func:`set_db_path` to use
``tmp_path`` for isolation — never touch the real store.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from noctusai_lib.primitives.timeutil import now_utc

# Default path matches PROJECT.md §5.4 exactly.
_DEFAULT_DB_PATH = (
    Path(__file__).resolve().parent.parent / "memory" / "store" / "telemetry.sqlite"
)
_db_path: Path = _DEFAULT_DB_PATH


def set_db_path(path: Path | str) -> None:
    """Override the on-disk DB path (tests use ``tmp_path``)."""
    global _db_path
    _db_path = Path(path)


def get_db_path() -> Path:
    return _db_path


# Migrations are an ordered list of (version, ddl) pairs. Each runs
# at most once (idempotency keyed off ``schema_version`` table).
_MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        # Combined DDL for v1: events table + indexes.
        """
        CREATE TABLE IF NOT EXISTS events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            project         TEXT,
            config_name     TEXT NOT NULL,
            agent_name      TEXT NOT NULL,
            sub_team        TEXT,
            turn_index      INTEGER NOT NULL,
            input_tokens    INTEGER NOT NULL,
            output_tokens   INTEGER NOT NULL,
            total_cost_usd  REAL NOT NULL,
            latency_ms      INTEGER NOT NULL,
            tool_calls      TEXT,
            outcome         TEXT NOT NULL,
            output_chars    INTEGER NOT NULL,
            task_hash       TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_name);
        CREATE INDEX IF NOT EXISTS idx_events_project ON events(project);
        CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
        """,
    ),
]

CURRENT_SCHEMA_VERSION = max(v for v, _ in _MIGRATIONS)


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "  version INTEGER NOT NULL,"
        "  applied_at TEXT NOT NULL"
        ")"
    )


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute("SELECT version FROM schema_version").fetchall()
    return {row[0] for row in rows}


def _apply_migrations(conn: sqlite3.Connection) -> None:
    _ensure_schema_version_table(conn)
    applied = _applied_versions(conn)
    ts = now_utc().isoformat()
    for version, ddl in _MIGRATIONS:
        if version in applied:
            continue
        conn.executescript(ddl)
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (version, ts),
        )
    conn.commit()


def connect() -> sqlite3.Connection:
    """Open the telemetry DB, applying any pending migrations.

    Creates parent directory if missing. Returns a fresh connection
    (caller is responsible for closing — typically via ``with``).
    """
    path = _db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _apply_migrations(conn)
    return conn


def applied_schema_versions() -> list[int]:
    """Return the schema versions applied to the current DB (sorted)."""
    with connect() as conn:
        return sorted(_applied_versions(conn))


__all__ = [
    "connect",
    "set_db_path",
    "get_db_path",
    "applied_schema_versions",
    "CURRENT_SCHEMA_VERSION",
]
