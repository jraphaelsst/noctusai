"""``noctus.team.*`` — agno multi-agent dev team controls.

Wraps :mod:`dev_team.mcp_facade` operations as Pydantic-typed MCP tools.
The 6 tools mirror the facade contract one-to-one:

  - ``noctus.team.agent_metrics`` — per-agent metrics rollup.
  - ``noctus.team.configure``     — patch an agent's model / provider in a
                                     named YAML config.
  - ``noctus.team.metrics``       — top-level metrics rollup.
  - ``noctus.team.route``         — team-vs-direct heuristic.
  - ``noctus.team.run``           — fire the team on a task.
  - ``noctus.team.status``        — read current team state from memory.

Per `KB § PATTERNS/mcp-tool-conventions.md` — 3-segment dotted naming,
hierarchical registration, lazy imports inside ``register_all`` so the
MCP server stays light when ``dev_team`` (and its agno dep) isn't loaded
on import.
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every tool under the ``noctus.team.*`` umbrella."""
    from . import agent_metrics, configure, metrics, route, run, status

    agent_metrics.register(server)
    configure.register(server)
    metrics.register(server)
    route.register(server)
    run.register(server)
    status.register(server)


__all__ = ["register_all"]
