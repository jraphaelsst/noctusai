"""Security Engineer specialist factory.

Per design-reference.md §2.8 — adversarial reviewer; uses keeper
toolkit (observation-only); runs data-protection five questions
(split with PM); member of design_review_team, code_review_team,
incident_response_team.

Public surface:
    build_security_engineer(config) -> agno.agent.Agent
"""

from __future__ import annotations

from typing import Any, Mapping

from dev_team.agents.base import build_agent


def build_security_engineer(config: Mapping[str, Any]):
    """Build the Security Engineer Agent."""
    return build_agent("security_engineer", config=config)


__all__ = ["build_security_engineer"]
