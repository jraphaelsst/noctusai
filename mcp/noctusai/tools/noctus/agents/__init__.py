"""``noctus.agents.*`` -- tools that drive the agents Studio API.

``noctus.agents.content``
    The "Claude, change Julia's X" path (Julia v2 CONTRACT 2.5): writes agent CONTENT rows (sections,
    system texts, tool descriptions, decisions, org-spec declarations, library skills and their pins,
    qualification-standard criteria/stages/parameters) into a target environment through the Studio API.
    Drafts only, never publishes; dry-run by default.
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every ``noctus.agents.*`` tool on the given FastMCP server."""
    from . import content

    content.register(server)


__all__ = ["register_all"]
