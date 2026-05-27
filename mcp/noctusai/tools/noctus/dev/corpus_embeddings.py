"""corpus-embeddings — 7th keeper-mirror cache.

Indexes the heterogeneous "everything else we read but isn't KB or code":

  - CHANGELOG.md            (when present)
  - templates/**/*.md       (PROJECT-TEMPLATE / PROPOSAL-TEMPLATE / etc.)
  - .claude/agents/*.md     (FULL body — L1 extract already in agent-context)
  - .claude/skills/**/SKILL.md
  - project-history/PROJECT-HISTORY.md (when present)

Each chunk row carries a `source_type` column (`changelog` / `template`
/ `agent` / `skill` / `history`) so semantic search can scope or
distinguish hits.

Why this cache exists (v4.0)
    Searchable corpus inventory: KB ✓, code ✓, memory ✓ (new), but the
    in-repo docs that AREN'T KB had no semantic surface. Now an agent
    can ask "which template covers X" / "which skill auto-triggers on Y"
    / "what was decided in PROJECT-HISTORY about Z" and get a real
    ranked answer instead of grep-and-pray.

Excluded by design (per user mandate):
  - projects/<slug>/PROJECT.md   — ephemeral, you're working on it
  - source code                  — already in code-embeddings
  - .claude/commands/<name>.md   — user-invoked only, low value

Mirror to prod
    Same contract as the other 6 keeper-mirror caches. Mirror table:
    `cache_corpus_embeddings` (wider — carries source_type).

Reuses kb_embeddings helpers (chunker / embedder / cosine / pack) — the
v4.0 N=4 duplication is marked NOC-REMEDIATE[embedding-cache-framework]
for v4.1 consolidation.

KB § PATTERNS/common/corpus-embeddings.md.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from settings import REPO_ROOT

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


CACHE_DIR = REPO_ROOT / ".claude" / "cache"
CACHE_PATH = CACHE_DIR / "corpus-embeddings.sqlite"


# ── Source-type roster (the corpus is heterogeneous + auditable) ────────────
SOURCE_TYPES = ("changelog", "template", "agent", "skill", "history")


def _enumerate_sources() -> list[tuple[str, Path]]:
    """Walk the corpus + yield (source_type, abspath). Missing files
    skipped silently (a fresh repo may not have CHANGELOG / history yet).
    """
    items: list[tuple[str, Path]] = []
    changelog = REPO_ROOT / "CHANGELOG.md"
    if changelog.is_file():
        items.append(("changelog", changelog))
    tpl = REPO_ROOT / "templates"
    if tpl.is_dir():
        for p in sorted(tpl.rglob("*.md")):
            if p.is_file():
                items.append(("template", p))
    agents = REPO_ROOT / ".claude" / "agents"
    if agents.is_dir():
        for p in sorted(agents.glob("*.md")):
            if p.is_file():
                items.append(("agent", p))
    skills = REPO_ROOT / ".claude" / "skills"
    if skills.is_dir():
        for p in sorted(skills.rglob("SKILL.md")):
            if p.is_file():
                items.append(("skill", p))
    history = REPO_ROOT / "project-history" / "PROJECT-HISTORY.md"
    if history.is_file():
        items.append(("history", history))
    return items


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
CREATE TABLE IF NOT EXISTS corpus_chunks (
  rowid_alias  INTEGER PRIMARY KEY AUTOINCREMENT,
  source_type  TEXT NOT NULL,
  path         TEXT NOT NULL,
  chunk_idx    INTEGER NOT NULL,
  chunk_text   TEXT NOT NULL,
  source_sha   TEXT NOT NULL,
  cached_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_corpus_chunks_path ON corpus_chunks(path);
CREATE INDEX IF NOT EXISTS idx_corpus_chunks_type ON corpus_chunks(source_type);
"""

_VEC_SCHEMA = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS corpus_vec USING vec0(
  embedding float[{EMBEDDING_DIM}]
);
"""

_FALLBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS corpus_embeddings_json (
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


def _chunk_any_markdown(text: str, title_hint: str | None = None) -> list[str]:
    """Reuses kb_embeddings chunker (markdown-structural H2 split + char
    cap). The chunker reads its own H1; pass through unchanged."""
    return _chunk_markdown(text)


def refresh(force: bool = False, paths: list[str] | None = None) -> dict:
    """Re-populate corpus embeddings. Per-file source_sha guard skips
    unchanged. `paths` (repo-rel) limits scope."""
    conn = _connect()
    _init_schema(conn)

    sources = _enumerate_sources()
    if paths:
        wanted = set(paths)
        sources = [(st, p) for (st, p) in sources if str(p.relative_to(REPO_ROOT)) in wanted]

    refreshed: list[str] = []
    skipped: list[str] = []
    errors: list[dict] = []
    total_rows = 0

    for source_type, abs_path in sources:
        rel = str(abs_path.relative_to(REPO_ROOT))
        sha = _sha_file(abs_path)
        if not force:
            cur = conn.execute(
                "SELECT DISTINCT source_sha FROM corpus_chunks WHERE path=? LIMIT 1",
                (rel,),
            )
            row = cur.fetchone()
            if row and row["source_sha"] == sha:
                skipped.append(rel)
                continue

        # Wipe old rows for this doc.
        cur = conn.execute("SELECT rowid_alias FROM corpus_chunks WHERE path=?", (rel,))
        old_rowids = [r[0] for r in cur.fetchall()]
        if old_rowids:
            placeholders = ",".join("?" * len(old_rowids))
            if _HAS_VEC:
                conn.execute(f"DELETE FROM corpus_vec WHERE rowid IN ({placeholders})", old_rowids)
            else:
                conn.execute(
                    f"DELETE FROM corpus_embeddings_json WHERE chunk_rowid IN ({placeholders})",
                    old_rowids,
                )
            conn.execute("DELETE FROM corpus_chunks WHERE path=?", (rel,))

        try:
            text = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            errors.append({"path": rel, "error": f"read: {e}"})
            continue
        chunks = _chunk_any_markdown(text)
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
                "INSERT INTO corpus_chunks(source_type,path,chunk_idx,chunk_text,source_sha,cached_at) "
                "VALUES (?,?,?,?,?,?)",
                (source_type, rel, idx, chunk, sha, now),
            )
            row_id = cur.lastrowid
            per_doc_rowids.append(row_id)
            if _HAS_VEC:
                conn.execute(
                    "INSERT INTO corpus_vec(rowid, embedding) VALUES (?, ?)",
                    (row_id, _pack_vec(vec)),
                )
            else:
                conn.execute(
                    "INSERT INTO corpus_embeddings_json(chunk_rowid, embedding) VALUES (?, ?)",
                    (row_id, json.dumps(vec)),
                )
            total_rows += 1
        if not per_doc_ok and per_doc_rowids:
            placeholders = ",".join("?" * len(per_doc_rowids))
            if _HAS_VEC:
                conn.execute(f"DELETE FROM corpus_vec WHERE rowid IN ({placeholders})", per_doc_rowids)
            else:
                conn.execute(
                    f"DELETE FROM corpus_embeddings_json WHERE chunk_rowid IN ({placeholders})",
                    per_doc_rowids,
                )
            conn.execute("DELETE FROM corpus_chunks WHERE path=?", (rel,))
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


def search(
    query: str,
    top_k: int = 5,
    min_score: float = 0.0,
    source_type: str | None = None,
) -> list[dict]:
    """Embed `query`, return top-K corpus chunks. Optional `source_type`
    scopes the search (e.g. only `agent` or only `template`).
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
        if source_type:
            cur = conn.execute(
                """
                SELECT c.source_type, c.path, c.chunk_idx, c.chunk_text, v.distance
                FROM corpus_vec v
                JOIN corpus_chunks c ON c.rowid_alias = v.rowid
                WHERE v.embedding MATCH ? AND k = ? AND c.source_type = ?
                ORDER BY v.distance
                """,
                (q_blob, top_k, source_type),
            )
        else:
            cur = conn.execute(
                """
                SELECT c.source_type, c.path, c.chunk_idx, c.chunk_text, v.distance
                FROM corpus_vec v
                JOIN corpus_chunks c ON c.rowid_alias = v.rowid
                WHERE v.embedding MATCH ? AND k = ?
                ORDER BY v.distance
                """,
                (q_blob, top_k),
            )
        for r in cur.fetchall():
            score = 1.0 / (1.0 + float(r["distance"]))
            if score >= min_score:
                results.append({
                    "source_type": r["source_type"], "path": r["path"],
                    "chunk_idx": r["chunk_idx"], "chunk_text": r["chunk_text"],
                    "score": score, "engine": "sqlite-vec",
                })
    else:
        if source_type:
            sql = """
                SELECT c.source_type, c.path, c.chunk_idx, c.chunk_text, j.embedding
                FROM corpus_chunks c
                JOIN corpus_embeddings_json j ON j.chunk_rowid = c.rowid_alias
                WHERE c.source_type = ?
            """
            rows = conn.execute(sql, (source_type,)).fetchall()
        else:
            sql = """
                SELECT c.source_type, c.path, c.chunk_idx, c.chunk_text, j.embedding
                FROM corpus_chunks c
                JOIN corpus_embeddings_json j ON j.chunk_rowid = c.rowid_alias
            """
            rows = conn.execute(sql).fetchall()
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
                "source_type": r["source_type"], "path": r["path"],
                "chunk_idx": r["chunk_idx"], "chunk_text": r["chunk_text"],
                "score": score, "engine": "fallback-cosine",
            })
    conn.close()
    return results


def cache_source_sha() -> str:
    """Aggregate sha of every corpus source file — for the freshness keeper."""
    h = hashlib.sha256()
    for source_type, p in _enumerate_sources():
        h.update(source_type.encode("utf-8"))
        h.update(b"\0")
        h.update(str(p.relative_to(REPO_ROOT)).encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def register(server) -> None:
    @server.tool(
        name="noctus.dev.refresh_corpus_embeddings",
        description=(
            "Re-populate the corpus-embeddings cache from the heterogeneous "
            "in-repo corpus (CHANGELOG.md + templates/ + .claude/agents/*.md "
            "FULL bodies + .claude/skills/**/SKILL.md + PROJECT-HISTORY.md). "
            "Per-file source_sha skip. Returns standard refresh shape."
        ),
    )
    def _refresh_corpus_embeddings(force: bool = False, paths: list[str] | None = None) -> dict:
        return refresh(force=force, paths=paths)

    @server.tool(
        name="noctus.dev.corpus_search",
        description=(
            "Semantic search over the in-repo corpus (CHANGELOG / templates / "
            "agents FULL body / skills / PROJECT-HISTORY). Pass source_type "
            "to scope (changelog / template / agent / skill / history). Returns "
            "top-K chunks by cosine similarity."
        ),
    )
    def _corpus_search(
        query: str, top_k: int = 5, min_score: float = 0.0, source_type: str | None = None,
    ) -> list:
        return search(query, top_k=top_k, min_score=min_score, source_type=source_type)


__all__ = ["refresh", "search", "cache_source_sha", "register",
           "CACHE_PATH", "SOURCE_TYPES", "_enumerate_sources"]
