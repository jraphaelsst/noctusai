"""Shared loader — resolves repo root, loads the cached graph, indexes it.

The on-disk cache lives at ``<repo_root>/.noc-graph/graph.json`` by
default. Query tools read this; only ``noctus.graph.build`` writes it.

Lazy-on-query freshness: ``load_cached_graph`` and ``load_index`` call
``_ensure_fresh_on_read`` before serving the graph, so the SQLite cache
(and its derived ``.noc-graph/graph.json``) is rebuilt only when queried
AND stale — never eagerly on every commit.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from noctusai_lib.graph.query import GraphIndex
from noctusai_lib.graph.schema import Graph

from settings import REPO_ROOT


def graph_cache_path(repo_root: Path | None = None) -> Path:
    return (repo_root or REPO_ROOT) / ".noc-graph" / "graph.json"


def load_cached_graph(repo_root: Path | None = None) -> Graph:
    """Load `.noc-graph/graph.json`, rebuilding if stale (lazy-on-query).

    Calls ``_ensure_fresh_on_read`` before loading so the caller always
    gets a fresh (or best-effort) graph without triggering an eager rebuild
    on every commit boundary.
    """
    from tools.noctus.dev.noc_graph_cache import _ensure_fresh_on_read
    _ensure_fresh_on_read(repo_root)
    cache = graph_cache_path(repo_root)
    if not cache.exists():
        raise FileNotFoundError(
            f"graph cache missing at {cache} — run `noctus.graph.build` first"
        )
    return Graph.from_json(cache.read_text(encoding="utf-8"))


def load_index(repo_root: Path | None = None) -> GraphIndex:
    """Load + index the cached graph. No caching across MCP requests (stateless).

    Delegates lazy-freshness check to ``load_cached_graph``.
    """
    return GraphIndex(load_cached_graph(repo_root))
