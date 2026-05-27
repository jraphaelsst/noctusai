"""memory-embeddings — 6th keeper-mirror cache.

Indexes the OUT-OF-REPO agent memory directory (`MEMORY.md` + every
`*.md` under `~/.claude/projects/<workspace>/memory/`) so semantic
search over accumulated feedback / project / reference notes works.

Why this cache exists
    Memory is auto-loaded every session and grows continuously (today
    ~50 feedback files). The platform already does semantic search over
    KB + code via `kb_embeddings` + `code_embeddings`; memory was the
    missing third corpus — every "have we seen this pattern before"
    query went un-served. v4.0 closes that gap.

Out-of-repo source
    The agent memory lives at `~/.claude/projects/<workspace>/memory/`
    (workspace = the platform's per-project Claude Code store). The
    workspace dir is resolved at refresh time via the
    `NOCTUS_AGENT_MEMORY_DIR` env override, OR by scanning
    `~/.claude/projects/*/memory/` for the dir whose `MEMORY.md`
    references this repo. Configurable; defaults work for the
    operator's machine.

Mirror to prod
    Same contract as kb-embeddings: snapshot to prod pgvector via
    `cache_deploy_mirror`. The cache TABLE on disk is local; the prod
    mirror table is `cache_memory_embeddings`.

Reuses kb_embeddings helpers (chunker / embedder / cosine / pack) to
avoid duplicating the embedding infrastructure. NOC-REMEDIATE[embedding-
cache-framework]: consolidate the 4 embedding-cache modules into a
generic framework when this hits N=4 (today: kb + code + memory +
corpus = N=4, formalization owed in v4.1).

KB § PATTERNS/common/memory-embeddings.md.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path

from settings import REPO_ROOT

# Reuse the shared embedding infrastructure from kb_embeddings.
from .kb_embeddings import (
    EMBEDDING_DIM,
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
    _HAS_VEC,
    _chunk_markdown,
    _cosine,
    _embed_sync,
    _pack_vec,
)

try:
    import sqlite_vec  # type: ignore[import-not-found]
except ImportError:
    sqlite_vec = None  # type: ignore[assignment]


# ── Paths ────────────────────────────────────────────────────────────────────
CACHE_DIR = REPO_ROOT / ".claude" / "cache"
CACHE_PATH = CACHE_DIR / "memory-embeddings.sqlite"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _primary_checkout_root() -> Path:
    """Return the PRIMARY git worktree root (not a linked worktree).
    Memory belongs to the logical project; linked worktrees share it.
    Falls back to REPO_ROOT if `git worktree list` fails."""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        for line in out.stdout.splitlines():
            if line.startswith("worktree "):
                return Path(line[len("worktree "):])  # first match = primary
    except (OSError, subprocess.SubprocessError):
        pass
    return REPO_ROOT


def _resolve_memory_dir() -> Path | None:
    """Locate the agent memory dir. Four-tier:
      1. `NOCTUS_AGENT_MEMORY_DIR` env override (explicit).
      2. Path-slug derivation against PRIMARY checkout (linked worktrees
         share memory): Claude Code names workspaces with `/` → `-`.
      3. Scan `~/.claude/projects/*/memory/` for a dir matching this
         repo's basename (loose fallback).
      4. Return None — refresh becomes a no-op.
    """
    env = os.environ.get("NOCTUS_AGENT_MEMORY_DIR")
    if env:
        p = Path(env).expanduser().resolve()
        return p if p.is_dir() else None

    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return None

    primary = _primary_checkout_root()
    repo_slug = str(primary).replace("/", "-")
    expected = base / repo_slug / "memory"
    if expected.is_dir():
        return expected

    repo_basename = primary.name.lower()
    candidates = sorted(base.glob("*/memory"))
    for c in candidates:
        if repo_basename in c.parent.name.lower() and "knowledge-extractor" not in c.parent.name.lower():
            return c

    return None


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _connect() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_PATH))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    if _HAS_VEC:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    return conn


_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_chunks (
  rowid_alias  INTEGER PRIMARY KEY AUTOINCREMENT,
  path         TEXT NOT NULL,
  chunk_idx    INTEGER NOT NULL,
  chunk_text   TEXT NOT NULL,
  source_sha   TEXT NOT NULL,
  cached_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_chunks_path ON memory_chunks(path);
"""

_VEC_SCHEMA = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING vec0(
  embedding float[{EMBEDDING_DIM}]
);
"""

_FALLBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_embeddings_json (
  chunk_rowid  INTEGER PRIMARY KEY,
  embedding    TEXT NOT NULL
);
"""


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_META_SCHEMA)
    if _HAS_VEC:
        conn.executescript(_VEC_SCHEMA)
    else:
        conn.executescript(_FALLBACK_SCHEMA)
    conn.commit()


def refresh(force: bool = False, paths: list[str] | None = None) -> dict:
    """Re-populate memory embeddings. Out-of-repo source — graceful no-op
    when the memory dir isn't resolvable (fresh clone, no Claude Code
    session, etc.).

    Returns `{ok, status, refreshed: [paths], skipped: [paths], errors,
    rows_written}`.
    """
    mem_dir = _resolve_memory_dir()
    if mem_dir is None:
        return {
            "ok": True, "status": "no-memory-dir",
            "refreshed": [], "skipped": [], "errors": [], "rows_written": 0,
            "message": (
                "agent memory dir not found — set NOCTUS_AGENT_MEMORY_DIR "
                "or run from a session whose ~/.claude/projects/*/memory/ "
                "exists."
            ),
        }

    conn = _connect()
    _init_schema(conn)

    all_md = sorted(p for p in mem_dir.glob("*.md") if p.is_file())
    if paths:
        targets = [p for p in all_md if str(p.relative_to(mem_dir)) in paths]
    else:
        targets = all_md

    refreshed: list[str] = []
    skipped: list[str] = []
    errors: list[dict] = []
    total_rows = 0

    for md in targets:
        rel = str(md.relative_to(mem_dir))
        sha = _sha_file(md)
        if not force:
            cur = conn.execute(
                "SELECT DISTINCT source_sha FROM memory_chunks WHERE path=? LIMIT 1",
                (rel,),
            )
            row = cur.fetchone()
            if row and row["source_sha"] == sha:
                skipped.append(rel)
                continue
        # Wipe old rows for this doc.
        cur = conn.execute("SELECT rowid_alias FROM memory_chunks WHERE path=?", (rel,))
        old_rowids = [r[0] for r in cur.fetchall()]
        if old_rowids:
            placeholders = ",".join("?" * len(old_rowids))
            if _HAS_VEC:
                conn.execute(f"DELETE FROM memory_vec WHERE rowid IN ({placeholders})", old_rowids)
            else:
                conn.execute(
                    f"DELETE FROM memory_embeddings_json WHERE chunk_rowid IN ({placeholders})",
                    old_rowids,
                )
            conn.execute("DELETE FROM memory_chunks WHERE path=?", (rel,))

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
            cur = conn.execute(
                "INSERT INTO memory_chunks(path,chunk_idx,chunk_text,source_sha,cached_at) "
                "VALUES (?,?,?,?,?)",
                (rel, idx, chunk, sha, now),
            )
            row_id = cur.lastrowid
            per_doc_rowids.append(row_id)
            if _HAS_VEC:
                conn.execute(
                    "INSERT INTO memory_vec(rowid, embedding) VALUES (?, ?)",
                    (row_id, _pack_vec(vec)),
                )
            else:
                conn.execute(
                    "INSERT INTO memory_embeddings_json(chunk_rowid, embedding) VALUES (?, ?)",
                    (row_id, json.dumps(vec)),
                )
            total_rows += 1
        if not per_doc_ok and per_doc_rowids:
            placeholders = ",".join("?" * len(per_doc_rowids))
            if _HAS_VEC:
                conn.execute(f"DELETE FROM memory_vec WHERE rowid IN ({placeholders})", per_doc_rowids)
            else:
                conn.execute(
                    f"DELETE FROM memory_embeddings_json WHERE chunk_rowid IN ({placeholders})",
                    per_doc_rowids,
                )
            conn.execute("DELETE FROM memory_chunks WHERE path=?", (rel,))
        if per_doc_ok:
            refreshed.append(rel)

    # Write aggregate source_sha into cache_meta for freshness checks.
    try:
        conn.execute(
            "INSERT OR REPLACE INTO cache_meta(key, value) VALUES ('source_sha', ?)",
            (cache_source_sha(),),
        )
    except sqlite3.OperationalError:
        pass

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


def search(query: str, top_k: int = 5, min_score: float = 0.0) -> list[dict]:
    """Embed `query`, return top-K memory chunks by cosine similarity.

    Returns: `[{path, chunk_idx, chunk_text, score}]` ordered by score
    desc. Lazy-degrade: empty list if cache missing or embedding API
    unreachable.
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
        cur = conn.execute(
            """
            SELECT c.path, c.chunk_idx, c.chunk_text, v.distance
            FROM memory_vec v
            JOIN memory_chunks c ON c.rowid_alias = v.rowid
            WHERE v.embedding MATCH ?
              AND k = ?
            ORDER BY v.distance
            """,
            (q_blob, top_k),
        )
        for r in cur.fetchall():
            score = 1.0 / (1.0 + float(r["distance"]))
            if score >= min_score:
                results.append({
                    "path": r["path"], "chunk_idx": r["chunk_idx"],
                    "chunk_text": r["chunk_text"], "score": score,
                    "engine": "sqlite-vec",
                })
    else:
        rows = conn.execute(
            """
            SELECT c.path, c.chunk_idx, c.chunk_text, j.embedding
            FROM memory_chunks c
            JOIN memory_embeddings_json j ON j.chunk_rowid = c.rowid_alias
            """
        ).fetchall()
        scored = []
        for r in rows:
            try:
                v = json.loads(r["embedding"])
            except (TypeError, ValueError):
                continue
            score = _cosine(q_vec, v)
            if score >= min_score:
                scored.append((score, r))
        scored.sort(key=lambda t: t[0], reverse=True)
        for score, r in scored[:top_k]:
            results.append({
                "path": r["path"], "chunk_idx": r["chunk_idx"],
                "chunk_text": r["chunk_text"], "score": score,
                "engine": "fallback-cosine",
            })
    conn.close()
    return results


def cache_source_sha() -> str:
    """Aggregate sha of every memory file content — change-detection token
    used by the freshness keeper + post-merge / post-checkout hooks."""
    mem_dir = _resolve_memory_dir()
    if mem_dir is None:
        return ""
    h = hashlib.sha256()
    for p in sorted(mem_dir.glob("*.md")):
        if p.is_file():
            h.update(p.name.encode("utf-8"))
            h.update(b"\0")
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


def register(server) -> None:
    @server.tool(
        name="noctus.dev.refresh_memory_embeddings",
        description=(
            "Re-populate the memory-embeddings cache from the out-of-repo "
            "agent memory dir (`~/.claude/projects/<workspace>/memory/`). "
            "Per-file source_sha guard skips unchanged. Returns "
            "{ok, status, refreshed, skipped, errors, rows_written}."
        ),
    )
    def _refresh_memory_embeddings(force: bool = False, paths: list[str] | None = None) -> dict:
        return refresh(force=force, paths=paths)

    @server.tool(
        name="noctus.dev.memory_search",
        description=(
            "Semantic search over agent memory (feedback / reference / "
            "project notes). Returns top-K chunks by cosine similarity. "
            "Use for 'have we seen this pattern' lookups."
        ),
    )
    def _memory_search(query: str, top_k: int = 5, min_score: float = 0.0) -> list:
        return search(query, top_k=top_k, min_score=min_score)


__all__ = ["refresh", "search", "cache_source_sha", "register",
           "CACHE_PATH", "_resolve_memory_dir"]
