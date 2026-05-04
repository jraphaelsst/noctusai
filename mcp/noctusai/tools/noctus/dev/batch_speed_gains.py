"""Batch speed-gain tracker — local SQLite store for orchestrator-batch metrics.

Implements the storage layer for the `feedback_TEMP_methodology_validation_in_progress.md`
rule #2: every parallel-engineer batch logs (engineer_count, wall_clock_parallel_s,
estimated_serial_s, speed_gain_pct, notes) so the architect can scan trends across
batches as the orchestration grows. Mirrors `phase_learnings.py` shape — minimal
schema, stdlib only, no ORM.

The .db file lives at `mcp/noctusai/data/batch_speed_gains.db` and is gitignored
(root .gitignore entry `mcp/noctusai/data/`). Local-only; no cross-machine sync.

Rows can be opened in IN_FLIGHT state at dispatch time, then closed (status ->
COMPLETED + final timing) at batch-close. This way the table reflects in-flight
state during execution.

Public surface:
    get_db_path() -> Path
    log_batch(...) -> int
    update_batch(...) -> bool
    query_batches(...) -> list[dict]
    cumulative_stats(...) -> dict
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS batch_speed_gains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orchestration_slug TEXT NOT NULL,
    batch_label TEXT NOT NULL,
    engineer_count INTEGER NOT NULL,
    wall_clock_parallel_s REAL,
    estimated_serial_s REAL,
    speed_gain_pct REAL,
    tokens_total INTEGER,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'IN_FLIGHT',
    recorded_at TEXT NOT NULL,
    closed_at TEXT,
    created_by TEXT,
    UNIQUE(orchestration_slug, batch_label)
);

CREATE INDEX IF NOT EXISTS idx_batch_speed_gains_orchestration
    ON batch_speed_gains(orchestration_slug);
"""

# Idempotent migrations for evolving schemas. Each entry is a DDL statement
# that should be no-op'd if the column already exists. SQLite raises
# OperationalError("duplicate column name: ...") on re-add — we catch that
# specific message; any other OperationalError surfaces.
_MIGRATIONS = [
    "ALTER TABLE batch_speed_gains ADD COLUMN tokens_total INTEGER",
]

_VALID_STATUSES = {"IN_FLIGHT", "COMPLETED", "ABORTED"}


def get_db_path() -> Path:
    """Return the SQLite db path. Honors `NOCTUS_BATCH_SPEED_GAINS_DB` env override."""
    override = os.environ.get("NOCTUS_BATCH_SPEED_GAINS_DB")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "data" / "batch_speed_gains.db"


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    for ddl in _MIGRATIONS:
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _compute_gain_pct(parallel_s: float | None, serial_s: float | None) -> float | None:
    if parallel_s is None or serial_s is None or serial_s <= 0:
        return None
    return round((1.0 - (parallel_s / serial_s)) * 100.0, 1)


def log_batch(
    orchestration_slug: str,
    batch_label: str,
    engineer_count: int,
    wall_clock_parallel_s: float | None = None,
    estimated_serial_s: float | None = None,
    tokens_total: int | None = None,
    notes: str | None = None,
    status: str = "IN_FLIGHT",
    created_by: str | None = None,
    db_path: Path | None = None,
) -> int:
    """Insert a batch row. Returns the new row id.

    Raises sqlite3.IntegrityError on (orchestration_slug, batch_label) collision —
    use update_batch for closing an in-flight row.
    """
    if not orchestration_slug or not orchestration_slug.strip():
        raise ValueError("orchestration_slug must be non-empty")
    if not batch_label or not batch_label.strip():
        raise ValueError("batch_label must be non-empty")
    if engineer_count < 1:
        raise ValueError("engineer_count must be >= 1")
    if status not in _VALID_STATUSES:
        raise ValueError(f"status must be one of {_VALID_STATUSES}, got {status!r}")
    by = created_by or os.environ.get("NOCTUS_AGENT_ID") or "unknown"
    gain_pct = _compute_gain_pct(wall_clock_parallel_s, estimated_serial_s)
    closed = _now_iso() if status == "COMPLETED" else None
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO batch_speed_gains
                (orchestration_slug, batch_label, engineer_count,
                 wall_clock_parallel_s, estimated_serial_s, speed_gain_pct,
                 tokens_total, notes, status, recorded_at, closed_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                orchestration_slug.strip(),
                batch_label.strip(),
                int(engineer_count),
                wall_clock_parallel_s,
                estimated_serial_s,
                gain_pct,
                int(tokens_total) if tokens_total is not None else None,
                notes.strip() if notes else None,
                status,
                _now_iso(),
                closed,
                by,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_batch(
    orchestration_slug: str,
    batch_label: str,
    wall_clock_parallel_s: float | None = None,
    estimated_serial_s: float | None = None,
    tokens_total: int | None = None,
    notes: str | None = None,
    status: str | None = None,
    db_path: Path | None = None,
) -> bool:
    """Update an existing batch row (typically IN_FLIGHT -> COMPLETED).

    Only non-None fields are written. speed_gain_pct is recomputed if either
    timing field is updated. Returns True if a row was updated.
    """
    sets: list[str] = []
    params: list[Any] = []
    if wall_clock_parallel_s is not None:
        sets.append("wall_clock_parallel_s = ?")
        params.append(float(wall_clock_parallel_s))
    if estimated_serial_s is not None:
        sets.append("estimated_serial_s = ?")
        params.append(float(estimated_serial_s))
    if tokens_total is not None:
        sets.append("tokens_total = ?")
        params.append(int(tokens_total))
    if notes is not None:
        sets.append("notes = ?")
        params.append(notes.strip())
    if status is not None:
        if status not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {_VALID_STATUSES}, got {status!r}")
        sets.append("status = ?")
        params.append(status)
        if status == "COMPLETED":
            sets.append("closed_at = ?")
            params.append(_now_iso())
    if not sets:
        return False

    conn = _connect(db_path)
    try:
        # Recompute gain if timings ended up updated; read current row first.
        if wall_clock_parallel_s is not None or estimated_serial_s is not None:
            row = conn.execute(
                "SELECT wall_clock_parallel_s, estimated_serial_s FROM batch_speed_gains "
                "WHERE orchestration_slug = ? AND batch_label = ?",
                (orchestration_slug.strip(), batch_label.strip()),
            ).fetchone()
            if row is not None:
                p = wall_clock_parallel_s if wall_clock_parallel_s is not None else row["wall_clock_parallel_s"]
                s = estimated_serial_s if estimated_serial_s is not None else row["estimated_serial_s"]
                sets.append("speed_gain_pct = ?")
                params.append(_compute_gain_pct(p, s))

        params.extend([orchestration_slug.strip(), batch_label.strip()])
        cur = conn.execute(
            f"UPDATE batch_speed_gains SET {', '.join(sets)} "
            "WHERE orchestration_slug = ? AND batch_label = ?",
            params,
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def query_batches(
    orchestration_slug: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List batch rows. orchestration_slug=None returns every orchestration."""
    sql = "SELECT * FROM batch_speed_gains"
    params: list[Any] = []
    if orchestration_slug:
        sql += " WHERE orchestration_slug = ?"
        params.append(orchestration_slug.strip())
    sql += " ORDER BY orchestration_slug, id"
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def cumulative_stats(
    orchestration_slug: str,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Aggregate completed batches for an orchestration: total engineers, total
    parallel seconds, total estimated-serial seconds, overall % gain.

    IN_FLIGHT and ABORTED rows are excluded.
    """
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS batch_count,
                SUM(engineer_count) AS engineer_total,
                SUM(wall_clock_parallel_s) AS parallel_total_s,
                SUM(estimated_serial_s) AS serial_total_s,
                SUM(tokens_total) AS tokens_total_sum
            FROM batch_speed_gains
            WHERE orchestration_slug = ? AND status = 'COMPLETED'
            """,
            (orchestration_slug.strip(),),
        ).fetchone()
        parallel_total = row["parallel_total_s"]
        serial_total = row["serial_total_s"]
        return {
            "orchestration_slug": orchestration_slug.strip(),
            "batch_count": row["batch_count"] or 0,
            "engineer_total": row["engineer_total"] or 0,
            "parallel_total_s": parallel_total,
            "serial_total_s": serial_total,
            "speed_gain_pct": _compute_gain_pct(parallel_total, serial_total),
            "tokens_total": row["tokens_total_sum"],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# FastMCP tool registration — see KB § PATTERNS/mcp-tool-conventions.md.
# ---------------------------------------------------------------------------

def register(server) -> None:
    """Register MCP tools for batch-speed-gain tracking."""

    @server.tool(
        name="noctus.dev.batch_speed_gain_log",
        description=(
            "Log a parallel-engineer batch's speed metrics to the local SQLite tracker. "
            "Pass status='IN_FLIGHT' at dispatch + close via batch_speed_gain_update; "
            "or log directly with status='COMPLETED'. speed_gain_pct is auto-computed."
        ),
    )
    def _batch_speed_gain_log(
        orchestration_slug: str,
        batch_label: str,
        engineer_count: int,
        wall_clock_parallel_s: float | None = None,
        estimated_serial_s: float | None = None,
        tokens_total: int | None = None,
        notes: str | None = None,
        status: str = "IN_FLIGHT",
        created_by: str | None = None,
    ) -> dict:
        new_id = log_batch(
            orchestration_slug=orchestration_slug,
            batch_label=batch_label,
            engineer_count=engineer_count,
            wall_clock_parallel_s=wall_clock_parallel_s,
            estimated_serial_s=estimated_serial_s,
            tokens_total=tokens_total,
            notes=notes,
            status=status,
            created_by=created_by,
        )
        return {"id": new_id}

    @server.tool(
        name="noctus.dev.batch_speed_gain_update",
        description=(
            "Update an existing batch row (typically IN_FLIGHT -> COMPLETED with final timings). "
            "Only non-None fields are written; speed_gain_pct is recomputed if timings change."
        ),
    )
    def _batch_speed_gain_update(
        orchestration_slug: str,
        batch_label: str,
        wall_clock_parallel_s: float | None = None,
        estimated_serial_s: float | None = None,
        tokens_total: int | None = None,
        notes: str | None = None,
        status: str | None = None,
    ) -> dict:
        ok = update_batch(
            orchestration_slug=orchestration_slug,
            batch_label=batch_label,
            wall_clock_parallel_s=wall_clock_parallel_s,
            estimated_serial_s=estimated_serial_s,
            tokens_total=tokens_total,
            notes=notes,
            status=status,
        )
        return {"updated": ok}

    @server.tool(
        name="noctus.dev.batch_speed_gain_query",
        description=(
            "List batch rows for one orchestration (or all if orchestration_slug=None). "
            "Returns per-batch detail rows ready for table rendering."
        ),
    )
    def _batch_speed_gain_query(
        orchestration_slug: str | None = None,
    ) -> dict:
        rows = query_batches(orchestration_slug=orchestration_slug)
        return {"batches": rows}

    @server.tool(
        name="noctus.dev.batch_speed_gain_cumulative",
        description=(
            "Aggregate COMPLETED batches for an orchestration: batch count, engineer total, "
            "wall-clock parallel total, estimated serial total, overall speed gain %."
        ),
    )
    def _batch_speed_gain_cumulative(
        orchestration_slug: str,
    ) -> dict:
        return cumulative_stats(orchestration_slug=orchestration_slug)
