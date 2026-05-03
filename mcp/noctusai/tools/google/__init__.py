"""``google.*`` tool umbrella — Google vendor adapters wrapped as MCP tools.

Sub-umbrellas:
  - ``google.calendar.*`` — Calendar events (4 tools).
  - ``google.maps.*`` — Routing / travel estimates (1 tool).

Each tool is a thin Pydantic-shaped wrapper over
``noctusai_lib.integrations.google_calendar`` / ``google_maps``.
``register_all`` delegates to each sub-umbrella in alphabetical order.
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every tool under the ``google.*`` umbrella."""
    from . import calendar, maps

    calendar.register_all(server)
    maps.register_all(server)


__all__ = ["register_all"]
