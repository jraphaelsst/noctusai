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
from tools.noctus.dev.cache_backend import apply_locking_pragmas, cache_path, known_caches


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Per-cache table inventory ────────────────────────────────────────────────
# Local SQLite has its own per-cache schemas. We mirror ROWS into the
# corresponding Postgres tables (created by --init-prod-cache-schema).
# Each entry = (sqlite_table_name, pg_table_name_under_noctus_cache_schema).
_TABLE_MAP: dict[str, tuple[str, str]] = {
    "keeper-patterns":  ("keeper_patterns", "cache_keeper_patterns"),
    # Note: sqlite table names are SINGULAR (agent_context / auto_improvement),
    # matching auto_improvement.py:_SCHEMA + agent_context.py:_SCHEMA. The
    # previous plural form ("agent_contexts" / "auto_improvements") was a drift
    # caught in-flight on first real mirror execution (2026-05-26 evening,
    # Phase 2 of cache-pg-vps-bringup).
    "agent-context":    ("agent_context",   "cache_agent_context"),
    "auto-improvement": ("auto_improvement", "cache_auto_improvement"),
    "kb-embeddings":    ("kb_chunks",       "cache_kb_embeddings"),
    "code-embeddings":  ("code_chunks",     "cache_code_embeddings"),
    "memory-embeddings": ("memory_chunks",  "cache_memory_embeddings"),
    "corpus-embeddings": ("corpus_chunks",  "cache_corpus_embeddings"),
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

-- memory-embeddings: out-of-repo agent memory dir (feedback_*.md +
-- reference_*.md + project_*.md + MEMORY.md). Same vector(1536) shape.
CREATE TABLE IF NOT EXISTS noctus_cache.cache_memory_embeddings (
    id              SERIAL PRIMARY KEY,
    path            TEXT NOT NULL,
    chunk_idx       INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    embedding       vector(1536),
    source_sha      TEXT NOT NULL,
    cached_at       TEXT NOT NULL,
    UNIQUE(path, chunk_idx, source_sha)
);
CREATE INDEX IF NOT EXISTS idx_pg_memory_path ON noctus_cache.cache_memory_embeddings(path);

-- corpus-embeddings: heterogeneous in-repo corpus (CHANGELOG + templates +
-- .claude/agents FULL body + .claude/skills + PROJECT-HISTORY). source_type
-- column distinguishes (changelog/template/agent/skill/history).
CREATE TABLE IF NOT EXISTS noctus_cache.cache_corpus_embeddings (
    id              SERIAL PRIMARY KEY,
    source_type     TEXT NOT NULL,
    path            TEXT NOT NULL,
    chunk_idx       INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    embedding       vector(1536),
    source_sha      TEXT NOT NULL,
    cached_at       TEXT NOT NULL,
    UNIQUE(path, chunk_idx, source_sha)
);
CREATE INDEX IF NOT EXISTS idx_pg_corpus_path ON noctus_cache.cache_corpus_embeddings(path);
CREATE INDEX IF NOT EXISTS idx_pg_corpus_type ON noctus_cache.cache_corpus_embeddings(source_type);

-- agent-context: disaggregated rows-per-section (matches local agent_context.py
-- _SCHEMA). The earlier `bundle_json` shape was speculative — locally each
-- section gets its own row so prod queries are SQL-native (no JSON unpack).
CREATE TABLE IF NOT EXISTS noctus_cache.cache_agent_context (
    agent_name      TEXT NOT NULL,
    section_kind    TEXT NOT NULL,
    section_path    TEXT,
    section_value   TEXT NOT NULL,
    source_sha      TEXT NOT NULL,
    cached_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pg_agent_name ON noctus_cache.cache_agent_context(agent_name);
CREATE INDEX IF NOT EXISTS idx_pg_section_kind ON noctus_cache.cache_agent_context(section_kind);

-- auto-improvement: matches local auto_improvement.py _SCHEMA. The earlier
-- `source_sha` column was speculative — local cache uses `cached_at` only.
CREATE TABLE IF NOT EXISTS noctus_cache.cache_auto_improvement (
    id              SERIAL PRIMARY KEY,
    ts              TEXT NOT NULL,
    agent           TEXT,
    scope           TEXT NOT NULL,
    kind            TEXT NOT NULL,
    target          TEXT NOT NULL,
    description     TEXT NOT NULL,
    status          TEXT NOT NULL,
    source_ref      TEXT,
    cached_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pg_ai_target ON noctus_cache.cache_auto_improvement(target);
CREATE INDEX IF NOT EXISTS idx_pg_ai_status ON noctus_cache.cache_auto_improvement(status);
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
        # Split by ; and run each non-empty + non-comment-only statement;
        # psycopg2 doesn't execute multi-stmt strings reliably + raises
        # "empty query" on comment-only chunks (when a `-- comment` line
        # ends up between two `;` separators).
        def _has_sql(s: str) -> bool:
            for ln in s.splitlines():
                stripped = ln.strip()
                if stripped and not stripped.startswith("--"):
                    return True
            return False
        statements = [s.strip() for s in _PG_INIT_DDL.split(";") if s.strip() and _has_sql(s)]
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


def _mirror_chunks_with_json_embedding(
    local: sqlite3.Connection,
    pg_conn: Any,
    chunks_table: str,
    embeddings_json_table: str,
    pg_table: str,
    chunk_columns_local: list[str],
    pg_insert_cols: list[str],
    *,
    embedding_pg_col_idx: int,
    column_renames: dict[str, str] | None = None,
) -> int:
    """Mirror local SQLite `*_chunks` + sibling `*_embeddings_json` → prod PG.

    Local design (the real shape — surfaced in-flight 2026-05-26 evening):
      `kb_chunks` / `code_chunks` carry the chunk text + path + metadata.
      `kb_embeddings_json` / `code_embeddings_json` carry the JSON-serialized
      embedding keyed by `chunk_rowid → chunks.rowid_alias`.

    Prod design: one wide row per chunk with `embedding vector(1536)` column
    populated by JOIN. The JOIN happens here (local-side) and the resulting
    Python list[float] is sent to pgvector via psycopg2.

    Args:
      chunks_table: e.g. ``kb_chunks`` / ``code_chunks``.
      embeddings_json_table: e.g. ``kb_embeddings_json`` / ``code_embeddings_json``.
      pg_table: e.g. ``cache_kb_embeddings`` / ``cache_code_embeddings``.
      chunk_columns_local: SELECT cols from the chunks table (in INSERT order).
      pg_insert_cols: target PG column names (parallel to chunk_columns_local
        but the embedding entry is inserted via JOIN from embeddings_json_table).
      embedding_pg_col_idx: position of the ``embedding`` column in
        ``pg_insert_cols`` (so we know where to inject the JSON-parsed list).
      column_renames: optional ``{local_col: pg_col}`` for renames (e.g.
        ``{"symbol_name": "symbol"}``). Only affects the SELECT clause — the
        PG insert uses ``pg_insert_cols`` verbatim.
    """
    import json
    cur_pg = pg_conn.cursor()
    cur_pg.execute(f"TRUNCATE TABLE noctus_cache.{pg_table}")

    # Build SELECT clause: chunks columns + embedding JSON from the JOIN.
    renames = column_renames or {}
    chunk_select = ", ".join(
        f"c.{col}" + (f" AS {renames[col]}" if col in renames else "")
        for col in chunk_columns_local
    )
    select_sql = (
        f"SELECT {chunk_select}, e.embedding AS _embedding_json "
        f"FROM {chunks_table} c "
        f"JOIN {embeddings_json_table} e ON c.rowid_alias = e.chunk_rowid"
    )
    rows = local.execute(select_sql).fetchall()
    if not rows:
        cur_pg.close()
        return 0

    converted = []
    for row in rows:
        row_dict = dict(row) if isinstance(row, sqlite3.Row) else None
        if row_dict is None:
            row_list = list(row)
            embedding_json = row_list[-1]
            chunk_vals = row_list[:-1]
        else:
            embedding_json = row_dict.pop("_embedding_json")
            # Honor pg_insert_cols ORDER — but the SELECT order was set by
            # chunk_columns_local (+ renames applied via AS), so row_dict
            # keys match pg_insert_cols MINUS the embedding column.
            chunk_vals = [
                row_dict[renames.get(c, c)]
                for c in chunk_columns_local
            ]

        # Decode JSON embedding to list[float]. psycopg2 + pgvector accepts
        # a list[float] for a vector(N) column.
        try:
            embedding_list = json.loads(embedding_json) if embedding_json else None
        except (TypeError, ValueError):
            embedding_list = None

        # Splice the embedding into the row at the right position.
        full_row = list(chunk_vals)
        full_row.insert(embedding_pg_col_idx, embedding_list)
        converted.append(tuple(full_row))

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
    # WAL + busy_timeout — match the standard cache locking discipline.
    apply_locking_pragmas(local)
    try:
        with backend.connect(cache_name) as pg_conn:
            try:
                if cache_name == "keeper-patterns":
                    rows = _mirror_keeper_patterns(local, pg_conn)
                elif cache_name == "kb-embeddings":
                    # Local stores chunks + embedding-JSON in sibling tables;
                    # JOIN locally + parse JSON → pgvector list[float].
                    rows = _mirror_chunks_with_json_embedding(
                        local, pg_conn,
                        chunks_table="kb_chunks",
                        embeddings_json_table="kb_embeddings_json",
                        pg_table="cache_kb_embeddings",
                        chunk_columns_local=["path", "chunk_idx", "chunk_text", "source_sha", "cached_at"],
                        pg_insert_cols=["path", "chunk_idx", "chunk_text", "embedding", "source_sha", "cached_at"],
                        embedding_pg_col_idx=3,
                    )
                elif cache_name == "code-embeddings":
                    # Same JOIN pattern + symbol_name→symbol rename.
                    rows = _mirror_chunks_with_json_embedding(
                        local, pg_conn,
                        chunks_table="code_chunks",
                        embeddings_json_table="code_embeddings_json",
                        pg_table="cache_code_embeddings",
                        chunk_columns_local=["path", "symbol_name", "chunk_idx", "chunk_text", "source_sha", "cached_at"],
                        pg_insert_cols=["path", "symbol", "chunk_idx", "chunk_text", "embedding", "source_sha", "cached_at"],
                        embedding_pg_col_idx=4,
                        column_renames={"symbol_name": "symbol"},
                    )
                elif cache_name == "memory-embeddings":
                    # Mirrors kb-embeddings shape (no source_type column needed).
                    rows = _mirror_chunks_with_json_embedding(
                        local, pg_conn,
                        chunks_table="memory_chunks",
                        embeddings_json_table="memory_embeddings_json",
                        pg_table="cache_memory_embeddings",
                        chunk_columns_local=["path", "chunk_idx", "chunk_text", "source_sha", "cached_at"],
                        pg_insert_cols=["path", "chunk_idx", "chunk_text", "embedding", "source_sha", "cached_at"],
                        embedding_pg_col_idx=3,
                    )
                elif cache_name == "corpus-embeddings":
                    # Heterogeneous: source_type column comes first in PG schema.
                    rows = _mirror_chunks_with_json_embedding(
                        local, pg_conn,
                        chunks_table="corpus_chunks",
                        embeddings_json_table="corpus_embeddings_json",
                        pg_table="cache_corpus_embeddings",
                        chunk_columns_local=["source_type", "path", "chunk_idx", "chunk_text", "source_sha", "cached_at"],
                        pg_insert_cols=["source_type", "path", "chunk_idx", "chunk_text", "embedding", "source_sha", "cached_at"],
                        embedding_pg_col_idx=4,
                    )
                elif cache_name == "agent-context":
                    # Disaggregated rows-per-section (matches local schema).
                    rows = _mirror_simple_table(
                        local, pg_conn,
                        "agent_context", "cache_agent_context",
                        ["agent_name", "section_kind", "section_path",
                         "section_value", "source_sha", "cached_at"],
                    )
                elif cache_name == "auto-improvement":
                    # `cached_at` is the local truth; `source_sha` was speculative
                    # in the prior PG schema and is dropped per route X.
                    rows = _mirror_simple_table(
                        local, pg_conn,
                        "auto_improvement", "cache_auto_improvement",
                        ["ts", "agent", "scope", "kind", "target", "description",
                         "status", "source_ref", "cached_at"],
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
                # WAL + busy_timeout — match the standard cache locking discipline.
                apply_locking_pragmas(conn)
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


# ── Tier-2 PULL direction (remote pgvector → local SQLite) ──────────────────
# Inverse of mirror — used by:
#   - cache_backend.cache_path() on auto-pull-on-empty (fresh clone bootstrap).
#   - `noctus.dev.cache_pull` MCP tool / `python cli.py --cache-pull`.
# Schema knowledge is shared with the mirror direction via _TABLE_MAP.

_LOCAL_SCHEMA_INIT: dict[str, list[str]] = {
    # Per-cache CREATE TABLE statements for the LOCAL SQLite side. Each cache
    # module already owns its DDL — these are minimal-shape mirrors used ONLY
    # when bootstrapping a fresh sqlite from remote rows (so the destination
    # schema exists before INSERT). Compatible with the real modules' DDL
    # via `CREATE TABLE IF NOT EXISTS`.
    "keeper-patterns": [
        """CREATE TABLE IF NOT EXISTS keeper_patterns (
            pattern_id TEXT PRIMARY KEY,
            tier TEXT NOT NULL,
            description TEXT NOT NULL,
            test_locator TEXT,
            source_sha TEXT NOT NULL,
            cached_at TEXT NOT NULL
        )""",
    ],
    "agent-context": [
        """CREATE TABLE IF NOT EXISTS agent_context (
            agent_name TEXT NOT NULL,
            section TEXT NOT NULL,
            body TEXT NOT NULL,
            bundle_sha TEXT NOT NULL,
            cached_at TEXT NOT NULL,
            PRIMARY KEY (agent_name, section)
        )""",
    ],
    "auto-improvement": [
        """CREATE TABLE IF NOT EXISTS auto_improvement (
            event_id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            target TEXT NOT NULL,
            kind TEXT NOT NULL,
            stage TEXT,
            note TEXT,
            source_sha TEXT NOT NULL,
            cached_at TEXT NOT NULL
        )""",
    ],
    "kb-embeddings": [
        """CREATE TABLE IF NOT EXISTS kb_chunks (
            path TEXT NOT NULL,
            chunk_idx INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            source_sha TEXT NOT NULL,
            cached_at TEXT NOT NULL,
            PRIMARY KEY (path, chunk_idx)
        )""",
        """CREATE TABLE IF NOT EXISTS kb_embeddings_json (
            path TEXT NOT NULL,
            chunk_idx INTEGER NOT NULL,
            embedding_json TEXT NOT NULL,
            PRIMARY KEY (path, chunk_idx)
        )""",
    ],
    "code-embeddings": [
        """CREATE TABLE IF NOT EXISTS code_chunks (
            path TEXT NOT NULL,
            symbol_name TEXT NOT NULL,
            chunk_idx INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            source_sha TEXT NOT NULL,
            cached_at TEXT NOT NULL,
            PRIMARY KEY (path, symbol_name, chunk_idx)
        )""",
        """CREATE TABLE IF NOT EXISTS code_embeddings_json (
            path TEXT NOT NULL,
            symbol_name TEXT NOT NULL,
            chunk_idx INTEGER NOT NULL,
            embedding_json TEXT NOT NULL,
            PRIMARY KEY (path, symbol_name, chunk_idx)
        )""",
    ],
    "memory-embeddings": [
        """CREATE TABLE IF NOT EXISTS memory_chunks (
            path TEXT NOT NULL,
            chunk_idx INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            source_sha TEXT NOT NULL,
            cached_at TEXT NOT NULL,
            PRIMARY KEY (path, chunk_idx)
        )""",
        """CREATE TABLE IF NOT EXISTS memory_embeddings_json (
            path TEXT NOT NULL,
            chunk_idx INTEGER NOT NULL,
            embedding_json TEXT NOT NULL,
            PRIMARY KEY (path, chunk_idx)
        )""",
    ],
    "corpus-embeddings": [
        """CREATE TABLE IF NOT EXISTS corpus_chunks (
            source_type TEXT NOT NULL,
            path TEXT NOT NULL,
            chunk_idx INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            source_sha TEXT NOT NULL,
            cached_at TEXT NOT NULL,
            PRIMARY KEY (path, chunk_idx)
        )""",
        """CREATE TABLE IF NOT EXISTS corpus_embeddings_json (
            path TEXT NOT NULL,
            chunk_idx INTEGER NOT NULL,
            embedding_json TEXT NOT NULL,
            PRIMARY KEY (path, chunk_idx)
        )""",
    ],
}


def _init_local_schema(conn: sqlite3.Connection, cache_name: str) -> None:
    """Ensure the destination SQLite has the tables we're about to INSERT into."""
    ddls = _LOCAL_SCHEMA_INIT.get(cache_name, [])
    for ddl in ddls:
        conn.execute(ddl)
    conn.commit()


def _pull_simple_table(
    local: sqlite3.Connection, pg_conn: Any,
    sqlite_table: str, pg_table: str, columns: list[str],
) -> int:
    """Generic non-vector pull (agent-context, auto-improvement, keeper-patterns)."""
    cur = pg_conn.cursor()
    cols_sql = ", ".join(columns)
    cur.execute(f"SELECT {cols_sql} FROM noctus_cache.{pg_table}")
    rows = cur.fetchall()
    cur.close()
    if not rows:
        return 0
    placeholders = ", ".join(["?"] * len(columns))
    # Replace prior content (TRUNCATE-equivalent).
    local.execute(f"DELETE FROM {sqlite_table}")
    local.executemany(
        f"INSERT INTO {sqlite_table} ({cols_sql}) VALUES ({placeholders})",
        [tuple(r) for r in rows],
    )
    local.commit()
    return len(rows)


def _pull_chunks_with_embedding(
    local: sqlite3.Connection, pg_conn: Any,
    *, chunks_table: str, embeddings_json_table: str, pg_table: str,
    chunk_columns_local: list[str],
    pg_select_cols: list[str],
    embedding_pg_col_idx: int,
    column_renames: dict[str, str] | None = None,
) -> int:
    """Pull a chunk + embedding cache (kb / code / memory / corpus).

    Vectors come back as pgvector; we serialize to JSON for SQLite storage
    (mirrors the local cache's `<name>_embeddings_json` table).
    """
    import json
    cur = pg_conn.cursor()
    cols_sql = ", ".join(pg_select_cols)
    cur.execute(f"SELECT {cols_sql} FROM noctus_cache.{pg_table}")
    rows = cur.fetchall()
    cur.close()
    if not rows:
        return 0

    renames_rev: dict[str, str] = {v: k for k, v in (column_renames or {}).items()}

    local.execute(f"DELETE FROM {chunks_table}")
    local.execute(f"DELETE FROM {embeddings_json_table}")

    # Chunks insert (sans embedding).
    chunk_cols = [c for i, c in enumerate(pg_select_cols) if i != embedding_pg_col_idx]
    chunk_cols_local = [renames_rev.get(c, c) for c in chunk_cols]
    placeholders = ", ".join(["?"] * len(chunk_cols_local))
    chunk_rows = [
        tuple(r[i] for i in range(len(pg_select_cols)) if i != embedding_pg_col_idx)
        for r in rows
    ]
    local.executemany(
        f"INSERT INTO {chunks_table} ({', '.join(chunk_cols_local)}) "
        f"VALUES ({placeholders})",
        chunk_rows,
    )

    # Embeddings JSON insert.
    # PK columns for the json table = path + chunk_idx (+ optionally symbol_name for code).
    has_symbol = "symbol_name" in chunk_cols_local
    json_rows = []
    for r in rows:
        path = r[chunk_columns_local.index("path") if "path" in chunk_columns_local else 0]
        # Use position in chunk_columns_local — same column order as in SELECT, sans embedding.
        path_idx = chunk_columns_local.index("path")
        path = chunk_rows[rows.index(r)][path_idx] if False else None  # not used
        # Build via dict for clarity.
        rowdict = dict(zip(chunk_columns_local, chunk_rows[rows.index(r)]))
        emb = r[embedding_pg_col_idx]
        # pgvector returns either str ("[1.0, 2.0]") OR list. Normalize.
        if isinstance(emb, str):
            emb_list = json.loads(emb)
        else:
            emb_list = list(emb)
        if has_symbol:
            json_rows.append((rowdict["path"], rowdict["symbol_name"],
                              rowdict["chunk_idx"], json.dumps(emb_list)))
        else:
            json_rows.append((rowdict["path"], rowdict["chunk_idx"], json.dumps(emb_list)))
    if has_symbol:
        local.executemany(
            f"INSERT INTO {embeddings_json_table} (path, symbol_name, chunk_idx, embedding_json) "
            f"VALUES (?, ?, ?, ?)",
            json_rows,
        )
    else:
        local.executemany(
            f"INSERT INTO {embeddings_json_table} (path, chunk_idx, embedding_json) "
            f"VALUES (?, ?, ?)",
            json_rows,
        )
    local.commit()
    return len(rows)


def pull_one_cache(
    cache_name: str, *, dsn: str | None = None, repo_root: Path | None = None,
) -> dict[str, Any]:
    """Pull a single cache from prod Postgres → local SQLite. Inverse of mirror.

    Returns: `{ok, cache, rows_pulled, target_path, error?}`.
    """
    if cache_name not in _TABLE_MAP:
        return {"ok": False, "cache": cache_name,
                "error": f"unknown cache; valid: {sorted(_TABLE_MAP)}"}
    try:
        from tools.noctus.dev.cache_backend_postgres import PostgresCacheBackend
    except ImportError as e:
        return {"ok": False, "cache": cache_name,
                "error": f"PostgresCacheBackend unavailable: {e}"}
    sqlite_target = cache_path(cache_name, repo_root)
    sqlite_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        backend = PostgresCacheBackend(dsn=dsn) if dsn else PostgresCacheBackend()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "cache": cache_name,
                "error": f"postgres backend init failed: {e}"}

    local = sqlite3.connect(str(sqlite_target))
    local.row_factory = sqlite3.Row
    # WAL + busy_timeout — match the standard cache locking discipline.
    apply_locking_pragmas(local)
    _init_local_schema(local, cache_name)

    try:
        with backend.connect(cache_name) as pg_conn:
            if cache_name == "keeper-patterns":
                rows = _pull_simple_table(local, pg_conn, "keeper_patterns",
                    "cache_keeper_patterns",
                    ["pattern_id", "tier", "description", "test_locator",
                     "source_sha", "cached_at"])
            elif cache_name == "agent-context":
                rows = _pull_simple_table(local, pg_conn, "agent_context",
                    "cache_agent_context",
                    ["agent_name", "section", "body", "bundle_sha", "cached_at"])
            elif cache_name == "auto-improvement":
                rows = _pull_simple_table(local, pg_conn, "auto_improvement",
                    "cache_auto_improvement",
                    ["event_id", "ts", "target", "kind", "stage", "note",
                     "source_sha", "cached_at"])
            elif cache_name == "kb-embeddings":
                rows = _pull_chunks_with_embedding(local, pg_conn,
                    chunks_table="kb_chunks",
                    embeddings_json_table="kb_embeddings_json",
                    pg_table="cache_kb_embeddings",
                    chunk_columns_local=["path", "chunk_idx", "chunk_text",
                                         "source_sha", "cached_at"],
                    pg_select_cols=["path", "chunk_idx", "chunk_text",
                                    "embedding", "source_sha", "cached_at"],
                    embedding_pg_col_idx=3)
            elif cache_name == "code-embeddings":
                rows = _pull_chunks_with_embedding(local, pg_conn,
                    chunks_table="code_chunks",
                    embeddings_json_table="code_embeddings_json",
                    pg_table="cache_code_embeddings",
                    chunk_columns_local=["path", "symbol_name", "chunk_idx",
                                         "chunk_text", "source_sha", "cached_at"],
                    pg_select_cols=["path", "symbol", "chunk_idx", "chunk_text",
                                    "embedding", "source_sha", "cached_at"],
                    embedding_pg_col_idx=4,
                    column_renames={"symbol_name": "symbol"})
            elif cache_name == "memory-embeddings":
                rows = _pull_chunks_with_embedding(local, pg_conn,
                    chunks_table="memory_chunks",
                    embeddings_json_table="memory_embeddings_json",
                    pg_table="cache_memory_embeddings",
                    chunk_columns_local=["path", "chunk_idx", "chunk_text",
                                         "source_sha", "cached_at"],
                    pg_select_cols=["path", "chunk_idx", "chunk_text",
                                    "embedding", "source_sha", "cached_at"],
                    embedding_pg_col_idx=3)
            elif cache_name == "corpus-embeddings":
                rows = _pull_chunks_with_embedding(local, pg_conn,
                    chunks_table="corpus_chunks",
                    embeddings_json_table="corpus_embeddings_json",
                    pg_table="cache_corpus_embeddings",
                    chunk_columns_local=["source_type", "path", "chunk_idx",
                                         "chunk_text", "source_sha", "cached_at"],
                    pg_select_cols=["source_type", "path", "chunk_idx",
                                    "chunk_text", "embedding", "source_sha",
                                    "cached_at"],
                    embedding_pg_col_idx=4)
            elif cache_name == "noc-graph":
                # noc-graph schema is bespoke; full pull is feasible but the
                # cache is cheaply rebuilt from local sources — skip for now,
                # let the standard refresh repopulate.
                rows = 0
            else:
                rows = 0
    except Exception as e:  # noqa: BLE001
        local.close()
        return {"ok": False, "cache": cache_name, "error": str(e)[:200]}
    finally:
        try:
            local.close()
        except Exception:
            pass

    return {
        "ok": True,
        "cache": cache_name,
        "rows_pulled": rows,
        "target_path": str(sqlite_target),
    }


def pull_all(
    *, only: list[str] | None = None, dsn: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Pull every cache (or `only=[...]`) from remote → local. Best-effort.

    Per-cache failures are surfaced individually; the function returns
    `ok=False` if ANY cache failed but does not roll others back.
    """
    targets = list(only) if only else list(_TABLE_MAP.keys())
    results: dict[str, dict] = {}
    failures: list[str] = []
    total = 0
    for name in targets:
        r = pull_one_cache(name, dsn=dsn, repo_root=repo_root)
        results[name] = r
        if r.get("ok"):
            total += r.get("rows_pulled", 0)
        else:
            failures.append(name)
    return {
        "ok": not failures,
        "pulled": results,
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
            " to filter; default = all caches. KB § PATTERNS/devops/"
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
        name="noctus.dev.cache_pull",
        description=(
            "Pull prod Postgres+pgvector cache → local SQLite. Inverse of "
            "cache_deploy_mirror. Used for fresh-machine bootstrap (no "
            "OpenAI re-embed required). Auto-invoked by cache_backend on "
            "missing local SQLite + opt-out via NOCTUS_DISABLE_AUTO_CACHE_PULL=1. "
            "Pass only=[...] to filter; default = all caches. Vectors "
            "transferred verbatim. KB § PATTERNS/common/cache-portable-architecture.md."
        ),
    )
    def _pull(
        only: list[str] | None = None,
        dsn: str | None = None,
    ) -> dict:
        return pull_all(only=only, dsn=dsn)

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
    "pull_one_cache",
    "pull_all",
    "register",
]
