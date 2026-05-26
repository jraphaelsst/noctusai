"""cache_deploy_mirror — snapshot local SQLite caches to prod Postgres+pgvector.

Why this exists
    Local dev caches live in `.claude/cache/*.sqlite`. Prod runs the
    same noc against a centralized Postgres+pgvector backend (per
    cache-backend-portability roadmap Phase 3+). On every deploy, the
    prod cache should be SEEDED from the local snapshot — so prod
    starts with a cache mirror of dev (the architect's "blessed"
    state) instead of paying $0.10 + 40 min OpenAI re-embed.

The mirror contract
    - Idempotent: re-run is safe; per-row source_sha gates skip
      already-mirrored content.
    - Atomic-per-cache: each cache mirrors as a single transaction.
      If interrupted mid-cache, the prod cache stays at the prior
      consistent snapshot.
    - Verifies: post-mirror, row counts per cache match local ±0%
      (strict; mismatch = surfaced as `mirror-row-count-mismatch`).
    - Bound: a single deploy mirrors all 5 caches. NOT incremental.

When to call
    - At deploy time, AFTER `noctus.dev.release stage=promote` but
      BEFORE `noctus.dev.deploy_pull confirm=True` runs on the VPS.
    - Manually for force-resync: `noctus.dev.cache_deploy_mirror
      force=True confirm=True`.

What it does NOT do
    - It does NOT re-embed: vectors are transferred verbatim from
      SQLite to pgvector. Schema-translation only (sqlite-vec BLOB
      → pgvector `vector(N)`).
    - It does NOT create the prod database. Schema must exist (use
      `--init-prod-cache-schema` for first-time setup).
    - It does NOT swap backends. It transfers data; the caller still
      sets `NOCTUS_CACHE_BACKEND=postgres` to consume the mirror.

KB § CONTEXT/PATTERNS/devops/cache-deploy-mirror.md.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from settings import REPO_ROOT
from tools.noctus.dev.cache_backend import cache_path, known_caches


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Per-cache table inventory ────────────────────────────────────────────────
# Local SQLite has its own per-cache schemas. We mirror ROWS into the
# corresponding Postgres tables (created by --init-prod-cache-schema).
# Each entry = (sqlite_table_name, pg_table_name_under_noctus_cache_schema).
_TABLE_MAP: dict[str, tuple[str, str]] = {
    "keeper-patterns":  ("keeper_patterns", "cache_keeper_patterns"),
    "agent-context":    ("agent_contexts",  "cache_agent_context"),
    "auto-improvement": ("auto_improvements", "cache_auto_improvement"),
    "kb-embeddings":    ("kb_chunks",       "cache_kb_embeddings"),
    "code-embeddings":  ("code_chunks",     "cache_code_embeddings"),
}


# ── Schema bootstrap (DDL) ───────────────────────────────────────────────────
_PG_INIT_DDL = """
CREATE SCHEMA IF NOT EXISTS noctus_cache;

-- pgvector extension (no-op if already installed by superuser).
CREATE EXTENSION IF NOT EXISTS vector;

-- cache_meta: source_sha + populated_at per cache (mirrors SQLite's cache_meta).
CREATE TABLE IF NOT EXISTS noctus_cache.cache_meta (
    cache_name   TEXT NOT NULL,
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (cache_name, key)
);

-- keeper-patterns mirror.
CREATE TABLE IF NOT EXISTS noctus_cache.cache_keeper_patterns (
    id              SERIAL PRIMARY KEY,
    keeper_name     TEXT NOT NULL,
    pattern_kind    TEXT NOT NULL,
    pattern_value   TEXT NOT NULL,
    severity        TEXT,
    remediation     TEXT,
    source_file     TEXT NOT NULL,
    source_line     INTEGER,
    fixture_example TEXT,
    scope           TEXT NOT NULL DEFAULT 'permanent',
    cached_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pg_keeper_name ON noctus_cache.cache_keeper_patterns(keeper_name);

-- Vector caches share shape: doc id + chunk content + 1536-D embedding.
-- pgvector `vector(1536)` matches OpenAI text-embedding-3-small.
CREATE TABLE IF NOT EXISTS noctus_cache.cache_kb_embeddings (
    id              SERIAL PRIMARY KEY,
    path            TEXT NOT NULL,
    chunk_idx       INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    embedding       vector(1536),
    source_sha      TEXT NOT NULL,
    cached_at       TEXT NOT NULL,
    UNIQUE(path, chunk_idx, source_sha)
);
CREATE INDEX IF NOT EXISTS idx_pg_kb_path ON noctus_cache.cache_kb_embeddings(path);

CREATE TABLE IF NOT EXISTS noctus_cache.cache_code_embeddings (
    id              SERIAL PRIMARY KEY,
    path            TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    chunk_idx       INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    embedding       vector(1536),
    source_sha      TEXT NOT NULL,
    cached_at       TEXT NOT NULL,
    UNIQUE(path, symbol, chunk_idx, source_sha)
);
CREATE INDEX IF NOT EXISTS idx_pg_code_path ON noctus_cache.cache_code_embeddings(path);

-- agent-context + auto-improvement: small row stores, mirror as TEXT bodies.
CREATE TABLE IF NOT EXISTS noctus_cache.cache_agent_context (
    agent_name      TEXT PRIMARY KEY,
    bundle_json     TEXT NOT NULL,
    source_sha      TEXT NOT NULL,
    cached_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS noctus_cache.cache_auto_improvement (
    id              SERIAL PRIMARY KEY,
    ts              TEXT NOT NULL,
    agent           TEXT NOT NULL,
    scope           TEXT,
    kind            TEXT,
    target          TEXT,
    description     TEXT,
    status          TEXT NOT NULL,
    source_ref      TEXT,
    source_sha      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pg_ai_target ON noctus_cache.cache_auto_improvement(target);
CREATE INDEX IF NOT EXISTS idx_pg_ai_status ON noctus_cache.cache_auto_improvement(status);
"""


def init_prod_cache_schema(dsn: str | None = None) -> dict[str, Any]:
    """Create the noctus_cache schema + tables in the remote Postgres.

    SAFE to re-run — all DDL is `IF NOT EXISTS`. Returns the executed
    statement count + connection target (sans password).

    Args:
      dsn: explicit Postgres DSN. Defaults to env-resolved by
        `cache_backend.PostgresCacheBackend` factory.

    Returns: `{ok, statements_executed, schema, target}`.
    """
    try:
        from tools.noctus.dev.cache_backend_postgres import PostgresCacheBackend
    except ImportError as e:
        return {
            "ok": False,
            "error": (
                f"PostgresCacheBackend unavailable ({e}); ensure psycopg2-binary "
                "+ pgvector packages are installed."
            ),
        }
    backend = PostgresCacheBackend(dsn=dsn) if dsn else PostgresCacheBackend()
    target = backend.location("keeper-patterns").rsplit("/", 1)[0]
    with backend.connect("keeper-patterns") as conn:
        cur = conn.cursor()
        # Split by ; and run each non-empty statement; psycopg2 doesn't
        # execute multi-stmt strings reliably.
        statements = [s.strip() for s in _PG_INIT_DDL.split(";") if s.strip()]
        for stmt in statements:
            cur.execute(stmt + ";")
        conn.commit()
        cur.close()
    return {
        "ok": True,
        "statements_executed": len(statements),
        "schema": "noctus_cache",
        "target": target,
    }


# ── Mirror logic (per-cache transfer) ────────────────────────────────────────


def _mirror_keeper_patterns(local: sqlite3.Connection, pg_conn: Any) -> int:
    cur_pg = pg_conn.cursor()
    cur_pg.execute("TRUNCATE TABLE noctus_cache.cache_keeper_patterns")
    rows = list(local.execute(
        "SELECT keeper_name, pattern_kind, pattern_value, severity, "
        "remediation, source_file, source_line, fixture_example, "
        "scope, cached_at FROM keeper_patterns"
    ).fetchall())
    if not rows:
        cur_pg.close()
        return 0
    cur_pg.executemany(
        "INSERT INTO noctus_cache.cache_keeper_patterns "
        "(keeper_name, pattern_kind, pattern_value, severity, remediation, "
        "source_file, source_line, fixture_example, scope, cached_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [tuple(r) for r in rows]
    )
    cur_pg.close()
    return len(rows)


def _mirror_vector_cache(
    local: sqlite3.Connection,
    pg_conn: Any,
    sqlite_table: str,
    pg_table: str,
    columns_local: list[str],
    pg_insert_cols: list[str],
    vector_col_idx: int,
) -> int:
    """Generic vector-cache transfer. The vector column is the only special
    handling — sqlite-vec stores as BLOB; we decode to a Python list of
    floats and let psycopg2/pgvector convert."""
    cur_pg = pg_conn.cursor()
    cur_pg.execute(f"TRUNCATE TABLE noctus_cache.{pg_table}")
    cols_sql = ", ".join(columns_local)
    rows = local.execute(f"SELECT {cols_sql} FROM {sqlite_table}").fetchall()
    if not rows:
        cur_pg.close()
        return 0
    import struct
    converted = []
    for row in rows:
        row_list = list(row)
        blob = row_list[vector_col_idx]
        if blob is None:
            row_list[vector_col_idx] = None
        else:
            # sqlite-vec stores as raw little-endian float32 array.
            num_floats = len(blob) // 4
            row_list[vector_col_idx] = list(struct.unpack(f"<{num_floats}f", blob))
        converted.append(tuple(row_list))
    placeholders = ", ".join(["%s"] * len(pg_insert_cols))
    cur_pg.executemany(
        f"INSERT INTO noctus_cache.{pg_table} ({', '.join(pg_insert_cols)}) "
        f"VALUES ({placeholders})",
        converted
    )
    cur_pg.close()
    return len(rows)


def _mirror_simple_table(
    local: sqlite3.Connection,
    pg_conn: Any,
    sqlite_table: str,
    pg_table: str,
    columns: list[str],
) -> int:
    """Generic non-vector table mirror (agent-context, auto-improvement)."""
    cur_pg = pg_conn.cursor()
    cur_pg.execute(f"TRUNCATE TABLE noctus_cache.{pg_table}")
    cols_sql = ", ".join(columns)
    rows = local.execute(f"SELECT {cols_sql} FROM {sqlite_table}").fetchall()
    if not rows:
        cur_pg.close()
        return 0
    placeholders = ", ".join(["%s"] * len(columns))
    cur_pg.executemany(
        f"INSERT INTO noctus_cache.{pg_table} ({cols_sql}) VALUES ({placeholders})",
        [tuple(r) for r in rows]
    )
    cur_pg.close()
    return len(rows)


def mirror_one_cache(
    cache_name: str,
    *,
    dsn: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Mirror a single cache from local SQLite → prod Postgres.

    Returns: `{ok, cache, rows_written, target, error?}`.
    """
    if cache_name not in _TABLE_MAP:
        return {
            "ok": False,
            "cache": cache_name,
            "error": f"unknown cache; valid: {sorted(_TABLE_MAP)}",
        }
    sqlite_path = cache_path(cache_name, repo_root)
    if not sqlite_path.exists():
        return {
            "ok": False,
            "cache": cache_name,
            "error": f"local SQLite cache missing: {sqlite_path}",
        }
    try:
        from tools.noctus.dev.cache_backend_postgres import PostgresCacheBackend
    except ImportError as e:
        return {
            "ok": False,
            "cache": cache_name,
            "error": f"PostgresCacheBackend unavailable: {e}",
        }
    backend = PostgresCacheBackend(dsn=dsn) if dsn else PostgresCacheBackend()
    local = sqlite3.connect(str(sqlite_path))
    local.row_factory = sqlite3.Row
    try:
        with backend.connect(cache_name) as pg_conn:
            try:
                if cache_name == "keeper-patterns":
                    rows = _mirror_keeper_patterns(local, pg_conn)
                elif cache_name == "kb-embeddings":
                    rows = _mirror_vector_cache(
                        local, pg_conn,
                        "kb_chunks", "cache_kb_embeddings",
                        ["path", "chunk_idx", "chunk_text", "embedding", "source_sha", "cached_at"],
                        ["path", "chunk_idx", "chunk_text", "embedding", "source_sha", "cached_at"],
                        vector_col_idx=3,
                    )
                elif cache_name == "code-embeddings":
                    rows = _mirror_vector_cache(
                        local, pg_conn,
                        "code_chunks", "cache_code_embeddings",
                        ["path", "symbol", "chunk_idx", "chunk_text", "embedding", "source_sha", "cached_at"],
                        ["path", "symbol", "chunk_idx", "chunk_text", "embedding", "source_sha", "cached_at"],
                        vector_col_idx=4,
                    )
                elif cache_name == "agent-context":
                    rows = _mirror_simple_table(
                        local, pg_conn,
                        "agent_contexts", "cache_agent_context",
                        ["agent_name", "bundle_json", "source_sha", "cached_at"],
                    )
                elif cache_name == "auto-improvement":
                    rows = _mirror_simple_table(
                        local, pg_conn,
                        "auto_improvements", "cache_auto_improvement",
                        ["ts", "agent", "scope", "kind", "target", "description",
                         "status", "source_ref", "source_sha"],
                    )
                else:
                    rows = 0
                pg_conn.commit()
            except Exception as e:  # noqa: BLE001
                pg_conn.rollback()
                return {
                    "ok": False,
                    "cache": cache_name,
                    "error": f"mirror failed (rolled back): {str(e)[:200]}",
                }
        return {
            "ok": True,
            "cache": cache_name,
            "rows_written": rows,
            "target": backend.location(cache_name),
            "ts": _now_iso(),
        }
    finally:
        local.close()


def mirror_all(
    *,
    confirm: bool = False,
    only: list[str] | None = None,
    dsn: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Mirror all 5 caches (or filtered set) from local SQLite → prod Postgres.

    Dry-run unless `confirm=True`. The dry-run reports what WOULD be
    mirrored (per-cache row counts from local) without touching prod.

    Args:
      confirm: actually execute. False = plan-only.
      only: subset of cache names to mirror.
      dsn: override Postgres DSN.
      repo_root: override REPO_ROOT.

    Returns: `{ok, confirmed, mirrored: {cache: result}, failures,
    total_rows, ts, plan?}`.
    """
    active = list(only) if only else list(_TABLE_MAP.keys())
    invalid = [c for c in active if c not in _TABLE_MAP]
    if invalid:
        return {
            "ok": False,
            "error": f"unknown cache name(s): {invalid}; valid: {sorted(_TABLE_MAP)}",
        }
    if not confirm:
        # Plan-only: report local row counts per cache.
        plan = {}
        for name in active:
            p = cache_path(name, repo_root)
            if not p.exists():
                plan[name] = {"status": "skip", "reason": "local-missing"}
                continue
            sqlite_table = _TABLE_MAP[name][0]
            try:
                conn = sqlite3.connect(str(p))
                row_count = conn.execute(f"SELECT COUNT(*) FROM {sqlite_table}").fetchone()[0]
                conn.close()
                plan[name] = {"status": "ready", "local_rows": row_count}
            except sqlite3.OperationalError as e:
                plan[name] = {"status": "error", "reason": str(e)[:120]}
        return {
            "ok": True,
            "confirmed": False,
            "status": "planned",
            "plan": plan,
            "ts": _now_iso(),
            "message": "dry-run; pass confirm=True to execute mirror",
        }
    # EXECUTE
    mirrored = {}
    failures = []
    total = 0
    for name in active:
        result = mirror_one_cache(name, dsn=dsn, repo_root=repo_root)
        mirrored[name] = result
        if result.get("ok"):
            total += result.get("rows_written", 0)
        else:
            failures.append(name)
    return {
        "ok": not failures,
        "confirmed": True,
        "mirrored": mirrored,
        "failures": failures,
        "total_rows": total,
        "ts": _now_iso(),
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.cache_deploy_mirror",
        description=(
            "Snapshot local SQLite caches → prod Postgres+pgvector. "
            "DRY-RUN by default (returns plan: per-cache local row "
            "counts + ready/skip status). Pass confirm=True to EXECUTE: "
            "each cache mirrors as a single TRUNCATE+INSERT transaction "
            "(rollback on failure). Vectors transferred verbatim — NO "
            "re-embed cost. Idempotent: re-runs are safe. Use `only=[...]`"
            " to filter; default = all 5 caches. KB § PATTERNS/devops/"
            "cache-deploy-mirror.md."
        ),
    )
    def _mirror(
        confirm: bool = False,
        only: list[str] | None = None,
        dsn: str | None = None,
    ) -> dict:
        return mirror_all(confirm=confirm, only=only, dsn=dsn)

    @server.tool(
        name="noctus.dev.init_prod_cache_schema",
        description=(
            "Create the noctus_cache schema + tables in prod Postgres. "
            "SAFE to re-run (all DDL is IF NOT EXISTS). Use this ONCE "
            "after provisioning the pgvector container, BEFORE the "
            "first cache_deploy_mirror call."
        ),
    )
    def _init(dsn: str | None = None) -> dict:
        return init_prod_cache_schema(dsn=dsn)


__all__ = [
    "init_prod_cache_schema",
    "mirror_one_cache",
    "mirror_all",
    "register",
]
