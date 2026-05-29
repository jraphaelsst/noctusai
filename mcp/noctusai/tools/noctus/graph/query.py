"""``noctus.graph.query`` — substring-ranked search over nodes."""

from __future__ import annotations

from typing import Optional

from noctusai_lib.graph.schema import NodeKind

from ._loader import load_index


def search(query: str, kinds: Optional[list[str]] = None, limit: int = 20) -> dict:
    idx = load_index()
    kind_enums = [NodeKind(k) for k in kinds] if kinds else None
    hits = idx.search(query, kinds=kind_enums, limit=limit)
    return {
        "query": query,
        "count": len(hits),
        "matches": [
            {
                "node": node.to_dict(),
                "score": score,
            }
            for node, score in hits
        ],
    }


def register(server) -> None:
    @server.tool(
        name="noctus.graph.query",
        description=(
            "Search the knowledge graph by substring on label/id/path. "
            "Returns ranked matches. Optional `kinds=[NodeKind, ...]` filter "
            "(e.g. `[\"mcp_tool\", \"kb_pattern\"]`). An EMPTY query "
            "(`query=\"\"`) LISTS every node — combine with `kinds` to "
            "enumerate all nodes of a kind (e.g. `query=\"\" "
            "kinds=[\"harness_agent\"]`); raise `limit` to page past 20. "
            "Run `noctus.graph.build` first if `.noc-graph/graph.json` is missing."
        ),
    )
    def _query(query: str, kinds: Optional[list[str]] = None, limit: int = 20) -> dict:
        return search(query, kinds=kinds, limit=limit)
