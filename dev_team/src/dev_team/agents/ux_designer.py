"""UX Designer specialist factory.

Per design-reference.md §2.3 — produces flows / wireframes / design
tokens / accessibility requirements before any frontend code is
written. UX produces the spec, Frontend implements; UX never touches
code.

Public surface:
    build_ux_designer(config) -> agno.agent.Agent
"""

from __future__ import annotations

from typing import Any, Mapping

from dev_team.agents.base import build_agent


def build_ux_designer(config: Mapping[str, Any]):
    """Build the UX Designer Agent."""
    return build_agent("ux_designer", config=config)


__all__ = ["build_ux_designer"]
