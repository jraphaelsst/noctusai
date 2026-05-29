"""Query primitives — search / neighbors / path / explain.

Pure-Python over an in-memory ``Graph``. No external deps.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable

from .schema import Edge, EdgeKind, Graph, Node, NodeKind


class GraphIndex:
    """In-memory adjacency + label index for cheap query.

    Built once per loaded ``Graph``. Re-use across queries within a
    process; rebuild when the graph rebuilds.
    """

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self.by_id: dict[str, Node] = {n.id: n for n in graph.nodes}
        self.out_edges: dict[str, list[Edge]] = defaultdict(list)
        self.in_edges: dict[str, list[Edge]] = defaultdict(list)
        for edge in graph.edges:
            self.out_edges[edge.source].append(edge)
            self.in_edges[edge.target].append(edge)

    # ── search ────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        kinds: list[NodeKind] | None = None,
        limit: int = 20,
    ) -> list[tuple[Node, float]]:
        """Substring-match on label + id + path. Returns ranked (node, score).

        An empty/whitespace query is a LISTING request, not a no-op: it
        enumerates every node (optionally ``kinds``-filtered), ordered by
        label for stable output. This makes ``query="" kinds=[...]`` the
        canonical "list every node of kind X" call the contextualize
        protocol relies on for surfacing the methodology fabric.
        """
        q_low = query.lower().strip()
        kind_filter = {k.value for k in kinds} if kinds else None
        if not q_low:
            listed = [
                (node, 1.0)
                for node in self.graph.nodes
                if not kind_filter or node.kind.value in kind_filter
            ]
            listed.sort(key=lambda pair: pair[0].label.lower())
            return listed[:limit]
        results: list[tuple[Node, float]] = []
        for node in self.graph.nodes:
            if kind_filter and node.kind.value not in kind_filter:
                continue
            score = _score(node, q_low)
            if score > 0:
                results.append((node, score))
        results.sort(key=lambda pair: pair[1], reverse=True)
        return results[:limit]

    # ── neighbors ─────────────────────────────────────────────────────────────

    def neighbors(
        self,
        node_id: str,
        *,
        depth: int = 1,
        edge_kinds: list[EdgeKind] | None = None,
    ) -> dict:
        """BFS up to ``depth`` hops. Returns subgraph + classified edge lists."""
        if node_id not in self.by_id:
            return {"node": None, "error": f"node {node_id!r} not found"}
        kind_filter = {k.value for k in edge_kinds} if edge_kinds else None
        visited: set[str] = {node_id}
        frontier: deque[tuple[str, int]] = deque([(node_id, 0)])
        sub_nodes: list[Node] = []
        sub_edges: list[Edge] = []
        while frontier:
            current, hops = frontier.popleft()
            sub_nodes.append(self.by_id[current])
            if hops >= depth:
                continue
            for edge in self.out_edges.get(current, []) + self.in_edges.get(current, []):
                if kind_filter and edge.kind.value not in kind_filter:
                    continue
                other = edge.target if edge.source == current else edge.source
                if other not in self.by_id:
                    continue
                if other not in visited:
                    visited.add(other)
                    frontier.append((other, hops + 1))
                sub_edges.append(edge)
        # dedup edges
        unique_edges: dict[tuple[str, str, str], Edge] = {}
        for edge in sub_edges:
            unique_edges[(edge.source, edge.target, edge.kind.value)] = edge
        return {
            "node": self.by_id[node_id].to_dict(),
            "edges_out": [e.to_dict() for e in self.out_edges.get(node_id, [])],
            "edges_in": [e.to_dict() for e in self.in_edges.get(node_id, [])],
            "subgraph": {
                "nodes": [n.to_dict() for n in sub_nodes],
                "edges": [e.to_dict() for e in unique_edges.values()],
            },
        }

    # ── path ──────────────────────────────────────────────────────────────────

    def shortest_path(
        self,
        source_id: str,
        target_id: str,
        *,
        max_depth: int = 6,
    ) -> dict:
        """Undirected BFS. Returns the path or empty if not found within max_depth."""
        if source_id not in self.by_id:
            return {"path": [], "error": f"source {source_id!r} not found"}
        if target_id not in self.by_id:
            return {"path": [], "error": f"target {target_id!r} not found"}
        if source_id == target_id:
            return {"path": [{"node": self.by_id[source_id].to_dict(), "edge": None}], "length": 0}

        parent: dict[str, tuple[str, Edge] | None] = {source_id: None}
        frontier: deque[tuple[str, int]] = deque([(source_id, 0)])
        while frontier:
            current, hops = frontier.popleft()
            if hops >= max_depth:
                continue
            for edge in self.out_edges.get(current, []) + self.in_edges.get(current, []):
                other = edge.target if edge.source == current else edge.source
                if other in parent or other not in self.by_id:
                    continue
                parent[other] = (current, edge)
                if other == target_id:
                    return self._reconstruct_path(parent, target_id)
                frontier.append((other, hops + 1))
        return {"path": [], "error": "no path within max_depth"}

    def _reconstruct_path(self, parent, target_id):
        steps: list[dict] = []
        cursor: str | None = target_id
        while cursor is not None:
            entry = parent.get(cursor)
            if entry is None:
                steps.append({"node": self.by_id[cursor].to_dict(), "edge": None})
                break
            prev, edge = entry
            steps.append({"node": self.by_id[cursor].to_dict(), "edge": edge.to_dict()})
            cursor = prev
        steps.reverse()
        via_kinds = sorted({s["edge"]["kind"] for s in steps if s["edge"]})
        return {"path": steps, "length": len(steps) - 1, "via_kinds": via_kinds}

    # ── explain ───────────────────────────────────────────────────────────────

    def explain(self, node_id: str) -> dict:
        if node_id not in self.by_id:
            return {"error": f"node {node_id!r} not found"}
        node = self.by_id[node_id]
        grouped_out: dict[str, list[dict]] = defaultdict(list)
        for edge in self.out_edges.get(node_id, []):
            target = self.by_id.get(edge.target)
            grouped_out[edge.kind.value].append({
                "target": edge.target,
                "label": target.label if target else edge.target,
                "kind": target.kind.value if target else None,
            })
        grouped_in: dict[str, list[dict]] = defaultdict(list)
        for edge in self.in_edges.get(node_id, []):
            source = self.by_id.get(edge.source)
            grouped_in[edge.kind.value].append({
                "source": edge.source,
                "label": source.label if source else edge.source,
                "kind": source.kind.value if source else None,
            })
        cluster_members: list[dict] = []
        if node.cluster is not None:
            cluster_members = [
                {"id": n.id, "label": n.label, "kind": n.kind.value}
                for n in self.graph.nodes
                if n.cluster == node.cluster and n.id != node_id
            ][:40]
        return {
            "node": node.to_dict(),
            "neighbors_out_by_kind": dict(grouped_out),
            "neighbors_in_by_kind": dict(grouped_in),
            "cluster_members": cluster_members,
        }


def _score(node: Node, q_low: str) -> float:
    """Crude relevance score — exact label, prefix, substring."""
    label = node.label.lower()
    if label == q_low:
        return 100.0
    if label.startswith(q_low):
        return 50.0
    if q_low in label:
        return 25.0
    if q_low in node.id.lower():
        return 10.0
    if node.path and q_low in node.path.lower():
        return 5.0
    return 0.0
