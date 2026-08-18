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

🔴 2026-08-14 fix — cache-mirror-join-drift
    The 4 chunk-and-embedding caches (kb/code/memory/corpus) each carry a
    chunk in ONE of two sibling tables — `*_vec` (sqlite-vec) or
    `*_embeddings_json` (plain-table fallback) — depending on which
    environment last refreshed it (`sqlite-vec` is an opportunistically
    pip-installed, UNPINNED dependency present in `mcp/noctusai/.venv` but
    absent from every requirements.txt). This module used to read ONLY the
    JSON sibling via an INNER JOIN, silently shipping 30-70% of each
    corpus while reporting `ok: true`. It now reads BOTH sibling tables
    (`_mirror_chunks_with_embedding`) and REFUSES (rolls back, `ok=False`,
    named delta) on any shortfall instead of shipping a partial cache —
    the "Verifies" contract above is now actually enforced, not just
    documented. `noctus.dev.repair_embedding_cache_drift` is the
    companion LOCAL-only, lossless (zero re-embed) repair for caches that
    were already split before this fix landed. See
    KB § PATTERNS/devops/cache-deploy-mirror.md.

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
from tools.noctus.dev import _embedding_corpus as _ec


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

# The 4 chunk+embedding caches carry a SECOND sibling table — either
# `*_vec` (sqlite-vec virtual table) or `*_embeddings_json` (plain-table
# fallback) — depending on which engine wrote a given row (see
# `_embedding_corpus.delete_embedding_rows` for why a single cache can
# have rows split across BOTH). The mirror must read both; this maps
# cache_name -> (vec_table, json_table).
_EMBEDDING_SIBLING_TABLES: dict[str, tuple[str, str]] = {
    "kb-embeddings":     ("kb_vec",     "kb_embeddings_json"),
    "code-embeddings":   ("code_vec",   "code_embeddings_json"),
    "memory-embeddings": ("memory_vec", "memory_embeddings_json"),
    "corpus-embeddings": ("corpus_vec", "corpus_embeddings_json"),
}


# ── Canonical per-cache column contract — ONE definition, BOTH directions ────
# Before 2026-08-18 the mirror direction carried these column lists inline at
# each call site and the PULL direction carried a SECOND, hand-authored copy
# (`_LOCAL_SCHEMA_INIT` + per-cache literal lists in `pull_one_cache`). The
# pull copy matched neither the real local SQLite DDL nor `_PG_INIT_DDL` — it
# had been written from the shape the author expected rather than the shape
# that exists, and nothing ever executed it (no test, and the only production
# caller is fresh-clone auto-pull-on-empty). All seven caches were affected;
# `code-embeddings` merely failed LOUDLY (`NOT NULL constraint failed:
# code_chunks.kind`) because a real table already existed to conflict with.
# On a genuinely fresh clone the invented DDL would have been CREATEd and the
# pull would have reported `ok: true` over a cache no reader can query.
#
# The fix is structural, not a column patch: one spec, consumed by mirror AND
# pull, with `test_cache_pull.py::TestSchemaParity` asserting the spec against
# the two real schemas (local `_ec.init_schema` / each module's `_SCHEMA`, and
# `_PG_INIT_DDL`). A future column added to one side and not the other fails
# that test instead of silently producing an unreadable cache.
# KB § PATTERNS/devops/cache-deploy-mirror.md.

# Non-vector caches: identical column list on both sides (no renames).
_SIMPLE_CACHE_SPEC: dict[str, dict[str, Any]] = {
    "keeper-patterns": {
        "sqlite_table": "keeper_patterns",
        "pg_table": "cache_keeper_patterns",
        "columns": [
            "keeper_name", "pattern_kind", "pattern_value", "severity",
            "remediation", "source_file", "source_line", "fixture_example",
            "scope", "cached_at",
        ],
    },
    "agent-context": {
        "sqlite_table": "agent_context",
        "pg_table": "cache_agent_context",
        "columns": [
            "agent_name", "section_kind", "section_path", "section_value",
            "source_sha", "cached_at",
        ],
    },
    "auto-improvement": {
        # `rowid_alias` is a local AUTOINCREMENT surrogate and is deliberately
        # NOT transferred — prod has its own SERIAL `id`. Re-pulling therefore
        # renumbers locally, which is fine: nothing joins on it.
        "sqlite_table": "auto_improvement",
        "pg_table": "cache_auto_improvement",
        "columns": [
            "ts", "agent", "scope", "kind", "target", "description",
            "status", "source_ref", "cached_at",
        ],
    },
}

# Chunk+embedding caches. `chunk_columns_local` are the LOCAL chunks-table
# columns in transfer order (excluding `rowid_alias`, which is the local
# surrogate the two sibling embedding tables key on). `pg_columns` is the same
# tuple with `embedding` spliced in at `embedding_pg_col_idx` and any local→pg
# rename applied (only `symbol_name` → `symbol`, for historical reasons).
# `extra_columns` is passed verbatim to `_ec.init_schema` so the pull side
# bootstraps the SAME DDL the refresh path owns.
_EMBEDDING_CACHE_SPEC: dict[str, dict[str, Any]] = {
    "kb-embeddings": {
        "chunks_table": "kb_chunks",
        "vec_table": "kb_vec",
        "json_table": "kb_embeddings_json",
        "pg_table": "cache_kb_embeddings",
        "extra_columns": {},
        "chunk_columns_local": [
            "path", "chunk_idx", "chunk_text", "source_sha", "cached_at",
        ],
        "pg_columns": [
            "path", "chunk_idx", "chunk_text", "embedding", "source_sha",
            "cached_at",
        ],
        "embedding_pg_col_idx": 3,
    },
    "code-embeddings": {
        "chunks_table": "code_chunks",
        "vec_table": "code_vec",
        "json_table": "code_embeddings_json",
        "pg_table": "cache_code_embeddings",
        "extra_columns": {"symbol_name": "TEXT NOT NULL", "kind": "TEXT NOT NULL"},
        "chunk_columns_local": [
            "path", "symbol_name", "chunk_idx", "kind", "chunk_text",
            "source_sha", "cached_at",
        ],
        "pg_columns": [
            "path", "symbol", "chunk_idx", "kind", "chunk_text", "embedding",
            "source_sha", "cached_at",
        ],
        "embedding_pg_col_idx": 5,
        # `kind` is NOT NULL locally but was absent from the PG table until
        # 2026-08-18, so rows mirrored before then read back NULL. We cannot
        # reconstruct the real value (it comes from the AST walk), so a pulled
        # legacy row gets this sentinel and the pull result REPORTS the count —
        # never a silent substitution. `COALESCE(kind,'') != 'organ'` (the only
        # consumer, `_ec` organ filtering) treats it correctly. One mirror run
        # from a healthy local cache makes the column real and this stops firing.
        "legacy_null_backfill": {"kind": "unknown"},
    },
    "memory-embeddings": {
        "chunks_table": "memory_chunks",
        "vec_table": "memory_vec",
        "json_table": "memory_embeddings_json",
        "pg_table": "cache_memory_embeddings",
        "extra_columns": {},
        "chunk_columns_local": [
            "path", "chunk_idx", "chunk_text", "source_sha", "cached_at",
        ],
        "pg_columns": [
            "path", "chunk_idx", "chunk_text", "embedding", "source_sha",
            "cached_at",
        ],
        "embedding_pg_col_idx": 3,
    },
    "corpus-embeddings": {
        "chunks_table": "corpus_chunks",
        "vec_table": "corpus_vec",
        "json_table": "corpus_embeddings_json",
        "pg_table": "cache_corpus_embeddings",
        "extra_columns": {"source_type": "TEXT NOT NULL"},
        "chunk_columns_local": [
            "source_type", "path", "chunk_idx", "chunk_text", "source_sha",
            "cached_at",
        ],
        "pg_columns": [
            "source_type", "path", "chunk_idx", "chunk_text", "embedding",
            "source_sha", "cached_at",
        ],
        "embedding_pg_col_idx": 4,
    },
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
    -- 'function' | 'async_function' | 'class' | 'file'. NULLABLE on purpose:
    -- the column was added 2026-08-18 and rows mirrored before then have no
    -- value to backfill from. Local `code_chunks.kind` is NOT NULL, so
    -- `pull_one_cache` substitutes a reported sentinel for legacy NULLs
    -- rather than inventing an AST classification. See _EMBEDDING_CACHE_SPEC
    -- ["code-embeddings"]["legacy_null_backfill"].
    kind            TEXT,
    chunk_text      TEXT NOT NULL,
    embedding       vector(1536),
    source_sha      TEXT NOT NULL,
    cached_at       TEXT NOT NULL,
    UNIQUE(path, symbol, chunk_idx, source_sha)
);
CREATE INDEX IF NOT EXISTS idx_pg_code_path ON noctus_cache.cache_code_embeddings(path);
-- Migration leg for an ALREADY-provisioned prod (the CREATE above is a no-op
-- there, so it can never add the column). Idempotent; PG 9.6+.
ALTER TABLE noctus_cache.cache_code_embeddings ADD COLUMN IF NOT EXISTS kind TEXT;

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


def _mirror_keeper_patterns(local: sqlite3.Connection, pg_conn: Any) -> dict[str, int]:
    """Returns `{rows_written, source_total}` — the uniform shape every
    `_mirror_*` helper returns so `mirror_one_cache` can generically verify
    the write matched what was read (KB § PATTERNS/devops/
    cache-deploy-mirror.md — no-silent-shortfall leg of the 2026-08-14 fix).
    For this cache `rows_written == source_total` by construction (no join,
    no filter — everything read gets written)."""
    cur_pg = pg_conn.cursor()
    cur_pg.execute("TRUNCATE TABLE noctus_cache.cache_keeper_patterns")
    cols = _SIMPLE_CACHE_SPEC["keeper-patterns"]["columns"]
    cols_sql = ", ".join(cols)
    rows = list(local.execute(
        f"SELECT {cols_sql} FROM keeper_patterns"
    ).fetchall())
    if rows:
        placeholders = ", ".join(["%s"] * len(cols))
        cur_pg.executemany(
            f"INSERT INTO noctus_cache.cache_keeper_patterns ({cols_sql}) "
            f"VALUES ({placeholders})",
            [tuple(r) for r in rows]
        )
    cur_pg.close()
    return {"rows_written": len(rows), "source_total": len(rows)}


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


def _mirror_chunks_with_embedding(
    local: sqlite3.Connection,
    pg_conn: Any,
    chunks_table: str,
    vec_table: str,
    embeddings_json_table: str,
    pg_table: str,
    chunk_columns_local: list[str],
    pg_insert_cols: list[str],
    *,
    embedding_pg_col_idx: int,
) -> dict[str, Any]:
    """Mirror local SQLite `*_chunks` + BOTH sibling embedding tables → prod PG.

    🔴 2026-08-14 fix (cache-mirror-join-drift): a chunk's embedding lives in
    EXACTLY ONE of two sibling tables — `*_vec` (sqlite-vec virtual table,
    written when the refreshing process has the extension loaded) or
    `*_embeddings_json` (plain-table fallback, written when it doesn't).
    `sqlite-vec` is an opportunistically pip-installed, UNPINNED dependency
    (absent from every requirements.txt in this repo) present in
    `mcp/noctusai/.venv` but not the repo-root `venv` / a fresh CI
    checkout — so the SAME cache file, refreshed across environments over
    its lifetime, ends up with its corpus SPLIT across both tables. The
    prior version of this function read ONLY `embeddings_json_table` via an
    INNER JOIN, silently dropping every chunk whose embedding lived in
    `vec_table` instead — verified empirically: kb/code/memory/corpus each
    had 30-70% of their corpus mirrored, the rest silently absent, while
    `mirror_all` still reported `ok: true`.

    This reads BOTH sibling tables in Python (not SQL JOIN — a vec0 virtual
    table can only be referenced when the sqlite-vec extension is loaded on
    THIS connection; `mirror_one_cache` opens via `_ec.connect_cache` so it
    is, when available) and reports ANY chunk with no embedding in EITHER
    side as a named shortfall in the return value — never silently dropped,
    never shipped as NULL (KB § 01-PHILOSOPHY.md — no silent errors).

    Args:
      chunks_table / vec_table / embeddings_json_table: sibling table names.
      pg_table: e.g. ``cache_kb_embeddings``.
      chunk_columns_local: chunk-table columns to SELECT, in the SAME
        relative order as `pg_insert_cols` minus the embedding slot (a
        rename, e.g. `symbol_name` -> `symbol`, only affects the TARGET
        column name in `pg_insert_cols` — the local SELECT always uses the
        real local column name; ordering does the rest).
      embedding_pg_col_idx: position of the ``embedding`` column in
        ``pg_insert_cols`` (so we know where to inject the vector).

    Returns `{rows_written, chunks_total, missing_embedding_count,
    missing_embedding_sample}` — deliberately NOT a bare int, so the caller
    can refuse to report success on a shortfall.
    """
    import json
    import struct

    cur_pg = pg_conn.cursor()
    cur_pg.execute(f"TRUNCATE TABLE noctus_cache.{pg_table}")

    # Sibling-table embedding lookups, keyed by `chunks_table.rowid_alias`.
    vec_by_rowid: dict[int, list[float]] = {}
    try:
        for rowid, blob in local.execute(f"SELECT rowid, embedding FROM {vec_table}"):
            if blob is None:
                continue
            n = len(blob) // 4
            vec_by_rowid[rowid] = list(struct.unpack(f"<{n}f", blob))
    except sqlite3.OperationalError:
        # vec0 module not loaded on this connection (HAS_VEC False here), or
        # the table doesn't exist yet — graceful: fall through to json-only.
        pass

    json_by_rowid: dict[int, list[float]] = {}
    try:
        for chunk_rowid, embedding_json in local.execute(
            f"SELECT chunk_rowid, embedding FROM {embeddings_json_table}"
        ):
            if not embedding_json:
                continue
            try:
                json_by_rowid[chunk_rowid] = json.loads(embedding_json)
            except (TypeError, ValueError):
                continue
    except sqlite3.OperationalError:
        pass  # table never created (a purely-vec-since-birth environment).

    cols_sql = ", ".join(["rowid_alias"] + chunk_columns_local)
    rows = local.execute(f"SELECT {cols_sql} FROM {chunks_table}").fetchall()

    path_idx = chunk_columns_local.index("path") if "path" in chunk_columns_local else None
    converted: list[tuple] = []
    missing: list[dict] = []
    for row in rows:
        rowid = row[0]
        chunk_vals = list(row[1:])
        embedding_list = vec_by_rowid.get(rowid, json_by_rowid.get(rowid))
        if embedding_list is None:
            missing.append({
                "rowid_alias": rowid,
                "path": chunk_vals[path_idx] if path_idx is not None else None,
            })
            continue
        full_row = list(chunk_vals)
        full_row.insert(embedding_pg_col_idx, embedding_list)
        converted.append(tuple(full_row))

    if converted:
        placeholders = ", ".join(["%s"] * len(pg_insert_cols))
        cur_pg.executemany(
            f"INSERT INTO noctus_cache.{pg_table} ({', '.join(pg_insert_cols)}) "
            f"VALUES ({placeholders})",
            converted,
        )
    cur_pg.close()
    return {
        "rows_written": len(converted),
        "chunks_total": len(rows),
        "missing_embedding_count": len(missing),
        "missing_embedding_sample": missing[:10],
    }


def _mirror_simple_table(
    local: sqlite3.Connection,
    pg_conn: Any,
    sqlite_table: str,
    pg_table: str,
    columns: list[str],
) -> dict[str, int]:
    """Generic non-vector table mirror (agent-context, auto-improvement).

    Returns `{rows_written, source_total}` — see `_mirror_keeper_patterns`."""
    cur_pg = pg_conn.cursor()
    cur_pg.execute(f"TRUNCATE TABLE noctus_cache.{pg_table}")
    cols_sql = ", ".join(columns)
    rows = local.execute(f"SELECT {cols_sql} FROM {sqlite_table}").fetchall()
    if rows:
        placeholders = ", ".join(["%s"] * len(columns))
        cur_pg.executemany(
            f"INSERT INTO noctus_cache.{pg_table} ({cols_sql}) VALUES ({placeholders})",
            [tuple(r) for r in rows]
        )
    cur_pg.close()
    return {"rows_written": len(rows), "source_total": len(rows)}


def mirror_one_cache(
    cache_name: str,
    *,
    dsn: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Mirror a single cache from local SQLite → prod Postgres.

    Verifies: `rows_written` MUST equal `source_total` (the local row count
    the mirror INTENDED to ship) or the transaction is rolled back and the
    result is `ok=False` with a named delta — never `ok=True` on a partial
    ship (2026-08-14 fix; this is what the module docstring already
    promised — "row counts per cache match local ±0%... mismatch =
    surfaced" — but the implementation never actually checked it before
    this fix). `source_total` for the 4 chunk+embedding caches is
    `chunks_total` (every chunk that exists, regardless of which sibling
    table its embedding lives in); for the other 3 it's the source table's
    row count.

    Returns: `{ok, cache, rows_written, source_total, target, error?}`.
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
    # `_ec.connect_cache` = WAL + busy_timeout (the standard locking
    # discipline `apply_locking_pragmas` already gave us) PLUS loads the
    # sqlite-vec extension when available — required to read a `*_vec`
    # sibling table at all (a vec0 virtual table errors "no such module:
    # vec0" on a plain `sqlite3.connect()`). Safe for the 3 non-vector
    # caches too (loading the extension is a no-op if nothing references it).
    local = _ec.connect_cache(sqlite_path)
    try:
        with backend.connect(cache_name) as pg_conn:
            try:
                if cache_name == "keeper-patterns":
                    result = _mirror_keeper_patterns(local, pg_conn)
                elif cache_name in _EMBEDDING_CACHE_SPEC:
                    # Column lists come from the shared spec — the SAME dict
                    # `pull_one_cache` reads, so the two directions cannot
                    # drift apart again (they did, silently, until 2026-08-18).
                    # The symbol_name -> symbol rename is TARGET-only; see
                    # `_mirror_chunks_with_embedding`'s docstring.
                    spec = _EMBEDDING_CACHE_SPEC[cache_name]
                    result = _mirror_chunks_with_embedding(
                        local, pg_conn,
                        chunks_table=spec["chunks_table"],
                        vec_table=spec["vec_table"],
                        embeddings_json_table=spec["json_table"],
                        pg_table=spec["pg_table"],
                        chunk_columns_local=spec["chunk_columns_local"],
                        pg_insert_cols=spec["pg_columns"],
                        embedding_pg_col_idx=spec["embedding_pg_col_idx"],
                    )
                    result["source_total"] = result.pop("chunks_total")
                elif cache_name == "agent-context":
                    # Disaggregated rows-per-section (matches local schema).
                    _spec = _SIMPLE_CACHE_SPEC["agent-context"]
                    result = _mirror_simple_table(
                        local, pg_conn,
                        _spec["sqlite_table"], _spec["pg_table"],
                        _spec["columns"],
                    )
                elif cache_name == "auto-improvement":
                    # `cached_at` is the local truth; `source_sha` was speculative
                    # in the prior PG schema and is dropped per route X.
                    _spec = _SIMPLE_CACHE_SPEC["auto-improvement"]
                    result = _mirror_simple_table(
                        local, pg_conn,
                        _spec["sqlite_table"], _spec["pg_table"],
                        _spec["columns"],
                    )
                else:
                    result = {"rows_written": 0, "source_total": 0}

                rows_written = result["rows_written"]
                source_total = result["source_total"]
                if rows_written != source_total:
                    # No-silent-shortfall gate: refuse to report success (or
                    # to leave a partial TRUNCATE+INSERT sitting in prod) on
                    # a mismatch. Atomic-per-cache contract preserved.
                    pg_conn.rollback()
                    delta = source_total - rows_written
                    missing_sample = result.get("missing_embedding_sample")
                    return {
                        "ok": False,
                        "cache": cache_name,
                        "error": (
                            f"mirror-row-count-mismatch: wrote {rows_written} of "
                            f"{source_total} local rows (delta={delta}) — refusing "
                            f"to report success on a shortfall (rolled back)"
                        ),
                        "rows_written": rows_written,
                        "source_total": source_total,
                        "missing_embedding_count": result.get("missing_embedding_count"),
                        "missing_embedding_sample": missing_sample,
                    }

                pg_conn.commit()
            except Exception as e:  # noqa: BLE001
                pg_conn.rollback()
                msg = f"mirror failed (rolled back): {str(e)[:200]}"
                # A column the local side has and prod does not means the PG
                # schema predates a spec change. `CREATE TABLE IF NOT EXISTS`
                # cannot add a column to a provisioned instance — the ALTER
                # legs in `_PG_INIT_DDL` do, and they only run via
                # `init_prod_cache_schema`. Say so instead of leaving the
                # operator with a bare psycopg2 error.
                if "does not exist" in str(e) and "column" in str(e):
                    msg += (
                        " — prod schema is behind the mirror spec. Run "
                        "noctus.dev.init_prod_cache_schema (safe to re-run; it "
                        "carries the ADD COLUMN IF NOT EXISTS legs) and retry."
                    )
                return {
                    "ok": False,
                    "cache": cache_name,
                    "error": msg,
                }
        return {
            "ok": True,
            "cache": cache_name,
            "rows_written": rows_written,
            "source_total": source_total,
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


# ── LOCAL-ONLY repair (2026-08-14 cache-mirror-join-drift) ──────────────────


def repair_embedding_cache_drift(
    only: list[str] | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """One-time LOSSLESS repair for the 2026-08-14 cache-mirror-join-drift
    incident, across every local embedding cache (or `only=[...]`).

    LOCAL-ONLY — never opens a Postgres connection, never touches prod.
    Delegates to `_ec.backfill_cross_engine_embeddings` per cache: copies
    every embedding that exists ONLY in the JSON-fallback sibling table
    across into the sqlite-vec table (same vector, zero re-embed / zero
    OpenAI spend) and prunes rows in either sibling table whose chunk no
    longer exists. Idempotent — safe to re-run.

    Requires the sqlite-vec extension loaded in THIS process (run it from
    `mcp/noctusai/.venv`, e.g. via the MCP server) — a no-vec environment
    returns `status='skipped-no-vec'` per cache (a no-op, not an error).

    Run this BEFORE the next `noctus.dev.cache_deploy_mirror confirm=True`
    so prod receives the FULL corpus, not the join-fixed-but-still-split
    local state. Returns `{ok, results: {cache_name: {...}}}`.
    """
    active = list(only) if only else list(_EMBEDDING_SIBLING_TABLES.keys())
    invalid = [c for c in active if c not in _EMBEDDING_SIBLING_TABLES]
    if invalid:
        return {
            "ok": False,
            "error": f"unknown embedding cache(s): {invalid}; valid: {sorted(_EMBEDDING_SIBLING_TABLES)}",
        }
    results: dict[str, Any] = {}
    for name in active:
        p = cache_path(name, repo_root)
        if not p.exists():
            results[name] = {"ok": False, "error": f"local SQLite cache missing: {p}"}
            continue
        chunks_table = _TABLE_MAP[name][0]
        vec_table, json_table = _EMBEDDING_SIBLING_TABLES[name]
        conn = _ec.connect_cache(p)
        try:
            _ec.init_schema(conn, chunks_table, vec_table, json_table)
            results[name] = _ec.backfill_cross_engine_embeddings(
                conn, chunks_table=chunks_table, vec_table=vec_table,
                json_table=json_table,
            )
        finally:
            conn.close()
    return {"ok": all(r.get("ok") for r in results.values()), "results": results}


# ── Tier-2 PULL direction (remote pgvector → local SQLite) ──────────────────
# Inverse of mirror — used by:
#   - cache_backend.cache_path() on auto-pull-on-empty (fresh clone bootstrap).
#   - `noctus.dev.cache_pull` MCP tool / `python cli.py --cache-pull`.
# Schema knowledge is shared with the mirror direction via _TABLE_MAP.

def _init_local_schema(conn: sqlite3.Connection, cache_name: str) -> None:
    """Create the destination tables using each cache module's OWN canonical DDL.

    🔴 2026-08-18: this used to execute `_LOCAL_SCHEMA_INIT`, a hand-authored
    "minimal-shape mirror" of the seven local schemas. Every one of the seven
    was wrong — not subtly (a missing index) but structurally: the embedding
    caches key their embedding siblings on `<chunks>.rowid_alias`, and the
    invented DDL had no `rowid_alias` at all, giving the json sibling a
    `(path, symbol_name, chunk_idx)` composite key it does not have and never
    creating the `*_vec` sibling that every vector read goes through. The
    non-vector three named columns (`pattern_id`, `tier`, `bundle_sha`, ...)
    that exist in no schema on either side.

    A duplicated schema is the bug; deleting the duplicate is the fix. Each
    cache module already owns its DDL and exports it, so we call that instead:
    `_ec.init_schema` for the four chunk+embedding caches (the same entrypoint
    the refresh path uses, `extra_columns` and all), and the module-level
    `_SCHEMA` constant for the other three. There is now exactly one
    definition of each local schema in the repo.
    """
    if cache_name in _EMBEDDING_CACHE_SPEC:
        spec = _EMBEDDING_CACHE_SPEC[cache_name]
        _ec.init_schema(
            conn,
            spec["chunks_table"],
            spec["vec_table"],
            spec["json_table"],
            extra_columns=spec["extra_columns"] or None,
        )
        return

    # Local imports: these modules import cache_backend, which imports this
    # module for auto-pull-on-empty — a module-scope import would cycle.
    if cache_name == "keeper-patterns":
        from tools.noctus.dev.keeper_pattern_cache import _SCHEMA as ddl
    elif cache_name == "agent-context":
        from tools.noctus.dev.agent_context_cache import _SCHEMA as ddl
    elif cache_name == "auto-improvement":
        from tools.noctus.dev.auto_improvement import _SCHEMA as ddl
    else:
        return  # noc-graph: bespoke, rebuilt locally rather than pulled.
    conn.executescript(ddl)
    conn.commit()


def _pull_simple_table(
    local: sqlite3.Connection, pg_conn: Any,
    sqlite_table: str, pg_table: str, columns: list[str],
) -> int:
    """Generic non-vector pull (keeper-patterns, agent-context, auto-improvement).

    Column list comes from `_SIMPLE_CACHE_SPEC` — the same list the mirror
    direction writes with, so a schema change lands on both sides at once.
    """
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
    local: sqlite3.Connection, pg_conn: Any, *, spec: dict[str, Any],
) -> dict[str, Any]:
    """Pull a chunk+embedding cache (kb / code / memory / corpus) — real shape.

    The local layout this writes (and that the prior version did not):

      `<name>_chunks`             rowid_alias INTEGER PK AUTOINCREMENT + cols
      `<name>_embeddings_json`    chunk_rowid PK -> chunks.rowid_alias
      `<name>_vec`                vec0 virtual table, rowid = chunks.rowid_alias

    So the chunk INSERT has to happen FIRST, one row at a time, because the
    rowid it allocates is the key both embedding siblings need. Batch
    `executemany` cannot give us that mapping.

    Both siblings are written when sqlite-vec is available here, not just the
    "current engine" one: `_ec.delete_embedding_rows`'s docstring records why
    a half-populated pair strands orphans the other environment cannot clean
    (the 2026-08-14 cache-mirror-join-drift root cause). A pulled cache should
    not be born in the state that incident produced. Without the extension we
    write the json sibling only, and `repair_embedding_cache_drift` /
    `_ec.backfill_cross_engine_embeddings` can promote it later — losslessly,
    no re-embed.

    Returns `{rows_pulled, vec_rows, json_rows, null_embedding_count,
    legacy_null_backfilled}` — a shortfall is reported, never swallowed.
    """
    chunks_table = spec["chunks_table"]
    vec_table = spec["vec_table"]
    json_table = spec["json_table"]
    pg_cols = spec["pg_columns"]
    emb_idx = spec["embedding_pg_col_idx"]
    local_cols = spec["chunk_columns_local"]
    backfill: dict[str, Any] = spec.get("legacy_null_backfill", {})

    cur = pg_conn.cursor()
    cur.execute(f"SELECT {', '.join(pg_cols)} FROM noctus_cache.{spec['pg_table']}")
    rows = cur.fetchall()
    cur.close()

    # ATOMIC, explicitly. A pull DELETEs before it INSERTs, so a failure
    # partway through would otherwise leave the operator worse off than
    # before they tried to restore — a wiped cache plus an error. Python's
    # implicit transaction happens to give us this today, but "happens to"
    # is how the pull path got into its 2026-08-18 state; the rollback is
    # written down and tested (`test_failed_pull_leaves_prior_cache_intact`).
    try:
        return _pull_chunks_inner(
            local, rows, chunks_table=chunks_table,
            vec_table=vec_table, json_table=json_table, local_cols=local_cols,
            emb_idx=emb_idx, backfill=backfill,
        )
    except Exception:
        local.rollback()
        raise


def _pull_chunks_inner(
    local: sqlite3.Connection, rows: list, *,
    chunks_table: str, vec_table: str, json_table: str,
    local_cols: list[str], emb_idx: int, backfill: dict[str, Any],
) -> dict[str, Any]:
    """The write half of `_pull_chunks_with_embedding` — see its docstring.

    Split out purely so the caller can wrap it in one rollback boundary.
    """
    import json

    # Wipe all three tables together — a pull REPLACES the local cache, and
    # leaving a stale sibling behind is exactly the drift class above.
    local.execute(f"DELETE FROM {chunks_table}")
    local.execute(f"DELETE FROM {json_table}")
    have_vec = False
    try:
        local.execute(f"DELETE FROM {vec_table}")
        have_vec = True
    except sqlite3.OperationalError:
        pass  # extension absent on this connection — json-only pull.

    if not rows:
        local.commit()
        return {"rows_pulled": 0, "vec_rows": 0, "json_rows": 0,
                "null_embedding_count": 0, "null_embedding_sample": [],
                "legacy_null_backfilled": {}}

    insert_sql = (
        f"INSERT INTO {chunks_table} ({', '.join(local_cols)}) "
        f"VALUES ({', '.join(['?'] * len(local_cols))})"
    )
    backfilled: dict[str, int] = {}
    null_embeddings: list[dict[str, Any]] = []
    vec_rows = json_rows = 0
    path_pos = local_cols.index("path") if "path" in local_cols else None

    for row in rows:
        values = list(row)
        embedding = values.pop(emb_idx)  # leaves the chunk columns, in order
        # Legacy NULLs in a locally-NOT-NULL column: substitute the DECLARED
        # sentinel and count it. Any other NULL falls through to sqlite, which
        # raises — an unknown gap must not be papered over.
        for col_name, sentinel in backfill.items():
            pos = local_cols.index(col_name)
            if values[pos] is None:
                values[pos] = sentinel
                backfilled[col_name] = backfilled.get(col_name, 0) + 1
        cur_local = local.execute(insert_sql, tuple(values))
        rowid = cur_local.lastrowid

        if embedding is None:
            null_embeddings.append({
                "rowid_alias": rowid,
                "path": values[path_pos] if path_pos is not None else None,
            })
            continue
        # pgvector hands back either "[1.0, 2.0]" or a sequence. Normalize.
        emb_list = json.loads(embedding) if isinstance(embedding, str) else list(embedding)
        local.execute(
            f"INSERT INTO {json_table}(chunk_rowid, embedding) VALUES (?, ?)",
            (rowid, json.dumps(emb_list)),
        )
        json_rows += 1
        if have_vec:
            local.execute(
                f"INSERT INTO {vec_table}(rowid, embedding) VALUES (?, ?)",
                (rowid, _ec.pack_vec(emb_list)),
            )
            vec_rows += 1

    local.commit()
    return {
        "rows_pulled": len(rows),
        "vec_rows": vec_rows,
        "json_rows": json_rows,
        "null_embedding_count": len(null_embeddings),
        "null_embedding_sample": null_embeddings[:10],
        "legacy_null_backfilled": backfilled,
    }


def pull_one_cache(
    cache_name: str, *, dsn: str | None = None, repo_root: Path | None = None,
) -> dict[str, Any]:
    """Pull a single cache from prod Postgres → local SQLite. Inverse of mirror.

    Returns: `{ok, cache, rows_pulled, target_path, detail?, error?}`.
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

    # `_ec.connect_cache` (not a bare sqlite3.connect) so the sqlite-vec
    # extension is loaded where available — without it the `*_vec` sibling
    # cannot be created OR written, and the pull silently degrades to a
    # json-only cache. Also applies the standard WAL + busy_timeout pragmas.
    local = _ec.connect_cache(sqlite_target)
    local.row_factory = sqlite3.Row
    apply_locking_pragmas(local)
    _init_local_schema(local, cache_name)

    detail: dict[str, Any] | None = None
    try:
        with backend.connect(cache_name) as pg_conn:
            if cache_name in _EMBEDDING_CACHE_SPEC:
                detail = _pull_chunks_with_embedding(
                    local, pg_conn, spec=_EMBEDDING_CACHE_SPEC[cache_name],
                )
                rows = detail["rows_pulled"]
            elif cache_name in _SIMPLE_CACHE_SPEC:
                spec = _SIMPLE_CACHE_SPEC[cache_name]
                rows = _pull_simple_table(
                    local, pg_conn, spec["sqlite_table"], spec["pg_table"],
                    spec["columns"],
                )
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

    result: dict[str, Any] = {
        "ok": True,
        "cache": cache_name,
        "rows_pulled": rows,
        "target_path": str(sqlite_target),
    }
    if detail is not None:
        result["detail"] = detail
        # Surface the two conditions a caller must not discover later.
        warnings: list[str] = []
        if detail["null_embedding_count"]:
            warnings.append(
                f"{detail['null_embedding_count']} chunk(s) arrived with a NULL "
                f"embedding and are unsearchable — prod holds an incomplete mirror"
            )
        for col, n in detail["legacy_null_backfilled"].items():
            warnings.append(
                f"{n} row(s) had no `{col}` in prod (column predates this "
                f"snapshot); wrote the declared sentinel "
                f"{_EMBEDDING_CACHE_SPEC[cache_name]['legacy_null_backfill'][col]!r}. "
                f"Re-run cache_deploy_mirror from a healthy local cache to make it real."
            )
        if not detail["vec_rows"] and detail["json_rows"]:
            warnings.append(
                "sqlite-vec absent here — embeddings landed in the json sibling "
                "only; run repair_embedding_cache_drift under the MCP venv to "
                "populate the vec table (lossless, no re-embed)"
            )
        if warnings:
            result["warnings"] = warnings
    return result


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
            "cache_deploy_mirror. Used for fresh-machine bootstrap and for "
            "restoring a damaged local cache (no OpenAI re-embed required). "
            "Auto-invoked by cache_backend on missing local SQLite + opt-out "
            "via NOCTUS_DISABLE_AUTO_CACHE_PULL=1. Pass only=[...] to filter; "
            "default = all caches. Vectors transferred verbatim. REPLACES the "
            "local cache (delete-then-insert per table). Check `warnings` in "
            "the result — a pull can succeed and still hand back a degraded "
            "cache (NULL embeddings in prod, a sentinel-backfilled legacy "
            "column, or a json-only pull when sqlite-vec is absent). Rewritten "
            "2026-08-18: every prior version wrote an invented schema. "
            "KB § PATTERNS/devops/cache-deploy-mirror.md § 2026-08-18 · "
            "KB § PATTERNS/common/cache-portable-architecture.md."
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

    @server.tool(
        name="noctus.dev.repair_embedding_cache_drift",
        description=(
            "LOCAL-ONLY, one-time lossless repair for the 2026-08-14 "
            "cache-mirror-join-drift incident: copies every embedding "
            "that lives ONLY in a chunk-and-embedding cache's JSON-"
            "fallback sibling table into the sqlite-vec table (same "
            "vector, ZERO re-embed / OpenAI spend) and prunes rows "
            "whose chunk no longer exists. Never touches prod. Requires "
            "sqlite-vec loaded in this process. Run BEFORE the next "
            "cache_deploy_mirror confirm=True so prod gets the FULL "
            "corpus. Idempotent. Use only=[...] to scope. KB § PATTERNS/"
            "devops/cache-deploy-mirror.md."
        ),
    )
    def _repair(only: list[str] | None = None) -> dict:
        return repair_embedding_cache_drift(only=only)


__all__ = [
    "init_prod_cache_schema",
    "mirror_one_cache",
    "mirror_all",
    "pull_one_cache",
    "pull_all",
    "repair_embedding_cache_drift",
    "register",
]
