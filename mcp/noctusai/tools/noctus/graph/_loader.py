"""Shared loader — resolves repo root, loads the cached graph, indexes it.

The on-disk cache lives at ``<repo_root>/.noc-graph/graph.json`` by
default. Query tools read this; only ``noctus.graph.build`` writes it.
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
    """Load `.noc-graph/graph.json`. Raises FileNotFoundError if missing."""
    cache = graph_cache_path(repo_root)
    if not cache.exists():
        raise FileNotFoundError(
            f"graph cache missing at {cache} — run `noctus.graph.build` first"
        )
    return Graph.from_json(cache.read_text(encoding="utf-8"))


def load_index(repo_root: Path | None = None) -> GraphIndex:
    """Load + index the cached graph. No caching across MCP requests (stateless)."""
    return GraphIndex(load_cached_graph(repo_root))
