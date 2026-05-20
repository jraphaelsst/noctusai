"""``noctus.graph.neighbors`` — BFS up to N hops from a node."""

from __future__ import annotations

from typing import Optional

from noctusai_lib.graph.schema import EdgeKind

from ._loader import load_index


def neighbors(node_id: str, depth: int = 1, edge_kinds: Optional[list[str]] = None) -> dict:
    idx = load_index()
    kind_enums = [EdgeKind(k) for k in edge_kinds] if edge_kinds else None
    return idx.neighbors(node_id, depth=depth, edge_kinds=kind_enums)


def register(server) -> None:
    @server.tool(
        name="noctus.graph.neighbors",
        description=(
            "Return the N-hop neighborhood around a node. Use the `id` "
            "field from `noctus.graph.query` results. Optional "
            "`edge_kinds=[EdgeKind, ...]` filter (e.g. `[\"imports\", "
            "\"consumes_seed\"]`). Default depth=1."
        ),
    )
    def _neighbors(node_id: str, depth: int = 1, edge_kinds: Optional[list[str]] = None) -> dict:
        return neighbors(node_id, depth=depth, edge_kinds=edge_kinds)
