"""``noctus.*`` tool umbrella — Noctus-owned MCP tools.

Sub-umbrellas:
  - ``noctus.dev.*`` — developer-experience tools (28 modules; ships today).
  - ``noctus.graph.*`` — queryable knowledge graph (build/query/neighbors/path/explain/report).
  - ``noctus.hound.*`` — code-hygiene orchestrator (runs the absorption
    + fusion + optimization trio together).
  - ``noctus.seed.*`` — seed-system absorption + capability tools.
  - ``noctus.team.*`` — agno multi-agent dev team tools.
  - ``noctus.youtube.*`` — YouTube channel analytics + action tools (read snapshots,
    report on growth, trigger syncs).
  - ``noctus.business.*`` — product business-logic tools (Phase 4 of
    mcp-server-fastmcp-switch; gated on Tier 1 substrate).

``register_all`` delegates to each sub-umbrella in alphabetical order.
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every tool under the ``noctus.*`` umbrella."""
    from . import dev, graph, hound, seed, team, youtube

    dev.register_all(server)
    graph.register_all(server)
    hound.register_all(server)
    seed.register_all(server)
    team.register_all(server)
    youtube.register_all(server)


__all__ = ["register_all"]
