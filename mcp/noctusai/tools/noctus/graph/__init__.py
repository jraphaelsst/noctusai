"""``noctus.graph.*`` tool umbrella — queryable knowledge graph of the platform.

Materializes the implicit relational index that's otherwise reconstructed
each turn from N composed scans. Backed by ``noctusai_lib.graph`` (the
extractor library) — these tools are thin Pydantic wrappers over that
library + the on-disk ``.noc-graph/graph.json`` cache.

Tools:
  - ``noctus.graph.build`` — (re)build the graph and write artifacts.
  - ``noctus.graph.query`` — substring + ranked search over node labels/paths.
  - ``noctus.graph.neighbors`` — BFS up to N hops from a node.
  - ``noctus.graph.path`` — shortest path between two nodes.
  - ``noctus.graph.explain`` — full node detail + grouped neighbors + cluster members.
  - ``noctus.graph.report`` — summary report (counts, top clusters, highlights).
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every tool under the ``noctus.graph.*`` umbrella."""
    from . import build, explain, neighbors, path, query, report

    build.register(server)
    query.register(server)
    neighbors.register(server)
    path.register(server)
    explain.register(server)
    report.register(server)


__all__ = ["register_all"]
