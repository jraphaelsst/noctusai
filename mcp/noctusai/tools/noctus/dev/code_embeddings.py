"""Local SQLite cache of code-symbol embeddings — fifth keeper-mirror cache.

Why this exists
    Cross-product duplication discovery is structurally weak with grep
    (different identifiers, similar shape) and structurally weak with the
    Python-only AST scanners (no TS surface, no embedding-friendly index).
    The KB-embeddings cache (4th) covers documentation; THIS one covers
    *code*. Together they form the two-half semantic layer over the repo:
    docs at `kb-embeddings.sqlite`, code at `code-embeddings.sqlite`.

How it works (educate the reader)
    1. Walk the source tree (default: `mcp/`, `noctusai_lib/`, `products/seed/`,
       and any other roots in `_CODE_ROOTS`). Skip `__pycache__`, `node_modules`,
       `venv/`, `.git/`, dotfiles.
    2. For every Python file: parse via stdlib `ast`. Emit one chunk per
       module-level **FunctionDef / AsyncFunctionDef / ClassDef** with
       symbol name + source text. (Methods on a class are reachable via the
       class chunk — going finer would explode chunk count without helping
       discovery.) Files that fail to parse fall back to one whole-file chunk.
    3. For every TypeScript file (`*.ts`, `*.tsx`): emit one chunk per file
       (TS AST in Python is a heavier dep than this surface warrants — the
       roadmap is explicit on this).
    4. A file's chunks → 1536-D vectors via the shared seed embedder,
       BATCHED (`noctusai_lib.integrations.llm.generate_embeddings_batch` —
       same provider as KB embeddings, no new external dep). One HTTP
       round-trip per `_iter_batches()` slice (default 64 chunks/request),
       not one per chunk — the fix for the 2026-08 pre-push retry-storm
       where a 508-chunk refresh fired 508 independently-retried requests.
    5. Stored as float32 BLOBs in sqlite-vec (fast path) or JSON in the
       fallback table (pure-Python cosine scan).
    6. Query time: embed the query → cosine sort → return top-K
       `{path, symbol_name, kind, chunk_text, score}`.

Mirror contract (5th in the family — keeper-pattern + agent-context +
auto-improvement + kb-embeddings + this)
    Same 3 legs:
      (a) Eager pre-commit refresh on staged `**/*.{py,ts,tsx}` under the
          tracked code roots.
      (b) Lazy query-time per-file source_sha mismatch rebuild.
      (c) `check_code_embeddings_cache_freshness` keeper (severity
          `warning` — vector code search is advisory; missing/stale cache
          degrades discovery but doesn't break correctness).

Why warning not high
    Same rationale as kb-embeddings: a stale code-vector cache returns
    slightly outdated rankings; recurrence detection still works via grep
    + scan_recurrence tools. Don't block commits over a degraded discovery
    layer.

Engine choice
    Same TWO-LAYER stack as kb_embeddings: OpenAI text-embedding-3-small
    via the seed lib + sqlite-vec for storage (JSON fallback when absent).

Depth · `KB § CONTEXT/PATTERNS/common/code-embeddings.md`.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import math
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path

from settings import REPO_ROOT

# v4.0 N=4 consolidation: shared helpers (connect / pack / embed / cosine /
# HAS_VEC / sqlite_vec) live in _embedding_corpus. Module-level aliases
# below preserve back-compat for direct symbol importers.
from . import _embedding_corpus as _ec
from ._embedding_corpus import HAS_VEC as _HAS_VEC, sqlite_vec


# ── Paths ────────────────────────────────────────────────────────────────────
from .cache_backend import cache_dir as _cache_dir, cache_path as _cache_path

CACHE_DIR = _cache_dir()
CACHE_PATH = _cache_path("code-embeddings")

# Code roots scanned. Add more as the platform grows.
_CODE_ROOTS = ("mcp", "noctusai_lib", "products/seed")
# Filename extensions to embed.
_PY_EXTS = (".py",)
_TS_EXTS = (".ts", ".tsx")
# Path-component blocklist (skip these subtrees entirely).
_SKIP_PARTS = frozenset({
    "__pycache__", "node_modules", "venv", ".venv", ".git",
    "dist", "build", ".pytest_cache", ".mypy_cache",
})

# Tunables (tracked in the KB doc).
MAX_CHUNK_CHARS = 6000   # Python AST chunks: bodies can run long; cap to keep
                         # the embedding within model budget (~1500 tokens).
MIN_CHUNK_CHARS = 50     # below this, the chunk is too trivial to be useful
                         # (one-liner helpers, empty stubs).
EMBEDDING_DIM = 1536     # OpenAI text-embedding-3-small.


# v4.0 N=4 consolidation: now/sha/connect/pack delegate to the framework.
_now_iso = _ec.now_iso
_sha_file = _ec.sha_file


def _connect() -> sqlite3.Connection:
    """Open the code-embeddings cache (delegates to shared connect_cache)."""
    return _ec.connect_cache(CACHE_PATH)


_pack_vec = _ec.pack_vec


# Metadata + chunks table — chunks carry both symbol_name AND kind so
# queries can filter (e.g. only classes, only async functions). The vec
# table joins by rowid_alias the same way kb_embeddings does.
#
# Schema is owned by the shared `_ec.init_schema` — single source of truth
# (2026-08-14 cache-mirror-join-drift fix: creating ONLY the current
# process's engine table here is exactly how the two sibling tables
# drifted out of sync across environments in the first place, since
# `code_embeddings.py` mirrors `_META_SCHEMA`/`_VEC_SCHEMA`/`_FALLBACK_SCHEMA`
# above as documentation of the shape `_ec` generates for these table
# names). See `_embedding_corpus.init_schema` + KB § PATTERNS/devops/
# cache-deploy-mirror.md.
def _init_schema(conn: sqlite3.Connection) -> None:
    _ec.init_schema(
        conn, "code_chunks", "code_vec", "code_embeddings_json",
        extra_columns={"symbol_name": "TEXT NOT NULL", "kind": "TEXT NOT NULL"},
    )


# ── Source-tree walker ───────────────────────────────────────────────────────
def _iter_code_files(root: Path) -> list[Path]:
    """Yield every Python + TypeScript source file under the tracked roots,
    skipping the _SKIP_PARTS subtrees and dotfile-prefixed entries."""
    out: list[Path] = []
    for code_root in _CODE_ROOTS:
        base = root / code_root
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if any(part.startswith(".") or part in _SKIP_PARTS for part in p.relative_to(root).parts):
                continue
            if p.suffix in _PY_EXTS + _TS_EXTS:
                out.append(p)
    return sorted(out)


# ── Python chunker (stdlib ast — top-level FunctionDef / ClassDef) ───────────
def _chunk_python(text: str, source_lines: list[str]) -> list[tuple[str, str, str]]:
    """Return `[(symbol_name, kind, chunk_text), ...]` for a Python source.

    Module-level FunctionDef / AsyncFunctionDef / ClassDef → one chunk each.
    If `ast.parse` fails (syntax error, partial file) → one whole-file chunk.
    Methods inside a class ARE included transitively via the class chunk;
    going finer would explode chunk count without improving discovery.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # Fall back to whole-file — better a coarse signal than no signal.
        return [("", "file", text)] if len(text) >= MIN_CHUNK_CHARS else []
    chunks: list[tuple[str, str, str]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        # ast.get_source_segment is the cleanest way; falls back to line-range.
        try:
            segment = ast.get_source_segment(text, node, padded=False)
        except Exception:  # noqa: BLE001 — version-tolerant
            segment = None
        if segment is None:
            start = max(0, node.lineno - 1)
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            segment = "\n".join(source_lines[start:end])
        if not segment:
            continue
        if len(segment) > MAX_CHUNK_CHARS:
            segment = segment[:MAX_CHUNK_CHARS]
        if len(segment) < MIN_CHUNK_CHARS:
            continue
        kind = (
            "async_function" if isinstance(node, ast.AsyncFunctionDef)
            else "function" if isinstance(node, ast.FunctionDef)
            else "class"
        )
        chunks.append((node.name, kind, segment))
    if not chunks and len(text) >= MIN_CHUNK_CHARS:
        # File has no top-level def/class — embed as one file-level chunk.
        capped = text[:MAX_CHUNK_CHARS] if len(text) > MAX_CHUNK_CHARS else text
        chunks.append(("", "file", capped))
    return chunks


def _chunk_typescript(text: str) -> list[tuple[str, str, str]]:
    """Return one whole-file chunk for a TypeScript source.

    Per the roadmap: AST-level chunking for TS would require a separate
    parser dep; file-level is the pragmatic baseline. Future slice can
    refine via tree-sitter-typescript if discovery quality demands it.
    """
    if len(text) < MIN_CHUNK_CHARS:
        return []
    capped = text[:MAX_CHUNK_CHARS] if len(text) > MAX_CHUNK_CHARS else text
    return [("", "file", capped)]


# v4.0 N=4 consolidation: embed/cosine delegate to _embedding_corpus.
_embed_sync = _ec.embed_sync
_embed_batch_sync = _ec.embed_batch_sync
_iter_batches = _ec.iter_batches
_cosine = _ec.cosine


# ── Public API ───────────────────────────────────────────────────────────────
def refresh(
    force: bool = False,
    paths: list[str] | None = None,
    repo_root: Path | None = None,
) -> dict:
    """Re-populate code embeddings. Per-file source_sha guard short-circuits
    in-sync files. `paths` limits scope (repo-rel). `force=True` rebuilds anyway.

    Returns `{ok, status, refreshed, skipped, errors, rows_written}`.
    Provider failure rolls back the failing file's partial inserts and
    continues with the rest — advisory layer, not all-or-nothing across files.
    """
    root = repo_root or REPO_ROOT
    if not any((root / r).is_dir() for r in _CODE_ROOTS):
        return {"ok": True, "status": "in-sync", "refreshed": [], "skipped": [],
                "errors": [], "rows_written": 0}
    conn = _connect()
    _init_schema(conn)

    all_files = _iter_code_files(root)
    if paths:
        path_set = set(paths)
        targets = [p for p in all_files if str(p.relative_to(root)) in path_set]
    else:
        targets = all_files

    refreshed: list[str] = []
    skipped: list[str] = []
    errors: list[dict] = []
    total_rows = 0

    # Capture the REAL provider token usage across the whole refresh batch
    # (ground truth for the cost ledger, not the MAX_CHUNK_CHARS//4 estimate).
    _usage = _ec.UsageAccumulator()
    _restore_usage = _ec.install_capture_sink(_usage)

    for src_path in targets:
        rel = str(src_path.relative_to(root))
        sha = _sha_file(src_path)
        if not force:
            cur = conn.execute(
                "SELECT DISTINCT source_sha FROM code_chunks WHERE path=? LIMIT 1",
                (rel,),
            )
            row = cur.fetchone()
            if row and row["source_sha"] == sha:
                skipped.append(rel)
                continue
        # Rebuild this file's rows — clear BOTH engines' tables unconditionally
        # (2026-08-14 fix), not just the current process's `_HAS_VEC` branch:
        # a PRIOR refresh of this same file may have run under a DIFFERENT
        # environment (see `_ec.delete_embedding_rows`).
        cur = conn.execute("SELECT rowid_alias FROM code_chunks WHERE path=?", (rel,))
        old_rowids = [r[0] for r in cur.fetchall()]
        if old_rowids:
            _ec.delete_embedding_rows(
                conn, vec_table="code_vec", json_table="code_embeddings_json",
                rowids=old_rowids,
            )
            conn.execute("DELETE FROM code_chunks WHERE path=?", (rel,))
        try:
            text = src_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            errors.append({"path": rel, "error": f"read: {e}"})
            continue
        if src_path.suffix in _PY_EXTS:
            chunks = _chunk_python(text, text.splitlines())
        else:
            chunks = _chunk_typescript(text)
        if not chunks:
            continue
        now = _now_iso()
        per_file_ok = True
        per_file_rowids: list[int] = []
        # Batch the embed calls — ONE HTTP round-trip per `_iter_batches()`
        # slice instead of one PER CHUNK. This is the fix for the 2026-08
        # pre-push retry-storm: a 508-chunk refresh used to fire 508
        # independently-paced-and-retried requests (507 retries observed —
        # roughly one per chunk — despite OpenAI itself being healthy
        # throughout); the embeddings endpoint accepts an array `input`, so
        # batching collapses that to ceil(chunks/batch_size) requests. A
        # batch failure fails ALL chunks in that slice together, preserving
        # the existing per-FILE all-or-nothing rollback below (a file's
        # earlier-batch rows are rolled back too — never partially cached).
        enumerated_chunks = list(enumerate(chunks))
        for batch in _iter_batches(enumerated_chunks):
            batch_texts = [item[1][2] for item in batch]  # chunk_text
            try:
                vecs = _embed_batch_sync(batch_texts)
            except Exception as e:  # noqa: BLE001
                errors.append({
                    "path": rel, "chunk_idx": batch[0][0], "error": str(e)[:200],
                })
                per_file_ok = False
                break
            if len(vecs) != len(batch):
                errors.append({
                    "path": rel, "chunk_idx": batch[0][0],
                    "error": f"batch embed returned {len(vecs)} vectors for {len(batch)} inputs",
                })
                per_file_ok = False
                break
            dim_bad = next((i for i, v in enumerate(vecs) if len(v) != EMBEDDING_DIM), None)
            if dim_bad is not None:
                errors.append({
                    "path": rel, "chunk_idx": batch[dim_bad][0],
                    "error": f"unexpected dim {len(vecs[dim_bad])} (want {EMBEDDING_DIM})",
                })
                per_file_ok = False
                break

            for (idx, (symbol, kind, chunk_text)), vec in zip(batch, vecs):
                cur = conn.execute(
                    "INSERT INTO code_chunks(path,chunk_idx,symbol_name,kind,"
                    "chunk_text,source_sha,cached_at) VALUES (?,?,?,?,?,?,?)",
                    (rel, idx, symbol, kind, chunk_text, sha, now),
                )
                row_id = cur.lastrowid
                per_file_rowids.append(row_id)
                if _HAS_VEC:
                    conn.execute(
                        "INSERT INTO code_vec(rowid, embedding) VALUES (?, ?)",
                        (row_id, _pack_vec(vec)),
                    )
                else:
                    conn.execute(
                        "INSERT INTO code_embeddings_json(chunk_rowid, embedding) VALUES (?, ?)",
                        (row_id, json.dumps(vec)),
                    )
                total_rows += 1
        if not per_file_ok and per_file_rowids:
            _ec.delete_embedding_rows(
                conn, vec_table="code_vec", json_table="code_embeddings_json",
                rowids=per_file_rowids,
            )
            conn.execute("DELETE FROM code_chunks WHERE path=?", (rel,))
            total_rows -= len(per_file_rowids)
            continue
        refreshed.append(rel)

    # Orphan prune (full passes only): drop rows for source files no longer on
    # disk (e.g. the renamed test_seven_way_sync.py). Shared helper; excludes
    # kind='organ' (organs live outside _CODE_ROOTS + own lifecycle). A scoped
    # refresh (`paths=...`) must NOT prune.
    pruned: list[str] = []
    if not paths:
        pruned = _ec.prune_orphan_chunks(
            conn,
            chunks_table="code_chunks",
            vec_table="code_vec",
            json_table="code_embeddings_json",
            live_rels={str(p.relative_to(root)) for p in all_files},
            exclude_organ=True,
        )

    conn.execute(
        "INSERT OR REPLACE INTO cache_meta(key,value) VALUES (?,?)",
        ("populated_at", _now_iso()),
    )
    conn.commit()
    conn.close()
    _restore_usage()
    status = "in-sync" if not refreshed else ("rebuilt" if not errors else "partial")

    # Cost instrumentation — durable ledger for OpenAI embed spend.
    if total_rows > 0:
        try:
            from tools.noctus.dev import vector_costs as _vc
            _estimated_tokens = total_rows * (MAX_CHUNK_CHARS // 4)
            _actual_tokens = _usage.total_tokens if _usage.has_data else None
            _actual_cost = _usage.cost_usd if _usage.has_data else None
            _vc.log_refresh_batch(
                namespace="code-embeddings",
                model="text-embedding-3-small",
                doc_count=len(refreshed),
                chunk_count=total_rows,
                estimated_tokens=_estimated_tokens,
                provider="openai",
                source_ref=f"session:{_now_iso()[:10]}",
                actual_tokens=_actual_tokens,
                actual_cost_usd=_actual_cost,
            )
        except Exception as _vc_exc:  # noqa: BLE001
            import logging as _log
            _log.getLogger(__name__).warning(
                "code_embeddings: vector_costs instrumentation failed: %s", _vc_exc
            )

    return {
        "ok": not errors,
        "status": status,
        "refreshed": refreshed,
        "skipped": skipped,
        "errors": errors,
        "rows_written": total_rows,
        "pruned": pruned,
    }


def search(
    query: str,
    top_k: int = 5,
    min_score: float = 0.0,
    kind: str | None = None,
) -> list[dict]:
    """Embed `query`, return top-K matching code symbols by cosine similarity.

    `kind` optionally filters by `'function' | 'async_function' | 'class' | 'file'`.
    Returns `[{path, symbol_name, kind, chunk_idx, chunk_text, score, engine}]`
    ordered by score desc. Lazy-degrades to empty on missing cache or
    provider failure.
    """
    if not CACHE_PATH.exists():
        return []
    try:
        q_vec = _embed_sync(query)
    except Exception:
        return []
    conn = _connect()
    _init_schema(conn)
    results: list[dict] = []
    if _HAS_VEC:
        q_blob = _pack_vec(q_vec)
        # vec0 doesn't support WHERE on joined columns inside MATCH; fetch
        # extra (top_k * 3) then filter by kind in Python.
        fetch_k = top_k * 3 if kind else top_k
        cur = conn.execute(
            """
            SELECT c.path, c.chunk_idx, c.symbol_name, c.kind, c.chunk_text, v.distance
            FROM code_vec v
            JOIN code_chunks c ON c.rowid_alias = v.rowid
            WHERE v.embedding MATCH ?
              AND k = ?
            ORDER BY v.distance
            """,
            (q_blob, fetch_k),
        )
        for r in cur.fetchall():
            if kind and r["kind"] != kind:
                continue
            distance = float(r["distance"])
            score = 1.0 / (1.0 + distance)
            if score >= min_score:
                results.append({
                    "path": r["path"], "chunk_idx": r["chunk_idx"],
                    "symbol_name": r["symbol_name"], "kind": r["kind"],
                    "chunk_text": r["chunk_text"], "score": score,
                    "engine": "sqlite-vec",
                })
            if len(results) >= top_k:
                break
    else:
        rows_q = """
            SELECT c.path, c.chunk_idx, c.symbol_name, c.kind, c.chunk_text, j.embedding
            FROM code_chunks c
            JOIN code_embeddings_json j ON j.chunk_rowid = c.rowid_alias
        """
        if kind:
            rows_q += " WHERE c.kind = ?"
            rows = conn.execute(rows_q, (kind,)).fetchall()
        else:
            rows = conn.execute(rows_q).fetchall()
        scored: list[tuple[float, dict]] = []
        for r in rows:
            try:
                vec = json.loads(r["embedding"])
            except (json.JSONDecodeError, TypeError):
                continue
            score = _cosine(q_vec, vec)
            if score >= min_score:
                scored.append((score, {
                    "path": r["path"], "chunk_idx": r["chunk_idx"],
                    "symbol_name": r["symbol_name"], "kind": r["kind"],
                    "chunk_text": r["chunk_text"], "score": score,
                    "engine": "pure-python",
                }))
        scored.sort(key=lambda t: t[0], reverse=True)
        results = [d for _, d in scored[:top_k]]
    conn.close()
    return results


def list_files() -> list[str]:
    """Distinct source files cached. Verify coverage after refresh."""
    if not CACHE_PATH.exists():
        return []
    conn = _connect()
    _init_schema(conn)
    cur = conn.execute("SELECT DISTINCT path FROM code_chunks ORDER BY path")
    out = [r["path"] for r in cur.fetchall()]
    conn.close()
    return out


def get_source_sha(path: str, repo_root: Path | None = None) -> tuple[str, str | None]:
    """Return (live_sha, cached_sha) for a source file. Supports the freshness
    keeper. `path` is repo-rel; cached_sha is None when no rows."""
    root = repo_root or REPO_ROOT
    src = root / path
    live = _sha_file(src)
    cached: str | None = None
    if CACHE_PATH.exists():
        try:
            # Reuse the module's pragma-applying helper (WAL + busy_timeout) —
            # a raw sqlite3.connect() here would skip busy_timeout and raise
            # `database is locked` when the freshness keeper reads this while the
            # pre-push refresh writer holds the cache. KB § PATTERNS/common/cache-locking-discipline.md.
            conn = _connect()
            cur = conn.execute(
                "SELECT DISTINCT source_sha FROM code_chunks WHERE path=? LIMIT 1",
                (path,),
            )
            row = cur.fetchone()
            cached = row[0] if row else None
            conn.close()
        except sqlite3.Error:
            cached = None
    return live, cached


def active_engine() -> str:
    return "sqlite-vec" if _HAS_VEC else "pure-python"


# ── Organizational tools (code-vector-empowered discovery) ─────────────────
def _load_all_chunk_vectors() -> list[tuple[str, int, str, str, str, list[float]]]:
    """Internal: load every (path, chunk_idx, symbol_name, kind, chunk_text, vector)."""
    if not CACHE_PATH.exists():
        return []
    conn = _connect()
    _init_schema(conn)
    out: list[tuple[str, int, str, str, str, list[float]]] = []
    if _HAS_VEC:
        cur = conn.execute(
            """
            SELECT c.path, c.chunk_idx, c.symbol_name, c.kind, c.chunk_text, v.embedding
            FROM code_chunks c JOIN code_vec v ON v.rowid = c.rowid_alias
            """
        )
        for r in cur.fetchall():
            blob = r["embedding"]
            vec = list(struct.unpack(f"{len(blob)//4}f", blob))
            out.append((r["path"], r["chunk_idx"], r["symbol_name"], r["kind"], r["chunk_text"], vec))
    else:
        cur = conn.execute(
            """
            SELECT c.path, c.chunk_idx, c.symbol_name, c.kind, c.chunk_text, j.embedding
            FROM code_chunks c JOIN code_embeddings_json j ON j.chunk_rowid = c.rowid_alias
            """
        )
        for r in cur.fetchall():
            try:
                vec = json.loads(r["embedding"])
            except (json.JSONDecodeError, TypeError):
                continue
            out.append((r["path"], r["chunk_idx"], r["symbol_name"], r["kind"], r["chunk_text"], vec))
    conn.close()
    return out


def code_neighbors(path: str, symbol_name: str = "", top_k: int = 5) -> list[dict]:
    """Top-K semantically nearest code symbols to the given `path` + `symbol_name`.

    If `symbol_name` is empty, uses the first chunk in the file as anchor.
    Returns `[{path, symbol_name, kind, score}]` ordered desc by similarity.
    Use case: cross-product recurrence discovery — "what other code looks
    like this helper?" → candidates for absorption.
    """
    rows = _load_all_chunk_vectors()
    if not rows:
        return []
    anchor = next(
        (
            (p, idx, sym, k, txt, vec) for p, idx, sym, k, txt, vec in rows
            if p == path and (not symbol_name or sym == symbol_name)
        ),
        None,
    )
    if anchor is None:
        return []
    _, _, _, _, _, anchor_vec = anchor
    scored: list[tuple[float, dict]] = []
    for p, idx, sym, k, _txt, vec in rows:
        if p == path and (not symbol_name or sym == symbol_name):
            continue  # exclude the anchor itself
        score = _cosine(anchor_vec, vec)
        scored.append((score, {
            "path": p, "symbol_name": sym, "kind": k,
            "chunk_idx": idx, "score": score,
        }))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [d for _, d in scored[:top_k]]


def code_similar_to_text(text: str, top_k: int = 5, kind: str | None = None) -> list[dict]:
    """Find code symbols semantically similar to free text.

    Use case: "I want to write a helper that does X" → run this first; if a
    candidate scores >0.7, reuse / extend it instead of writing fresh.
    Combats N=3+ recurrence at AUTHORING time, not at refactor time.
    """
    return search(text, top_k=top_k, kind=kind)


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.code_search",
        description=(
            "Semantic search over the code corpus — fifth keeper-mirror cache. "
            "ADDITIVE to grep / scan_recurrence (which stay canonical for "
            "exact-name lookups). Embeds the query, returns top-K matching "
            "code symbols (function / class / file) by cosine similarity. "
            "Optional `kind` filter: 'function' | 'async_function' | 'class' "
            "| 'file'. Use for fuzzy-intent queries ('find helpers that "
            "extract a phone number') where exact identifiers are unknown. "
            "Graceful-degrades to empty result on provider failure. "
            "KB § CONTEXT/PATTERNS/common/code-embeddings.md."
        ),
    )
    def _search(query: str, top_k: int = 5, min_score: float = 0.0,
                kind: str | None = None) -> list[dict]:
        return search(query, top_k=top_k, min_score=min_score, kind=kind)

    @server.tool(
        name="noctus.dev.code_embeddings_refresh",
        description=(
            "Re-populate the code embeddings cache from the tracked source "
            "roots (mcp/, noctusai_lib/, products/seed/). Per-file source_sha "
            "guard short-circuits in-sync files; `paths=[...]` limits scope; "
            "`force=True` rebuilds anyway. Auto-run by pre-commit on staged "
            "code changes. Logs OpenAI embed cost to vector-costs.ndjson."
        ),
    )
    def _refresh(force: bool = False, paths: list[str] | None = None) -> dict:
        return refresh(force=force, paths=paths)

    @server.tool(
        name="noctus.dev.code_embeddings_list",
        description=(
            "Distinct source files currently in the code embeddings cache. "
            "Useful for verifying coverage after a refresh."
        ),
    )
    def _list() -> list[str]:
        return list_files()

    @server.tool(
        name="noctus.dev.code_neighbors",
        description=(
            "Find top-K semantically nearest code symbols to a given "
            "{path, symbol_name}. Powers cross-product recurrence discovery: "
            "'what other code looks like this helper?' → candidates for "
            "absorption to the seed (combats the N=3+ recurrence rule at "
            "discovery time)."
        ),
    )
    def _neighbors(path: str, symbol_name: str = "", top_k: int = 5) -> list[dict]:
        return code_neighbors(path, symbol_name=symbol_name, top_k=top_k)

    @server.tool(
        name="noctus.dev.code_similar_to_text",
        description=(
            "Find code symbols semantically similar to free text. Use BEFORE "
            "writing a new helper: if an existing symbol scores >0.7, reuse "
            "or extend it instead of authoring fresh. Combats N=3+ "
            "recurrence at AUTHORING time, not at refactor time. Optional "
            "`kind` filter restricts to one symbol kind."
        ),
    )
    def _similar(text: str, top_k: int = 5, kind: str | None = None) -> list[dict]:
        return code_similar_to_text(text, top_k=top_k, kind=kind)


# Auto-register with the vector platform so vector_status() reports rows.
def _code_rows_count() -> int | None:
    try:
        return len(list_files())
    except Exception:  # noqa: BLE001
        return None


try:
    from . import vectorize as _vectorize
    _vectorize.register_cache(
        name="code-embeddings",
        purpose="Code semantic search (cross-product recurrence discovery)",
        rows_fn=_code_rows_count,
    )
except Exception:  # noqa: BLE001 — import-cycle resilient
    pass


__all__ = [
    "CACHE_PATH",
    "MAX_CHUNK_CHARS",
    "MIN_CHUNK_CHARS",
    "EMBEDDING_DIM",
    "refresh",
    "search",
    "list_files",
    "get_source_sha",
    "active_engine",
    "code_neighbors",
    "code_similar_to_text",
    "register",
]
