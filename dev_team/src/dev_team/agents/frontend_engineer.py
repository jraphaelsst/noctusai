"""Frontend Engineer specialist factory.

Per design-reference.md §2.6 — implements UI per UX designs;
AST-first edits via ts-morph; live-ticks PROJECT.md §6; member of
design_review_team and incident_response_team (situational).

Public surface:
    build_frontend_engineer(config) -> agno.agent.Agent
"""

from __future__ import annotations

from typing import Any, Mapping

from dev_team.agents.base import build_agent


def build_frontend_engineer(config: Mapping[str, Any]):
    """Build the Frontend Engineer Agent."""
    return build_agent("frontend_engineer", config=config)


__all__ = ["build_frontend_engineer"]
