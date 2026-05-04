"""``noctus.*`` tool umbrella — Noctus-owned MCP tools.

Sub-umbrellas:
  - ``noctus.dev.*`` — developer-experience tools (24 modules; ships today).
  - ``noctus.business.*`` — product business-logic tools (Phase 4 of
    mcp-server-fastmcp-switch; gated on Tier 1 substrate).

``register_all`` delegates to each sub-umbrella in alphabetical order.
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every tool under the ``noctus.*`` umbrella."""
    from . import dev, team

    dev.register_all(server)
    team.register_all(server)


__all__ = ["register_all"]
