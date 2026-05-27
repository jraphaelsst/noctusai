"""memory-embeddings — 6th keeper-mirror cache.

Indexes the OUT-OF-REPO agent memory dir (`MEMORY.md` + every
`*.md` under `~/.claude/projects/<workspace>/memory/`) for semantic
search over accumulated feedback / project / reference notes.

v4.0 refactor: this module is now a THIN WRAPPER over the shared
`_embedding_corpus` framework. The chunker, embedder, cosine, pack,
connect, refresh-loop, and search-loop all live there. This module
defines only the corpus-specific bits: cache path + memory-dir
resolution + the (rel, abs, extras) source enumerator.

KB § PATTERNS/common/memory-embeddings.md.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

from settings import REPO_ROOT

from . import _embedding_corpus as _ec
from ._embedding_corpus import MarkdownCorpus


# ── Paths ────────────────────────────────────────────────────────────────────
CACHE_DIR = REPO_ROOT / ".claude" / "cache"
CACHE_PATH = CACHE_DIR / "memory-embeddings.sqlite"


def _primary_checkout_root() -> Path:
    """Return the PRIMARY git worktree root (not a linked worktree).
    Memory belongs to the logical project; linked worktrees share it."""
    try:
        out = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        for line in out.stdout.splitlines():
            if line.startswith("worktree "):
                return Path(line[len("worktree "):])
    except (OSError, subprocess.SubprocessError):
        pass
    return REPO_ROOT


def _resolve_memory_dir() -> Path | None:
    """Locate the agent memory dir. Three tiers:
      1. `NOCTUS_AGENT_MEMORY_DIR` env override.
      2. Path-slug derivation against PRIMARY checkout (linked worktrees
         share memory): Claude Code names workspaces with `/` → `-`.
      3. Loose-match fallback by basename.
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
    for c in sorted(base.glob("*/memory")):
        if (repo_basename in c.parent.name.lower()
                and "knowledge-extractor" not in c.parent.name.lower()):
            return c
    return None


def _enumerate_sources() -> list[tuple[str, Path, dict]]:
    """Yield (rel_path, abs_path, {}) for every memory `*.md` file.
    Empty extras dict — memory has no source_type / symbol etc."""
    mem_dir = _resolve_memory_dir()
    if mem_dir is None:
        return []
    return [
        (str(p.relative_to(mem_dir)), p, {})
        for p in sorted(mem_dir.glob("*.md"))
        if p.is_file()
    ]


_CORPUS = MarkdownCorpus(
    cache_path=CACHE_PATH,
    chunks_table="memory_chunks",
    vec_table="memory_vec",
    json_table="memory_embeddings_json",
    enumerate_sources=_enumerate_sources,
    extra_columns={},
)


def refresh(force: bool = False, paths: list[str] | None = None) -> dict:
    """Re-populate memory embeddings. Graceful no-op when memory dir
    isn't resolvable (fresh clone / no Claude Code session)."""
    if _resolve_memory_dir() is None:
        return {
            "ok": True, "status": "no-memory-dir",
            "refreshed": [], "skipped": [], "errors": [], "rows_written": 0,
            "message": (
                "agent memory dir not found — set NOCTUS_AGENT_MEMORY_DIR "
                "or run from a session whose ~/.claude/projects/*/memory/ "
                "exists."
            ),
        }
    result = _ec.refresh_markdown_corpus(_CORPUS, force=force, paths=paths)
    # Write aggregate source_sha for freshness keeper.
    try:
        conn = sqlite3.connect(str(CACHE_PATH))
        conn.execute(
            "INSERT OR REPLACE INTO cache_meta(key, value) VALUES ('source_sha', ?)",
            (cache_source_sha(),),
        )
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        pass
    return result


def search(query: str, top_k: int = 5, min_score: float = 0.0) -> list[dict]:
    """Semantic search over memory chunks."""
    return _ec.search_markdown_corpus(
        _CORPUS, query, top_k=top_k, min_score=min_score,
    )


def cache_source_sha() -> str:
    """Aggregate sha of memory dir contents — for freshness keeper."""
    return _ec.aggregate_source_sha(_enumerate_sources())


def register(server) -> None:
    @server.tool(
        name="noctus.dev.refresh_memory_embeddings",
        description=(
            "Re-populate the memory-embeddings cache from the out-of-repo "
            "agent memory dir (`~/.claude/projects/<workspace>/memory/`). "
            "Per-file source_sha guard skips unchanged."
        ),
    )
    def _refresh_memory_embeddings(force: bool = False, paths: list[str] | None = None) -> dict:
        return refresh(force=force, paths=paths)

    @server.tool(
        name="noctus.dev.memory_search",
        description=(
            "Semantic search over agent memory (feedback / reference / "
            "project notes). Top-K chunks by cosine similarity."
        ),
    )
    def _memory_search(query: str, top_k: int = 5, min_score: float = 0.0) -> list:
        return search(query, top_k=top_k, min_score=min_score)


__all__ = ["refresh", "search", "cache_source_sha", "register",
           "CACHE_PATH", "_resolve_memory_dir"]
