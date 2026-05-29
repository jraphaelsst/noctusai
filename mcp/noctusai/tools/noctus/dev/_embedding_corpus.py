"""Shared embedding-cache infrastructure — the N=4 consolidation (v4.0).

Until v4.0 each of the 4 embedding caches (kb / code / memory / corpus)
carried its own copy of: chunker, embedder wrapper, cosine helper, vector-
pack helper, WAL+sqlite-vec connect, schema templates, refresh loop, search
loop. The N=4 recurrence triggered the formalization rule — this module is
the single source.

Public surface:
  EMBEDDING_DIM, MAX_CHUNK_CHARS, MIN_CHUNK_CHARS — knobs.
  HAS_VEC                                          — runtime flag.
  chunk_markdown(text) -> list[str]                — markdown-structural.
  embed_sync(text) -> list[float]                  — sync wrap of seed lib.
  cosine(a, b) -> float                            — pure-Python.
  pack_vec(vec) -> bytes                           — little-endian float32.
  connect_cache(cache_path) -> sqlite3.Connection  — WAL + sqlite-vec.

For the per-corpus modules (kb / memory / corpus — markdown-shaped):
  MarkdownCorpus dataclass + refresh_markdown_corpus + search_markdown_corpus

code-embeddings stays its own module because its chunker is AST-based for
.py and whole-file for .ts/.tsx — a different shape from markdown — but
adopts the shared embed/cosine/pack/connect helpers.

KB § PATTERNS/common/kb-vector-search.md (the first incarnation),
KB § PATTERNS/common/memory-embeddings.md / corpus-embeddings.md.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import sqlite3
import struct
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional, TypeVar


# ── Knobs ──────────────────────────────────────────────────────────────────
EMBEDDING_DIM = 1536      # OpenAI text-embedding-3-small.
MAX_CHUNK_CHARS = 1800    # ~450 tokens; well under the 8191-token model limit.
MIN_CHUNK_CHARS = 200     # below this, don't emit (too short to be useful).


# ── sqlite-vec optional ────────────────────────────────────────────────────
try:
    import sqlite_vec  # type: ignore[import-not-found]
    HAS_VEC = True
except ImportError:
    sqlite_vec = None  # type: ignore[assignment]
    HAS_VEC = False


# ── Time + sha helpers (shared) ────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


# ── Embedding (sync wrap) ──────────────────────────────────────────────────
def embed_sync(text: str) -> list[float]:
    """Sync-wrap the async `noctusai_lib.integrations.llm.generate_embedding`.

    Run in a fresh event loop so we don't fight any caller-owned loop.
    Caller MUST ensure `configure_llm()` was called (the noctusai CLI's
    `_ensure_llm_configured` helper does this for refresh/search paths).
    """
    from noctusai_lib.integrations.llm import generate_embedding
    return asyncio.run(generate_embedding(text))


# ── Cosine ─────────────────────────────────────────────────────────────────
def cosine(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity. ~10ms for 1536-D × 500 vectors."""
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


# ── Top-K similarity ranking ────────────────────────────────────────────────
_T = TypeVar("_T")


def top_k_similar(
    query_vec: list[float],
    candidates: Iterable[tuple[list[float], _T]],
    *,
    k: int = 5,
    min_score: float = 0.0,
) -> list[tuple[float, _T]]:
    """Return the top-K ``(score, item)`` pairs ranked by cosine similarity.

    Generic over the payload type ``T`` — consumers pass ``(vec, any_dict)``
    pairs and get back ``(score, any_dict)`` pairs sorted high-to-low.

    Parameters
    ----------
    query_vec:
        The query embedding.
    candidates:
        Iterable of ``(vector, item)`` pairs.  ``item`` is opaque — returned
        as-is alongside the score.
    k:
        Maximum number of results to return.
    min_score:
        Pairs with ``cosine(query_vec, vec) < min_score`` are excluded.
        Defaults to 0.0 (includes all non-negative similarities).

    Returns
    -------
    List of ``(score, item)`` tuples sorted by score descending, length ≤ k.
    """
    scored: list[tuple[float, _T]] = []
    for vec, item in candidates:
        score = cosine(query_vec, vec)
        if score >= min_score:
            scored.append((score, item))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:k]


# ── Vector pack ────────────────────────────────────────────────────────────
def pack_vec(vec: list[float]) -> bytes:
    """sqlite-vec stores vectors as little-endian float32 BLOBs."""
    return struct.pack(f"{len(vec)}f", *vec)


# ── Connect (WAL + sqlite-vec) ─────────────────────────────────────────────
def connect_cache(cache_path: Path) -> sqlite3.Connection:
    """Open the SQLite cache with WAL journal + sqlite-vec extension loaded
    (when available). Idempotent — safe to call multiple times."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cache_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    if HAS_VEC:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    return conn


# ── Markdown chunker ───────────────────────────────────────────────────────
def chunk_markdown(text: str) -> list[str]:
    """Split a markdown doc into chunks at H2 boundaries, then char-cap.

    Each chunk preserves the H1 title as a prefix for context (so a chunk
    can be retrieved standalone without losing what doc it's from).
    """
    lines = text.splitlines()
    title = ""
    for line in lines[:30]:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # Split at H2 boundaries.
    sections: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current:
                sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)

    if not sections:
        sections = [lines]

    chunks: list[str] = []
    for sec in sections:
        body = "\n".join(sec).strip()
        if not body:
            continue
        prefixed = f"{title}\n\n{body}" if title and not body.startswith(title) else body
        while len(prefixed) > MAX_CHUNK_CHARS:
            cut = prefixed.rfind("\n", MIN_CHUNK_CHARS, MAX_CHUNK_CHARS)
            if cut < 0:
                cut = MAX_CHUNK_CHARS
            chunks.append(prefixed[:cut].strip())
            prefixed = (f"{title}\n\n" if title else "") + prefixed[cut:].strip()
        if len(prefixed) >= MIN_CHUNK_CHARS:
            chunks.append(prefixed.strip())
    return chunks


# ── Schema templates ───────────────────────────────────────────────────────
def meta_schema_sql(
    chunks_table: str,
    extra_columns: Optional[dict[str, str]] = None,
) -> str:
    """DDL for cache_meta + the per-corpus chunks table.

    extra_columns: {col_name: sql_type_with_constraints} appended BEFORE the
    standard (path, chunk_idx, chunk_text, source_sha, cached_at) — used by
    corpus-embeddings for source_type, by code-embeddings for symbol_name.
    """
    extra_cols_sql = ""
    extra_indexes_sql = ""
    if extra_columns:
        for col, decl in extra_columns.items():
            extra_cols_sql += f"  {col}         {decl},\n"
            extra_indexes_sql += (
                f"CREATE INDEX IF NOT EXISTS "
                f"idx_{chunks_table}_{col} ON {chunks_table}({col});\n"
            )
    return f"""
CREATE TABLE IF NOT EXISTS cache_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS {chunks_table} (
  rowid_alias  INTEGER PRIMARY KEY AUTOINCREMENT,
{extra_cols_sql}  path         TEXT NOT NULL,
  chunk_idx    INTEGER NOT NULL,
  chunk_text   TEXT NOT NULL,
  source_sha   TEXT NOT NULL,
  cached_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{chunks_table}_path ON {chunks_table}(path);
{extra_indexes_sql}"""


def vec_schema_sql(vec_table: str) -> str:
    return f"""
CREATE VIRTUAL TABLE IF NOT EXISTS {vec_table} USING vec0(
  embedding float[{EMBEDDING_DIM}]
);
"""


def json_fallback_schema_sql(json_table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {json_table} (
  chunk_rowid  INTEGER PRIMARY KEY,
  embedding    TEXT NOT NULL
);
"""


def init_schema(
    conn: sqlite3.Connection,
    chunks_table: str,
    vec_table: str,
    json_table: str,
    extra_columns: Optional[dict[str, str]] = None,
) -> None:
    conn.executescript(meta_schema_sql(chunks_table, extra_columns))
    if HAS_VEC:
        conn.executescript(vec_schema_sql(vec_table))
    else:
        conn.executescript(json_fallback_schema_sql(json_table))
    conn.commit()


# ── Markdown corpus spec + refresh + search ────────────────────────────────

@dataclass
class MarkdownCorpus:
    """The parameter pack each per-corpus module passes to refresh / search.

    `enumerate_sources` yields `(rel_path: str, abs_path: Path,
    extras: dict[str, str])` triples. `extras` populates the configured
    `extra_columns` (e.g. `{"source_type": "agent"}` for corpus-embeddings;
    empty dict for kb / memory which have no extras).
    """
    cache_path: Path
    chunks_table: str
    vec_table: str
    json_table: str
    enumerate_sources: Callable[[], Iterable[tuple[str, Path, dict]]]
    extra_columns: dict[str, str] = field(default_factory=dict)


def _delete_rows_for_path(conn: sqlite3.Connection, corpus: MarkdownCorpus, rel: str) -> None:
    """Wipe stale rows for one source path from both engines' tables."""
    cur = conn.execute(
        f"SELECT rowid_alias FROM {corpus.chunks_table} WHERE path=?", (rel,)
    )
    old_rowids = [r[0] for r in cur.fetchall()]
    if not old_rowids:
        return
    placeholders = ",".join("?" * len(old_rowids))
    if HAS_VEC:
        conn.execute(
            f"DELETE FROM {corpus.vec_table} WHERE rowid IN ({placeholders})",
            old_rowids,
        )
    else:
        conn.execute(
            f"DELETE FROM {corpus.json_table} WHERE chunk_rowid IN ({placeholders})",
            old_rowids,
        )
    conn.execute(f"DELETE FROM {corpus.chunks_table} WHERE path=?", (rel,))


def refresh_markdown_corpus(
    corpus: MarkdownCorpus,
    *,
    force: bool = False,
    paths: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Re-populate the corpus's embeddings cache.

    Per-file `source_sha` skip when unchanged. Atomic per-doc — partial
    embed failure rolls back that doc's rows. Other corpora are unaffected.

    Returns: ``{ok, status, refreshed, skipped, errors, rows_written}``.
    """
    conn = connect_cache(corpus.cache_path)
    init_schema(
        conn,
        chunks_table=corpus.chunks_table,
        vec_table=corpus.vec_table,
        json_table=corpus.json_table,
        extra_columns=corpus.extra_columns,
    )

    refreshed: list[str] = []
    skipped: list[str] = []
    errors: list[dict] = []
    total_rows = 0

    sources = list(corpus.enumerate_sources())
    if paths:
        wanted = set(paths)
        sources = [s for s in sources if s[0] in wanted]

    for rel, abs_path, extras in sources:
        sha = sha_file(abs_path)
        if not force:
            cur = conn.execute(
                f"SELECT DISTINCT source_sha FROM {corpus.chunks_table} "
                f"WHERE path=? LIMIT 1",
                (rel,),
            )
            row = cur.fetchone()
            if row and row["source_sha"] == sha:
                skipped.append(rel)
                continue

        _delete_rows_for_path(conn, corpus, rel)

        try:
            text = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            errors.append({"path": rel, "error": f"read: {e}"})
            continue

        chunks = chunk_markdown(text)
        if not chunks:
            continue

        ts = now_iso()
        per_doc_ok = True
        per_doc_rowids: list[int] = []

        # Build the INSERT column list dynamically based on extra_columns.
        extra_col_names = list(corpus.extra_columns.keys())
        insert_cols = (
            extra_col_names
            + ["path", "chunk_idx", "chunk_text", "source_sha", "cached_at"]
        )
        placeholders = ",".join("?" * len(insert_cols))
        insert_sql = (
            f"INSERT INTO {corpus.chunks_table}({','.join(insert_cols)}) "
            f"VALUES ({placeholders})"
        )

        for idx, chunk in enumerate(chunks):
            try:
                vec = embed_sync(chunk)
            except Exception as e:  # noqa: BLE001
                errors.append({"path": rel, "chunk_idx": idx, "error": str(e)[:200]})
                per_doc_ok = False
                break
            if len(vec) != EMBEDDING_DIM:
                errors.append({
                    "path": rel, "chunk_idx": idx,
                    "error": f"unexpected dim {len(vec)} (want {EMBEDDING_DIM})",
                })
                per_doc_ok = False
                break

            extra_values = [extras.get(col) for col in extra_col_names]
            row_values = (
                *extra_values, rel, idx, chunk, sha, ts,
            )
            cur = conn.execute(insert_sql, row_values)
            row_id = cur.lastrowid
            per_doc_rowids.append(row_id)
            if HAS_VEC:
                conn.execute(
                    f"INSERT INTO {corpus.vec_table}(rowid, embedding) VALUES (?, ?)",
                    (row_id, pack_vec(vec)),
                )
            else:
                conn.execute(
                    f"INSERT INTO {corpus.json_table}(chunk_rowid, embedding) "
                    f"VALUES (?, ?)",
                    (row_id, json.dumps(vec)),
                )
            total_rows += 1

        if not per_doc_ok and per_doc_rowids:
            ph = ",".join("?" * len(per_doc_rowids))
            if HAS_VEC:
                conn.execute(
                    f"DELETE FROM {corpus.vec_table} WHERE rowid IN ({ph})",
                    per_doc_rowids,
                )
            else:
                conn.execute(
                    f"DELETE FROM {corpus.json_table} WHERE chunk_rowid IN ({ph})",
                    per_doc_rowids,
                )
            conn.execute(
                f"DELETE FROM {corpus.chunks_table} WHERE path=?", (rel,)
            )
        if per_doc_ok:
            refreshed.append(rel)

    conn.commit()
    conn.close()

    status = "refreshed" if refreshed else ("in-sync" if not errors else "errors")
    return {
        "ok": not errors,
        "status": status,
        "refreshed": refreshed,
        "skipped": skipped,
        "errors": errors,
        "rows_written": total_rows,
    }


def search_markdown_corpus(
    corpus: MarkdownCorpus,
    query: str,
    *,
    top_k: int = 5,
    min_score: float = 0.0,
    where_clause: Optional[str] = None,
    where_params: Optional[list] = None,
) -> list[dict]:
    """Embed `query`, return top-K matching chunks ranked by cosine similarity.

    Optional `where_clause` (without WHERE keyword) + `where_params` scopes
    the search — used by corpus-embeddings for `source_type=?` filtering.

    Returns: `[{<extra columns…>, path, chunk_idx, chunk_text, score, engine}]`
    ordered by score desc. Lazy-degrade: empty list if cache missing or
    embedding API unreachable.
    """
    if not corpus.cache_path.exists():
        return []
    try:
        q_vec = embed_sync(query)
    except Exception:
        return []

    conn = connect_cache(corpus.cache_path)
    init_schema(
        conn,
        chunks_table=corpus.chunks_table,
        vec_table=corpus.vec_table,
        json_table=corpus.json_table,
        extra_columns=corpus.extra_columns,
    )

    extra_select = ",".join(f"c.{c}" for c in corpus.extra_columns)
    extra_cols_csv = extra_select + ", " if extra_select else ""
    where_sql = f" AND ({where_clause})" if where_clause else ""
    params_extra = where_params or []

    results: list[dict] = []
    if HAS_VEC:
        q_blob = pack_vec(q_vec)
        sql = (
            f"SELECT {extra_cols_csv}c.path, c.chunk_idx, c.chunk_text, v.distance "
            f"FROM {corpus.vec_table} v "
            f"JOIN {corpus.chunks_table} c ON c.rowid_alias = v.rowid "
            f"WHERE v.embedding MATCH ? AND k = ?{where_sql} "
            f"ORDER BY v.distance"
        )
        cur = conn.execute(sql, (q_blob, top_k, *params_extra))
        for r in cur.fetchall():
            score = 1.0 / (1.0 + float(r["distance"]))
            if score >= min_score:
                hit = {col: r[col] for col in corpus.extra_columns}
                hit.update({
                    "path": r["path"], "chunk_idx": r["chunk_idx"],
                    "chunk_text": r["chunk_text"], "score": score,
                    "engine": "sqlite-vec",
                })
                results.append(hit)
    else:
        sql = (
            f"SELECT {extra_cols_csv}c.path, c.chunk_idx, c.chunk_text, j.embedding "
            f"FROM {corpus.chunks_table} c "
            f"JOIN {corpus.json_table} j ON j.chunk_rowid = c.rowid_alias"
        )
        if where_clause:
            sql += f" WHERE {where_clause}"
            rows = conn.execute(sql, tuple(params_extra)).fetchall()
        else:
            rows = conn.execute(sql).fetchall()
        scored = []
        for r in rows:
            try:
                v = json.loads(r["embedding"])
            except (TypeError, ValueError):
                continue
            score = cosine(q_vec, v)
            if score >= min_score:
                scored.append((score, r))
        scored.sort(key=lambda t: t[0], reverse=True)
        for score, r in scored[:top_k]:
            hit = {col: r[col] for col in corpus.extra_columns}
            hit.update({
                "path": r["path"], "chunk_idx": r["chunk_idx"],
                "chunk_text": r["chunk_text"], "score": score,
                "engine": "fallback-cosine",
            })
            results.append(hit)
    conn.close()
    return results


def aggregate_source_sha(sources: Iterable[tuple[str, Path, dict]]) -> str:
    """Aggregate sha over every source file's content + extras — for the
    freshness keeper."""
    h = hashlib.sha256()
    for rel, abs_path, extras in sorted(sources, key=lambda s: s[0]):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        for k, v in sorted(extras.items()):
            h.update(f"{k}={v}".encode("utf-8"))
            h.update(b"\0")
        if abs_path.exists():
            h.update(abs_path.read_bytes())
    return h.hexdigest()[:12]


__all__ = [
    "EMBEDDING_DIM", "MAX_CHUNK_CHARS", "MIN_CHUNK_CHARS", "HAS_VEC",
    "now_iso", "sha_file",
    "chunk_markdown", "embed_sync", "cosine", "top_k_similar", "pack_vec", "connect_cache",
    "meta_schema_sql", "vec_schema_sql", "json_fallback_schema_sql",
    "init_schema",
    "MarkdownCorpus", "refresh_markdown_corpus", "search_markdown_corpus",
    "aggregate_source_sha",
]
