"""corpus-embeddings — 7th keeper-mirror cache.

Indexes the heterogeneous in-repo "everything else we read but isn't KB
or code": CHANGELOG.md + templates + .claude/agents (FULL body) +
.claude/skills + PROJECT-HISTORY.md. Each chunk row carries a
`source_type` column so search can scope.

v4.0 refactor: thin wrapper over the shared `_embedding_corpus`
framework. Only the corpus-specific bits live here: the cache path +
the heterogeneous source enumerator + `source_type` filtering.

KB § PATTERNS/common/corpus-embeddings.md.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from settings import REPO_ROOT

from . import _embedding_corpus as _ec
from ._embedding_corpus import MarkdownCorpus


from .cache_backend import cache_dir as _cache_dir, cache_path as _cache_path

# Resolved lazily via cache_backend (Tier-1 persistent location:
# <git-common-dir>/noctusai/cache/). Module-level constants are kept for
# backward-compat; they hit the resolver on each module import (cheap,
# memoized in cache_backend).
CACHE_DIR = _cache_dir()
CACHE_PATH = _cache_path("corpus-embeddings")


SOURCE_TYPES = (
    "changelog", "template", "agent", "skill", "history",
    "router", "topic", "orientation", "command",
)


def _enumerate_sources() -> list[tuple[str, Path, dict]]:
    """Walk the corpus + yield (rel_path, abs_path, {"source_type": ...})
    triples. Missing files skipped silently (a fresh repo may not have
    CHANGELOG / history yet)."""
    items: list[tuple[str, Path, dict]] = []

    changelog = REPO_ROOT / "CHANGELOG.md"
    if changelog.is_file():
        items.append((
            str(changelog.relative_to(REPO_ROOT)), changelog,
            {"source_type": "changelog"},
        ))

    tpl = REPO_ROOT / "templates"
    if tpl.is_dir():
        for p in sorted(tpl.rglob("*.md")):
            if p.is_file():
                items.append((
                    str(p.relative_to(REPO_ROOT)), p,
                    {"source_type": "template"},
                ))

    agents = REPO_ROOT / ".claude" / "agents"
    if agents.is_dir():
        for p in sorted(agents.glob("*.md")):
            if p.is_file():
                items.append((
                    str(p.relative_to(REPO_ROOT)), p,
                    {"source_type": "agent"},
                ))

    skills = REPO_ROOT / ".claude" / "skills"
    if skills.is_dir():
        for p in sorted(skills.rglob("SKILL.md")):
            if p.is_file():
                items.append((
                    str(p.relative_to(REPO_ROOT)), p,
                    {"source_type": "skill"},
                ))

    # router — CLAUDE.md is the always-loaded behavioral router; the most-read
    # methodology surface on the platform. Searching it is high-value.
    router = REPO_ROOT / "CLAUDE.md"
    if router.is_file():
        items.append((
            str(router.relative_to(REPO_ROOT)), router,
            {"source_type": "router"},
        ))

    # topic — CLAUDE/<topic>.md (backend / frontend / projects / platform):
    # the topical behavioral layer read by discipline.
    topic_dir = REPO_ROOT / "CLAUDE"
    if topic_dir.is_dir():
        for p in sorted(topic_dir.glob("*.md")):
            if p.is_file():
                items.append((
                    str(p.relative_to(REPO_ROOT)), p,
                    {"source_type": "topic"},
                ))

    # orientation — CONTEXTUALIZE.md (the fresh-session entry point).
    orient = REPO_ROOT / "CONTEXTUALIZE.md"
    if orient.is_file():
        items.append((
            str(orient.relative_to(REPO_ROOT)), orient,
            {"source_type": "orientation"},
        ))

    # command — .claude/commands/<name>.md (slash commands; user-invoked, but
    # agents need to know what they do when the user asks).
    cmd_dir = REPO_ROOT / ".claude" / "commands"
    if cmd_dir.is_dir():
        for p in sorted(cmd_dir.glob("*.md")):
            if p.is_file():
                items.append((
                    str(p.relative_to(REPO_ROOT)), p,
                    {"source_type": "command"},
                ))

    history = REPO_ROOT / "project-history" / "PROJECT-HISTORY.md"
    if history.is_file():
        items.append((
            str(history.relative_to(REPO_ROOT)), history,
            {"source_type": "history"},
        ))

    return items


_CORPUS = MarkdownCorpus(
    cache_path=CACHE_PATH,
    chunks_table="corpus_chunks",
    vec_table="corpus_vec",
    json_table="corpus_embeddings_json",
    enumerate_sources=_enumerate_sources,
    extra_columns={"source_type": "TEXT NOT NULL"},
)


def refresh(force: bool = False, paths: list[str] | None = None) -> dict:
    result = _ec.refresh_markdown_corpus(
        _CORPUS, force=force, paths=paths, cost_namespace="corpus-embeddings"
    )
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


def search(
    query: str,
    top_k: int = 5,
    min_score: float = 0.0,
    source_type: str | None = None,
) -> list[dict]:
    """Semantic search over the in-repo corpus. Optional source_type filter."""
    where = None
    params = None
    if source_type:
        where = "c.source_type = ?"
        params = [source_type]
    return _ec.search_markdown_corpus(
        _CORPUS, query, top_k=top_k, min_score=min_score,
        where_clause=where, where_params=params,
    )


def cache_source_sha() -> str:
    return _ec.aggregate_source_sha(_enumerate_sources())


def register(server) -> None:
    @server.tool(
        name="noctus.dev.refresh_corpus_embeddings",
        description=(
            "Re-populate the corpus-embeddings cache from the heterogeneous "
            "in-repo corpus (CHANGELOG.md + templates/ + .claude/agents/*.md "
            "FULL bodies + .claude/skills/**/SKILL.md + PROJECT-HISTORY.md)."
        ),
    )
    def _refresh_corpus_embeddings(force: bool = False, paths: list[str] | None = None) -> dict:
        return refresh(force=force, paths=paths)

    @server.tool(
        name="noctus.dev.corpus_search",
        description=(
            "Semantic search over the in-repo corpus. Pass source_type to "
            "scope (changelog / template / agent / skill / history)."
        ),
    )
    def _corpus_search(
        query: str, top_k: int = 5, min_score: float = 0.0,
        source_type: str | None = None,
    ) -> list:
        return search(query, top_k=top_k, min_score=min_score, source_type=source_type)


__all__ = ["refresh", "search", "cache_source_sha", "register",
           "CACHE_PATH", "SOURCE_TYPES", "_enumerate_sources"]
