"""Local SQLite cache of KB doc embeddings — fourth keeper-mirror cache.

Why this exists
    Existing routing (CLAUDE.md §1 + owns_kb + INDEX.md + skills auto-trigger
    + 3 keeper-mirror caches) is precise but **lexical**: it routes via known
    names. Semantic queries — "find patterns about cross-product state
    management" — return nothing useful from grep when the canonical doc
    uses different vocabulary. Vector search is the **discovery layer**:
    fuzzy-meaning queries → ranked relevant KB chunks. ADDITIVE, never
    replacing the curated index.

How it works (educate the reader)
    1. Each `KNOWLEDGE-BASE/**/*.md` doc is chunked (by H2 with paragraph
       overlap), embedded via the seed's `text-embedding-3-small` — NO new
       external dep; same provider + same credential chain as ERP's
       embedding_service.
    2. A doc's chunks → 1536-D vectors, BATCHED
       (`noctusai_lib.integrations.llm.generate_embeddings_batch`, via
       `_embedding_corpus.embed_batch_sync` + `iter_batches`). One HTTP
       round-trip per batch, not one per chunk — the fix for the 2026-08
       pre-push retry-storm (kb-embeddings is one of the four OpenAI-backed
       pre-push refreshes; a large KB diff used to fire one
       independently-retried request per chunk). Stored as JSON in sqlite
       alongside the chunk text + source SHA.
    3. At query time: embed the query, compute cosine similarity vs every
       cached vector (pure-Python; ~500 chunks × 1536-D is trivial),
       return top-K {path, chunk_text, score}.
    4. The LLM consuming the result reads the **chunk text**, never the
       vector — vectors are search indices, not storage.

Mirror contract (4th in the family — keeper-pattern + agent-context +
auto-improvement + this)
    Same 3 legs:
      (a) Eager pre-commit refresh when any `KNOWLEDGE-BASE/**/*.md` is staged.
      (b) Lazy query-time per-doc source_sha mismatch rebuild.
      (c) `check_kb_embeddings_cache_freshness` keeper (severity `warning` —
          NOT `high`: vector search is advisory; missing/stale cache
          degrades discovery but doesn't break correctness).

Why warning not high
    A stale vector cache returns slightly outdated rankings; everything
    else still works. The agent can fall back to grep/owns_kb. Don't
    block commits over a degraded discovery layer.

Engine choice — TWO LAYERS, BOTH OPTIMIZED (user mandate "mix both")
    1. **Embedding model** (text → vector): OpenAI text-embedding-3-small
       via `noctusai_lib.integrations.llm.generate_embedding`. 1536-D,
       org→platform→env credential chain, same provider already in the
       ERP stack (no new external dep). Picked for quality.
    2. **Vector storage + search** (find nearest): `sqlite-vec` (MIT
       extension by asg017). Adds `vec0` virtual tables + native
       `vec_distance_cosine()` function + binary BLOB storage (~4× more
       compact than JSON). FAST path: SQL `ORDER BY vec_distance_cosine`
       — sub-ms at corpus scale, future-proof to 1M+ vectors.

Graceful fallback
    If `sqlite-vec` is unavailable (CI without the wheel, fresh dev env),
    falls back to JSON-in-TEXT storage + pure-Python cosine scan. The
    fallback works fine at noc's current scale (~500 vectors, ~10ms
    scan); sqlite-vec just makes it faster + cleaner.

Depth · `KB § PATTERNS/common/kb-vector-search.md`.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path

from settings import REPO_ROOT

# v4.0 N=4 consolidation: helpers now live in _embedding_corpus.
# The module-level aliases below (_chunk_markdown, _embed_sync, _cosine,
# _pack_vec, _connect, _init_schema, _HAS_VEC) preserve back-compat for
# any in-tree caller importing these symbols directly. New code should
# import from _embedding_corpus.
from . import _embedding_corpus as _ec
from ._embedding_corpus import (
    HAS_VEC as _HAS_VEC,
    EMBEDDING_DIM,
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
    sqlite_vec,
)


# ── Paths ────────────────────────────────────────────────────────────────────
from .cache_backend import cache_dir as _cache_dir, cache_path as _cache_path

CACHE_DIR = _cache_dir()
CACHE_PATH = _cache_path("kb-embeddings")
KB_DIR = REPO_ROOT / "KNOWLEDGE-BASE"

# v4.0 N=4 consolidation: the leaf helpers now live in `_embedding_corpus`
# and are imported above. Back-compat aliases below so any caller that
# imported these symbols directly keeps working.
_now_iso = _ec.now_iso
_sha_file = _ec.sha_file


def _connect() -> sqlite3.Connection:
    """Open the kb-embeddings cache (delegates to shared connect_cache)."""
    return _ec.connect_cache(CACHE_PATH)


_pack_vec = _ec.pack_vec


# Schema (kb_chunks + kb_vec + kb_embeddings_json) is owned by the shared
# `_ec.init_schema` — single source of truth (2026-08-14 cache-mirror-
# join-drift fix: creating ONLY the current process's engine table here,
# duplicated from `_embedding_corpus`'s copy, is exactly how the two
# sibling tables drifted out of sync across environments in the first
# place). See `_embedding_corpus.init_schema` + KB § PATTERNS/devops/
# cache-deploy-mirror.md.
def _init_schema(conn: sqlite3.Connection) -> None:
    _ec.init_schema(conn, "kb_chunks", "kb_vec", "kb_embeddings_json")


# v4.0 N=4 consolidation: chunker + embedder now in _embedding_corpus.
_chunk_markdown = _ec.chunk_markdown
_embed_sync = _ec.embed_sync
_embed_batch_sync = _ec.embed_batch_sync
_iter_batches = _ec.iter_batches


# v4.0 N=4 consolidation: cosine now in _embedding_corpus.
_cosine = _ec.cosine


# ── Public API ───────────────────────────────────────────────────────────────
def refresh(force: bool = False, paths: list[str] | None = None) -> dict:
    """Re-populate embeddings. Per-doc source_sha guard short-circuits in-sync
    docs. `paths` limits scope (repo-rel `CONTEXT/...` paths). `force=True`
    rebuilds anyway.

    Returns `{ok, status, refreshed: [paths], skipped: [paths], errors: [...],
    rows_written}`.
    """
    if not KB_DIR.is_dir():
        return {"ok": True, "status": "in-sync", "refreshed": [], "skipped": [], "errors": [], "rows_written": 0}
    conn = _connect()
    _init_schema(conn)

    # Discover .md files in KNOWLEDGE-BASE/.
    all_md = sorted(p for p in KB_DIR.rglob("*.md") if p.is_file())
    if paths:
        targets = [p for p in all_md if str(p.relative_to(KB_DIR)) in paths]
    else:
        targets = all_md

    refreshed: list[str] = []
    skipped: list[str] = []
    errors: list[dict] = []
    total_rows = 0

    # Capture the REAL provider token usage across the whole refresh batch
    # (ground truth for the cost ledger, not the MAX_CHUNK_CHARS//4 estimate).
    _usage = _ec.UsageAccumulator()
    _restore_usage = _ec.install_capture_sink(_usage)

    for md in targets:
        rel = str(md.relative_to(KB_DIR))
        sha = _sha_file(md)
        if not force:
            cur = conn.execute(
                "SELECT DISTINCT source_sha FROM kb_chunks WHERE path=? LIMIT 1",
                (rel,),
            )
            row = cur.fetchone()
            if row and row["source_sha"] == sha:
                skipped.append(rel)
                continue
        # Rebuild this doc's rows — delete from BOTH engines' tables
        # unconditionally (2026-08-14 fix), not just the current process's
        # `_HAS_VEC` branch: a PRIOR refresh of this same doc may have run
        # under a DIFFERENT environment (see `_ec.delete_embedding_rows`).
        cur = conn.execute("SELECT rowid_alias FROM kb_chunks WHERE path=?", (rel,))
        old_rowids = [r[0] for r in cur.fetchall()]
        if old_rowids:
            _ec.delete_embedding_rows(
                conn, vec_table="kb_vec", json_table="kb_embeddings_json",
                rowids=old_rowids,
            )
            conn.execute("DELETE FROM kb_chunks WHERE path=?", (rel,))
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            errors.append({"path": rel, "error": f"read: {e}"})
            continue
        chunks = _chunk_markdown(text)
        if not chunks:
            continue
        now = _now_iso()
        per_doc_ok = True
        per_doc_rowids: list[int] = []
        # Batch the embed calls — ONE HTTP round-trip per `_iter_batches()`
        # slice instead of one PER CHUNK. This is the fix for the 2026-08
        # pre-push retry-storm: kb-embeddings is one of the four OpenAI-
        # backed pre-push refreshes, and a large KB diff used to fire one
        # independently-paced-and-retried request per chunk (mirrors the
        # code_embeddings.py root cause exactly — 508 chunks -> 507 retries
        # observed there, despite OpenAI itself being healthy the whole
        # time). A batch failure fails ALL chunks in that slice together,
        # preserving the existing per-DOC all-or-nothing rollback below (a
        # doc's earlier-batch rows are rolled back too — never partially
        # cached).
        enumerated_chunks = list(enumerate(chunks))
        for batch in _iter_batches(enumerated_chunks):
            batch_texts = [c for _idx, c in batch]
            try:
                vecs = _embed_batch_sync(batch_texts)
            except Exception as e:  # noqa: BLE001 — surface the provider error
                errors.append({
                    "path": rel, "chunk_idx": batch[0][0], "error": str(e)[:200],
                })
                per_doc_ok = False
                break
            if len(vecs) != len(batch):
                errors.append({
                    "path": rel, "chunk_idx": batch[0][0],
                    "error": f"batch embed returned {len(vecs)} vectors for {len(batch)} inputs",
                })
                per_doc_ok = False
                break
            dim_bad = next((i for i, v in enumerate(vecs) if len(v) != EMBEDDING_DIM), None)
            if dim_bad is not None:
                errors.append({
                    "path": rel, "chunk_idx": batch[dim_bad][0],
                    "error": f"unexpected dim {len(vecs[dim_bad])} (want {EMBEDDING_DIM}) — model changed?",
                })
                per_doc_ok = False
                break

            for (idx, chunk), vec in zip(batch, vecs):
                cur = conn.execute(
                    "INSERT INTO kb_chunks(path,chunk_idx,chunk_text,source_sha,cached_at) "
                    "VALUES (?,?,?,?,?)",
                    (rel, idx, chunk, sha, now),
                )
                row_id = cur.lastrowid
                per_doc_rowids.append(row_id)
                if _HAS_VEC:
                    conn.execute(
                        "INSERT INTO kb_vec(rowid, embedding) VALUES (?, ?)",
                        (row_id, _pack_vec(vec)),
                    )
                else:
                    conn.execute(
                        "INSERT INTO kb_embeddings_json(chunk_rowid, embedding) VALUES (?, ?)",
                        (row_id, json.dumps(vec)),
                    )
                total_rows += 1
        if not per_doc_ok and per_doc_rowids:
            # all-or-nothing per doc — roll back the partial inserts.
            _ec.delete_embedding_rows(
                conn, vec_table="kb_vec", json_table="kb_embeddings_json",
                rowids=per_doc_rowids,
            )
            conn.execute("DELETE FROM kb_chunks WHERE path=?", (rel,))
            total_rows -= len(per_doc_rowids)
            continue
        refreshed.append(rel)

    # Orphan prune (full passes only): drop rows for docs no longer on disk
    # (e.g. the seven-way-sync.md → eight-way-sync.md rename). Shared helper; a
    # scoped refresh (`paths=...`) must NOT prune — it only knows its own subset.
    pruned: list[str] = []
    if not paths:
        pruned = _ec.prune_orphan_chunks(
            conn,
            chunks_table="kb_chunks",
            vec_table="kb_vec",
            json_table="kb_embeddings_json",
            live_rels={str(p.relative_to(KB_DIR)) for p in all_md},
        )

    conn.execute(
        "INSERT OR REPLACE INTO cache_meta(key,value) VALUES (?,?)",
        ("populated_at", _now_iso()),
    )
    conn.commit()
    conn.close()
    _restore_usage()
    status = "in-sync" if not refreshed else ("rebuilt" if not errors else "partial")

    # ── Cost instrumentation (ADDITIVE — does not modify existing logic) ───────
    # Log embedding work to the durable vector-costs ledger. Skipped when
    # total_rows == 0 (in-sync, no API calls). Wrapped — never blocks refresh.
    if total_rows > 0:
        try:
            from tools.noctus.dev import vector_costs as _vc
            _estimated_tokens = total_rows * (MAX_CHUNK_CHARS // 4)
            _actual_tokens = _usage.total_tokens if _usage.has_data else None
            _actual_cost = _usage.cost_usd if _usage.has_data else None
            _vc.log_refresh_batch(
                namespace="kb-embeddings",
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
                "kb_embeddings: vector_costs instrumentation failed: %s", _vc_exc
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


def search(query: str, top_k: int = 5, min_score: float = 0.0) -> list[dict]:
    """Embed `query`, return the top-K matching KB chunks by cosine similarity.

    Returns: `[{path, chunk_idx, chunk_text, score, engine}]` ordered by
    score desc. Lazy-degrade: empty list if cache missing or embedding API
    unreachable.

    Engine selection: when sqlite-vec is loaded, uses the native vec0 KNN
    (`MATCH ?` + `LIMIT k`). Otherwise falls back to pure-Python cosine
    scan over the JSON column.
    """
    if not CACHE_PATH.exists():
        return []
    try:
        q_vec = _embed_sync(query)
    except Exception:
        # Advisory layer — fail silently on provider issues.
        return []
    conn = _connect()
    _init_schema(conn)
    results: list[dict] = []
    if _HAS_VEC:
        # Fast path: vec0 native KNN. `vec_distance_cosine` returns DISTANCE
        # (0 = identical, 2 = opposite); convert to similarity (1 - dist/2).
        q_blob = _pack_vec(q_vec)
        cur = conn.execute(
            """
            SELECT c.path, c.chunk_idx, c.chunk_text, v.distance
            FROM kb_vec v
            JOIN kb_chunks c ON c.rowid_alias = v.rowid
            WHERE v.embedding MATCH ?
              AND k = ?
            ORDER BY v.distance
            """,
            (q_blob, top_k),
        )
        for r in cur.fetchall():
            # sqlite-vec MATCH returns L2 distance for float[]; convert to
            # a cosine-shaped similarity. For normalized embeddings (which
            # OpenAI text-embedding-3-* are NOT pre-normalized — but the
            # ordering is still correct), this is an approximation. Caller
            # uses it for ranking, not for an absolute threshold.
            distance = float(r["distance"])
            score = 1.0 / (1.0 + distance)  # monotonic transform; preserves ordering
            if score >= min_score:
                results.append({
                    "path": r["path"], "chunk_idx": r["chunk_idx"],
                    "chunk_text": r["chunk_text"], "score": score,
                    "engine": "sqlite-vec",
                })
    else:
        # Fallback path: scan + pure-Python cosine.
        rows = conn.execute(
            """
            SELECT c.path, c.chunk_idx, c.chunk_text, j.embedding
            FROM kb_chunks c
            JOIN kb_embeddings_json j ON j.chunk_rowid = c.rowid_alias
            """
        ).fetchall()
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
                    "chunk_text": r["chunk_text"], "score": score,
                    "engine": "pure-python",
                }))
        scored.sort(key=lambda t: t[0], reverse=True)
        results = [d for _, d in scored[:top_k]]
    conn.close()
    return results


def list_docs() -> list[str]:
    """Distinct paths cached. Useful for verifying coverage."""
    if not CACHE_PATH.exists():
        return []
    conn = _connect()
    _init_schema(conn)
    cur = conn.execute("SELECT DISTINCT path FROM kb_chunks ORDER BY path")
    out = [r["path"] for r in cur.fetchall()]
    conn.close()
    return out


def get_source_sha(path: str) -> tuple[str, str | None]:
    """Return (live_sha, cached_sha) for a KB doc. Supports the freshness keeper.

    `path` is repo-rel (`CONTEXT/...`); cached_sha is None when no rows.
    """
    md = KB_DIR / path
    live = _sha_file(md)
    cached: str | None = None
    if CACHE_PATH.exists():
        try:
            # Reuse the module's pragma-applying helper (WAL + busy_timeout) —
            # a raw sqlite3.connect() here would skip busy_timeout and raise
            # `database is locked` under writer contention. KB § PATTERNS/common/cache-locking-discipline.md.
            conn = _connect()
            cur = conn.execute(
                "SELECT DISTINCT source_sha FROM kb_chunks WHERE path=? LIMIT 1",
                (path,),
            )
            row = cur.fetchone()
            cached = row[0] if row else None
            conn.close()
        except sqlite3.Error:
            cached = None
    return live, cached


def active_engine() -> str:
    """Return 'sqlite-vec' (fast path active) or 'pure-python' (fallback)."""
    return "sqlite-vec" if _HAS_VEC else "pure-python"


# ── Organizational tools (vector-empowered KB management) ──────────────────
# These build on the embeddings cache to deliver concrete value beyond
# search: validate the manual ownership claims, surface semantic neighbors,
# pre-author radar. KB stays canonical in markdown; the vector layer is
# an ENRICHMENT, not a replacement (user mandate 2026-05-26).

def _load_all_chunk_vectors() -> list[tuple[str, int, str, list[float]]]:
    """Internal: load every (path, chunk_idx, chunk_text, vector) from the cache.
    Handles both engines transparently. Used by the organizational tools.
    """
    if not CACHE_PATH.exists():
        return []
    conn = _connect()
    _init_schema(conn)
    out: list[tuple[str, int, str, list[float]]] = []
    if _HAS_VEC:
        cur = conn.execute(
            """
            SELECT c.path, c.chunk_idx, c.chunk_text, v.embedding
            FROM kb_chunks c JOIN kb_vec v ON v.rowid = c.rowid_alias
            """
        )
        for r in cur.fetchall():
            # Unpack the float32 BLOB.
            blob = r["embedding"]
            vec = list(struct.unpack(f"{len(blob)//4}f", blob))
            out.append((r["path"], r["chunk_idx"], r["chunk_text"], vec))
    else:
        cur = conn.execute(
            """
            SELECT c.path, c.chunk_idx, c.chunk_text, j.embedding
            FROM kb_chunks c JOIN kb_embeddings_json j ON j.chunk_rowid = c.rowid_alias
            """
        )
        for r in cur.fetchall():
            try:
                vec = json.loads(r["embedding"])
            except (json.JSONDecodeError, TypeError):
                continue
            out.append((r["path"], r["chunk_idx"], r["chunk_text"], vec))
    conn.close()
    return out


def _doc_centroid(rows: list[tuple[str, int, str, list[float]]], path: str) -> list[float] | None:
    """Compute the centroid (average vector) of all chunks belonging to `path`.
    Returns None if no chunks for that path."""
    vecs = [vec for p, _, _, vec in rows if p == path]
    if not vecs:
        return None
    dim = len(vecs[0])
    centroid = [0.0] * dim
    for v in vecs:
        for i in range(dim):
            centroid[i] += v[i]
    n = len(vecs)
    return [x / n for x in centroid]


def kb_neighbors(path: str, top_k: int = 5) -> list[dict]:
    """Return top-K semantically nearest KB docs to `path` (excluding itself).

    Powers auto-generated "see also" / Composes-with suggestions. Useful
    when authoring or refactoring a doc — finds related territory
    automatically instead of relying on hand-curated cross-refs.

    Returns: `[{path, score, shared_subfolder}]` ordered by similarity desc.
    """
    rows = _load_all_chunk_vectors()
    if not rows:
        return []
    src_centroid = _doc_centroid(rows, path)
    if src_centroid is None:
        return []
    # Compute target-doc centroids.
    paths = sorted({p for p, _, _, _ in rows if p != path})
    scored: list[tuple[float, dict]] = []
    for target in paths:
        tgt_centroid = _doc_centroid(rows, target)
        if tgt_centroid is None:
            continue
        score = _cosine(src_centroid, tgt_centroid)
        scored.append((score, {
            "path": target,
            "score": score,
            "shared_subfolder": target.split("/")[2] == path.split("/")[2] if "/" in target and "/" in path else False,
        }))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [d for _, d in scored[:top_k]]


def kb_similar(text: str, top_k: int = 5) -> list[dict]:
    """Pre-authoring radar — given free text (a draft title, summary, or
    paragraph), return top-K semantically similar existing KB chunks.

    Use case: BEFORE writing a new KB pattern, run this against your
    proposed intro. If existing patterns score >0.7 similarity, extend one
    of those instead of authoring a new one (combats KB-doc drift toward
    many small overlapping patterns).

    Returns: same shape as `search()`.
    """
    return search(text, top_k=top_k)


def kb_validate_owns_kb() -> list[dict]:
    """Audit the per-agent `owns_kb:` claims against semantic centroids.

    For each agent, compute a centroid = average vector of all chunks in
    its owned KB docs. For each owned doc, measure cosine similarity to
    its agent's centroid AND to every other agent's centroid. Flag docs
    where another agent's centroid is closer — a signal that the doc
    might be mis-owned.

    This is an ADVISORY tool — the manual `owns_kb` decisions are still
    canonical. The keeper `check_agent_kb_alignment` enforces the rules;
    this tool surfaces signals for human review.

    Returns: list of finding dicts ordered by "drift severity":
      {path, current_owner, suggested_owner, current_score, suggested_score,
       drift: current_score - suggested_score (negative ⇒ mis-owned)}
    """
    # Parse owns_kb declarations from agent files.
    agents_dir = REPO_ROOT / ".claude" / "agents"
    if not agents_dir.is_dir():
        return []
    owners: dict[str, list[str]] = {}  # agent_name → [owned KB paths]
    for agent_md in sorted(agents_dir.glob("*.md")):
        try:
            text = agent_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Reuse the compliance.py parser to stay aligned.
        try:
            from tools.noctus.dev.compliance import _parse_frontmatter_owns_kb
        except ImportError:
            return []
        paths = _parse_frontmatter_owns_kb(text) or []
        if paths:
            owners[agent_md.stem] = paths

    rows = _load_all_chunk_vectors()
    if not rows or not owners:
        return []

    # Compute centroid per agent (average over all their owned docs' chunks).
    agent_centroids: dict[str, list[float]] = {}
    for agent, paths in owners.items():
        agent_chunks = [vec for p, _, _, vec in rows if p in paths]
        if not agent_chunks:
            continue
        dim = len(agent_chunks[0])
        centroid = [0.0] * dim
        for v in agent_chunks:
            for i in range(dim):
                centroid[i] += v[i]
        n = len(agent_chunks)
        agent_centroids[agent] = [x / n for x in centroid]

    # For each owned doc, score it against every centroid; flag mis-owned.
    findings: list[dict] = []
    for owner_agent, paths in owners.items():
        if owner_agent not in agent_centroids:
            continue
        for path in paths:
            doc_centroid = _doc_centroid(rows, path)
            if doc_centroid is None:
                continue
            scores = {
                a: _cosine(doc_centroid, c)
                for a, c in agent_centroids.items()
            }
            current_score = scores.get(owner_agent, 0.0)
            best_other = max(
                ((a, s) for a, s in scores.items() if a != owner_agent),
                key=lambda t: t[1],
                default=(None, 0.0),
            )
            suggested_owner, suggested_score = best_other
            drift = current_score - suggested_score
            if drift < 0:  # mis-owned: another agent's centroid is closer
                findings.append({
                    "path": path,
                    "current_owner": owner_agent,
                    "current_score": current_score,
                    "suggested_owner": suggested_owner,
                    "suggested_score": suggested_score,
                    "drift": drift,
                })
    findings.sort(key=lambda f: f["drift"])  # most-mis-owned first
    return findings


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.kb_search",
        description=(
            "Semantic search over the KB — fourth keeper-mirror cache, "
            "ADDITIVE to grep / owns_kb / INDEX.md (which stay canonical). "
            "Embeds the query, returns top-K KB chunks by cosine similarity. "
            "Use for fuzzy-intent queries ('find patterns about cross-product "
            "state management') where exact terminology is unknown. For "
            "named patterns / specific files, use grep + INDEX.md instead. "
            "Graceful-degrades to empty result if the embedding provider is "
            "unreachable (advisory layer, not blocking). "
            "KB § PATTERNS/common/kb-vector-search.md."
        ),
    )
    def _search(query: str, top_k: int = 5, min_score: float = 0.0) -> list[dict]:
        return search(query, top_k=top_k, min_score=min_score)

    @server.tool(
        name="noctus.dev.kb_embeddings_refresh",
        description=(
            "Re-populate the KB embeddings cache from `KNOWLEDGE-BASE/**/*.md`. "
            "Per-doc source_sha guard short-circuits in-sync docs; "
            "`paths=[...]` limits scope; `force=True` rebuilds anyway. "
            "Auto-run by pre-commit on KB doc change. Calls OpenAI "
            "text-embedding-3-small via `noctusai_lib.integrations.llm` "
            "(no new external dep — same provider as the ERP embedding "
            "system)."
        ),
    )
    def _refresh(force: bool = False, paths: list[str] | None = None) -> dict:
        return refresh(force=force, paths=paths)

    @server.tool(
        name="noctus.dev.kb_embeddings_list",
        description=(
            "Distinct KB paths currently in the embeddings cache. Useful "
            "for verifying coverage after a refresh."
        ),
    )
    def _list() -> list[str]:
        return list_docs()

    @server.tool(
        name="noctus.dev.kb_neighbors",
        description=(
            "Find top-K semantically nearest KB docs to a given path. "
            "Powers auto-generated 'see also' / Composes-with suggestions. "
            "Useful when authoring or refactoring a doc — surfaces related "
            "territory automatically. Returns "
            "[{path, score, shared_subfolder}] ordered desc by similarity. "
            "KB § PATTERNS/common/kb-vector-search.md."
        ),
    )
    def _neighbors(path: str, top_k: int = 5) -> list[dict]:
        return kb_neighbors(path, top_k=top_k)

    @server.tool(
        name="noctus.dev.kb_similar",
        description=(
            "Pre-authoring radar — given free text (draft title / summary "
            "/ paragraph), return top-K semantically similar existing KB "
            "chunks. Use BEFORE writing a new KB pattern: if existing "
            "patterns score >0.7 similarity, extend one of those instead "
            "of authoring a new one (combats KB-doc drift toward many "
            "small overlapping patterns)."
        ),
    )
    def _similar(text: str, top_k: int = 5) -> list[dict]:
        return kb_similar(text, top_k=top_k)

    @server.tool(
        name="noctus.dev.kb_validate_owns_kb",
        description=(
            "Audit the per-agent `owns_kb:` claims against semantic "
            "centroids. For each agent, compute centroid = avg vector of "
            "all chunks in its owned KB docs. For each owned doc, score "
            "it against every agent's centroid; flag docs where another "
            "agent's centroid is closer (potential mis-ownership). "
            "Advisory only — the manual decisions stay canonical. "
            "Returns findings ordered by drift severity (most-mis-owned first)."
        ),
    )
    def _validate() -> list[dict]:
        return kb_validate_owns_kb()


__all__ = [
    "CACHE_PATH",
    "MAX_CHUNK_CHARS",
    "MIN_CHUNK_CHARS",
    "EMBEDDING_DIM",
    "refresh",
    "search",
    "list_docs",
    "get_source_sha",
    "active_engine",
    "kb_neighbors",
    "kb_similar",
    "kb_validate_owns_kb",
    "register",
]
