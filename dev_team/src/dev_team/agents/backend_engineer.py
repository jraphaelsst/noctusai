"""Backend Engineer specialist factory.

Per design-reference.md §2.5 — implements server-side logic per the
Architect's contracts; AST-first edits via libcst; live-ticks
PROJECT.md §6; member of design_review_team and incident_response_team.

Public surface:
    build_backend_engineer(config) -> agno.agent.Agent
"""

from __future__ import annotations

from typing import Any, Mapping

from dev_team.agents.base import build_agent


def build_backend_engineer(config: Mapping[str, Any]):
    """Build the Backend Engineer Agent."""
    return build_agent("backend_engineer", config=config)


__all__ = ["build_backend_engineer"]
