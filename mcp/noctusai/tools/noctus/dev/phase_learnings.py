"""Phase-learnings tracker — local SQLite store for per-phase learnings.

Implements the storage layer for the phase-enrichment-loop methodology rule
(`KB § PATTERNS/project-execution.md § 2.11`). Every shipped phase logs
≥1 learning; the next phase queries unconsumed learnings and folds the
relevant ones into its plan, then marks them consumed.

Schema is intentionally minimal — one table, no ORM, no migration framework.
The user has future plans for the tracker; over-engineering now would obscure
intent. When new use cases surface, columns/tables get added then.

The .db file lives at `mcp/noctusai/data/phase_learnings.db` and is
gitignored (root .gitignore entry `mcp/noctusai/data/`). Local-only; no
cross-machine sync.

Public surface:
    get_db_path() -> Path
    log_learning(...) -> int
    query_learnings(...) -> list[dict]
    consume_learning(...) -> bool

Tests live at `mcp/noctusai/tests/test_phase_learnings.py`. The MCP tool
wrappers (`noctus.dev.phase_learning_log`, `noctus.dev.phase_learning_query`,
`noctus.dev.phase_learning_consume`) are registered via `register(server)`
at module bottom per the per-file FastMCP registration pattern.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Module is imported by both library callers and FastMCP tool registration.
# Top-level import time stays cheap — only stdlib + Path.

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS phase_learnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_slug TEXT NOT NULL,
    phase_number INTEGER NOT NULL,
    phase_title TEXT,
    learning_kind TEXT,
    learning_text TEXT NOT NULL,
    shipped_at TEXT NOT NULL,
    consumed_by_phase_number INTEGER,
    consumed_at TEXT,
    created_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_phase_learnings_project_slug
    ON phase_learnings(project_slug);

CREATE INDEX IF NOT EXISTS idx_phase_learnings_unconsumed
    ON phase_learnings(project_slug, consumed_by_phase_number);
"""

_VALID_KINDS = {"methodology", "technical", "process", "tool", "other"}


def get_db_path() -> Path:
    """Return the SQLite db path. Honors `NOCTUS_PHASE_LEARNINGS_DB` env override (used in tests)."""
    override = os.environ.get("NOCTUS_PHASE_LEARNINGS_DB")
    if override:
        return Path(override)
    # Default: mcp/noctusai/data/phase_learnings.db (gitignored).
    # Walk up from this file: tools/noctus/dev/phase_learnings.py → tools/noctus/dev → tools/noctus → tools → noctusai
    return Path(__file__).resolve().parents[3] / "data" / "phase_learnings.db"


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a connection to the db, creating the parent dir + schema lazily."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_learning(
    project_slug: str,
    phase_number: int,
    phase_title: str | None,
    learning_kind: str,
    learning_text: str,
    created_by: str | None = None,
    db_path: Path | None = None,
) -> int:
    """Append a phase learning. Returns the new row id.

    Args:
        project_slug: e.g. 'phase-detector-and-enrichment-loop'
        phase_number: 0-indexed phase number from §6
        phase_title: free-form, e.g. 'Detector regex precision' (None ok)
        learning_kind: one of 'methodology' / 'technical' / 'process' / 'tool' / 'other'
        learning_text: 1-3 sentence non-obvious insight discovered during the phase
        created_by: agent identity, e.g. 'claude-opus-4-7' (None → reads NOCTUS_AGENT_ID env or 'unknown')
        db_path: override (tests)
    """
    if not project_slug or not project_slug.strip():
        raise ValueError("project_slug must be non-empty")
    if not learning_text or not learning_text.strip():
        raise ValueError("learning_text must be non-empty")
    if learning_kind not in _VALID_KINDS:
        raise ValueError(f"learning_kind must be one of {_VALID_KINDS}, got {learning_kind!r}")
    by = created_by or os.environ.get("NOCTUS_AGENT_ID") or "unknown"
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO phase_learnings
                (project_slug, phase_number, phase_title, learning_kind,
                 learning_text, shipped_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_slug.strip(),
                int(phase_number),
                phase_title.strip() if phase_title else None,
                learning_kind,
                learning_text.strip(),
                _now_iso(),
                by,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def query_learnings(
    project_slug: str,
    phase_number: int | None = None,
    unconsumed_only: bool = False,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List learnings for a project. Returns rows as plain dicts.

    Args:
        project_slug: required filter
        phase_number: optional — restrict to one phase
        unconsumed_only: if True, exclude rows already marked consumed
        db_path: override (tests)
    """
    if not project_slug or not project_slug.strip():
        raise ValueError("project_slug must be non-empty")
    sql = "SELECT * FROM phase_learnings WHERE project_slug = ?"
    params: list[Any] = [project_slug.strip()]
    if phase_number is not None:
        sql += " AND phase_number = ?"
        params.append(int(phase_number))
    if unconsumed_only:
        sql += " AND consumed_by_phase_number IS NULL"
    sql += " ORDER BY phase_number, id"
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def consume_learning(
    learning_id: int,
    by_phase_number: int,
    db_path: Path | None = None,
) -> bool:
    """Mark a learning as consumed by a later phase. Returns True if a row was updated."""
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            UPDATE phase_learnings
            SET consumed_by_phase_number = ?, consumed_at = ?
            WHERE id = ? AND consumed_by_phase_number IS NULL
            """,
            (int(by_phase_number), _now_iso(), int(learning_id)),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# FastMCP tool registration — see KB § PATTERNS/mcp-tool-conventions.md.
# ---------------------------------------------------------------------------

def register(server) -> None:
    """Register MCP tools for phase-learnings tracking.

    Per `KB § PATTERNS/mcp-tool-conventions.md` — 3-segment dotted naming
    (`<vendor>.<service>.<action>`), direct function args matching the
    existing dev-umbrella convention, lazy connection.
    """
    @server.tool(
        name="noctus.dev.phase_learning_log",
        description=(
            "Append a phase learning to the local SQLite tracker. Returns the new row id. "
            "Each shipped phase logs ≥1 learning per `KB § PATTERNS/project-execution.md § 2.11 "
            "Phase enrichment loop`. Kinds: methodology / technical / process / tool / other."
        ),
    )
    def _phase_learning_log(
        project_slug: str,
        phase_number: int,
        learning_kind: str,
        learning_text: str,
        phase_title: str | None = None,
        created_by: str | None = None,
    ) -> dict:
        new_id = log_learning(
            project_slug=project_slug,
            phase_number=phase_number,
            phase_title=phase_title,
            learning_kind=learning_kind,
            learning_text=learning_text,
            created_by=created_by,
        )
        return {"id": new_id}

    @server.tool(
        name="noctus.dev.phase_learning_query",
        description=(
            "List phase learnings for a project. Optionally filter by phase or restrict to "
            "unconsumed rows (the next phase reads unconsumed_only=True to find what to fold in)."
        ),
    )
    def _phase_learning_query(
        project_slug: str,
        phase_number: int | None = None,
        unconsumed_only: bool = False,
    ) -> dict:
        rows = query_learnings(
            project_slug=project_slug,
            phase_number=phase_number,
            unconsumed_only=unconsumed_only,
        )
        return {"learnings": rows}

    @server.tool(
        name="noctus.dev.phase_learning_consume",
        description=(
            "Mark a learning as consumed by a later phase. Returns {consumed: bool} — False "
            "if the row was already consumed or the id doesn't exist."
        ),
    )
    def _phase_learning_consume(
        learning_id: int,
        by_phase_number: int,
    ) -> dict:
        ok = consume_learning(
            learning_id=learning_id,
            by_phase_number=by_phase_number,
        )
        return {"consumed": ok}
