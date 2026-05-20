"""``noctus.graph.path`` — shortest path between two nodes (undirected BFS)."""

from __future__ import annotations

from ._loader import load_index


def shortest_path(source_id: str, target_id: str, max_depth: int = 6) -> dict:
    idx = load_index()
    return idx.shortest_path(source_id, target_id, max_depth=max_depth)


def register(server) -> None:
    @server.tool(
        name="noctus.graph.path",
        description=(
            "Shortest path between two nodes (undirected BFS). Returns "
            "the chain of {node, edge} steps + via_kinds summary. "
            "Defaults to max_depth=6."
        ),
    )
    def _path(source_id: str, target_id: str, max_depth: int = 6) -> dict:
        return shortest_path(source_id, target_id, max_depth=max_depth)
