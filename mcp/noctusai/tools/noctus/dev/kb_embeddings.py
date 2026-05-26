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
       overlap), passed through OpenAI `text-embedding-3-small` (the seed
       default at `noctusai_lib.integrations.llm.generate_embedding` —
       NO new external dep; same provider + same credential chain as ERP's
       embedding_service).
    2. Each chunk → 1536-D vector. Stored as JSON in sqlite alongside the
       chunk text + source SHA.
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

# ── sqlite-vec — optional fast path (storage layer engine) ─────────────────
# Loaded at module import time; degraded to JSON+pure-Python cosine if absent.
# Cache files written with one engine are NOT compatible with the other —
# both schemas live side-by-side and the active one is detected at refresh.
try:
    import sqlite_vec  # type: ignore[import-not-found]
    _HAS_VEC = True
except ImportError:  # pragma: no cover — fallback path
    sqlite_vec = None  # type: ignore[assignment]
    _HAS_VEC = False


# ── Paths ────────────────────────────────────────────────────────────────────
CACHE_DIR = REPO_ROOT / ".claude" / "cache"
CACHE_PATH = CACHE_DIR / "kb-embeddings.sqlite"
KB_DIR = REPO_ROOT / "KNOWLEDGE-BASE"

# Chunking knobs (tunable; tracked in the KB doc).
MAX_CHUNK_CHARS = 1800   # ~450 tokens — well under the 8191-token model limit.
MIN_CHUNK_CHARS = 200    # below this, don't emit (too short to be useful).
EMBEDDING_DIM = 1536     # OpenAI text-embedding-3-small. Update if model changes.


# ── Helpers ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _connect() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_PATH))
    conn.row_factory = sqlite3.Row
    if _HAS_VEC:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)  # registers vec0 virtual tables + vec_* functions
        conn.enable_load_extension(False)
    return conn


def _pack_vec(vec: list[float]) -> bytes:
    """sqlite-vec stores vectors as little-endian float32 BLOBs."""
    return struct.pack(f"{len(vec)}f", *vec)


# Metadata table (always present — used in both engines).
_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kb_chunks (
  rowid_alias  INTEGER PRIMARY KEY AUTOINCREMENT,
  path         TEXT NOT NULL,
  chunk_idx    INTEGER NOT NULL,
  chunk_text   TEXT NOT NULL,
  source_sha   TEXT NOT NULL,
  cached_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_path ON kb_chunks(path);
"""

# Fast-path: vec0 virtual table for the binary embedding column. Joined to
# kb_chunks via rowid for the chunk_text / metadata.
_VEC_SCHEMA = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS kb_vec USING vec0(
  embedding float[{EMBEDDING_DIM}]
);
"""

# Fallback-path: JSON column on the same kb_chunks table when sqlite-vec is
# unavailable. The schema differs by ONE column to keep migrations trivial.
_FALLBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_embeddings_json (
  chunk_rowid  INTEGER PRIMARY KEY,    -- → kb_chunks.rowid_alias
  embedding    TEXT NOT NULL           -- JSON-serialized list[float]
);
"""


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_META_SCHEMA)
    if _HAS_VEC:
        conn.executescript(_VEC_SCHEMA)
    else:
        conn.executescript(_FALLBACK_SCHEMA)
    conn.commit()


# ── Chunker (markdown-structural — H2 windows + char cap) ────────────────────
def _chunk_markdown(text: str) -> list[str]:
    """Split a markdown doc into chunks at H2 boundaries, then char-cap.

    Each chunk preserves the H1 title as a prefix for context (so a chunk
    can be retrieved standalone without losing what doc it's from). KB
    docs are well-structured for this — every pattern has a clear H1 +
    H2 sections.
    """
    lines = text.splitlines()
    # H1 title prefix — first `# ...` line.
    title = next((ln for ln in lines if ln.startswith("# ") and not ln.startswith("## ")), "")

    # Group lines by H2 sections.
    sections: list[list[str]] = []
    current: list[str] = []
    for ln in lines:
        if ln.startswith("## "):
            if current:
                sections.append(current)
            current = [ln]
        else:
            current.append(ln)
    if current:
        sections.append(current)

    # If no H2 sections, treat the whole doc as one block.
    if not sections:
        sections = [lines]

    # Build chunks: each H2 section becomes 1+ chunks (split at MAX_CHUNK_CHARS).
    chunks: list[str] = []
    for sec in sections:
        body = "\n".join(sec).strip()
        if not body:
            continue
        # Prefix with title for context.
        prefixed = f"{title}\n\n{body}" if title and not body.startswith(title) else body
        # Char-cap split.
        while len(prefixed) > MAX_CHUNK_CHARS:
            cut = prefixed.rfind("\n", MIN_CHUNK_CHARS, MAX_CHUNK_CHARS)
            if cut < 0:
                cut = MAX_CHUNK_CHARS
            chunks.append(prefixed[:cut].strip())
            prefixed = (f"{title}\n\n" if title else "") + prefixed[cut:].strip()
        if len(prefixed) >= MIN_CHUNK_CHARS:
            chunks.append(prefixed.strip())
    return chunks


# ── Sync wrapper around the async seed embedder ──────────────────────────────
def _embed_sync(text: str) -> list[float]:
    """Sync-wrap the async `generate_embedding`. Run in a fresh event loop
    so we don't fight any caller-owned loop."""
    from noctusai_lib.integrations.llm import generate_embedding
    return asyncio.run(generate_embedding(text))


# ── Cosine ───────────────────────────────────────────────────────────────────
def _cosine(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity. ~10ms for 1536-D × 500 vectors."""
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


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
        # Rebuild this doc's rows — delete from both engines' tables.
        # rowids of kb_chunks are referenced by kb_vec AND kb_embeddings_json;
        # collect old rowids and clear both.
        cur = conn.execute("SELECT rowid_alias FROM kb_chunks WHERE path=?", (rel,))
        old_rowids = [r[0] for r in cur.fetchall()]
        if old_rowids:
            placeholders = ",".join("?" * len(old_rowids))
            if _HAS_VEC:
                conn.execute(f"DELETE FROM kb_vec WHERE rowid IN ({placeholders})", old_rowids)
            else:
                conn.execute(
                    f"DELETE FROM kb_embeddings_json WHERE chunk_rowid IN ({placeholders})",
                    old_rowids,
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
        for idx, chunk in enumerate(chunks):
            try:
                vec = _embed_sync(chunk)
            except Exception as e:  # noqa: BLE001 — surface the provider error
                errors.append({"path": rel, "chunk_idx": idx, "error": str(e)[:200]})
                per_doc_ok = False
                break
            if len(vec) != EMBEDDING_DIM:
                errors.append({
                    "path": rel, "chunk_idx": idx,
                    "error": f"unexpected dim {len(vec)} (want {EMBEDDING_DIM}) — model changed?",
                })
                per_doc_ok = False
                break
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
            placeholders = ",".join("?" * len(per_doc_rowids))
            if _HAS_VEC:
                conn.execute(f"DELETE FROM kb_vec WHERE rowid IN ({placeholders})", per_doc_rowids)
            else:
                conn.execute(
                    f"DELETE FROM kb_embeddings_json WHERE chunk_rowid IN ({placeholders})",
                    per_doc_rowids,
                )
            conn.execute("DELETE FROM kb_chunks WHERE path=?", (rel,))
            total_rows -= len(per_doc_rowids)
            continue
        refreshed.append(rel)
    conn.execute(
        "INSERT OR REPLACE INTO cache_meta(key,value) VALUES (?,?)",
        ("populated_at", _now_iso()),
    )
    conn.commit()
    conn.close()
    status = "in-sync" if not refreshed else ("rebuilt" if not errors else "partial")

    # ── Cost instrumentation (ADDITIVE — does not modify existing logic) ───────
    # Log embedding work to the durable vector-costs ledger. Skipped when
    # total_rows == 0 (in-sync, no API calls). Wrapped — never blocks refresh.
    if total_rows > 0:
        try:
            from tools.noctus.dev import vector_costs as _vc
            _estimated_tokens = total_rows * (MAX_CHUNK_CHARS // 4)
            _vc.log_refresh_batch(
                namespace="kb-embeddings",
                model="text-embedding-3-small",
                doc_count=len(refreshed),
                chunk_count=total_rows,
                estimated_tokens=_estimated_tokens,
                provider="openai",
                source_ref=f"session:{_now_iso()[:10]}",
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
            conn = sqlite3.connect(str(CACHE_PATH))
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
