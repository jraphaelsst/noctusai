"""DevOps / Platform Engineer specialist factory.

Per design-reference.md §2.7 — IaC, CI/CD, secrets, observability;
member of design_review_team; LEADS incident_response_team.

Public surface:
    build_devops_engineer(config) -> agno.agent.Agent
"""

from __future__ import annotations

from typing import Any, Mapping

from dev_team.agents.base import build_agent


def build_devops_engineer(config: Mapping[str, Any]):
    """Build the DevOps Engineer Agent."""
    return build_agent("devops_engineer", config=config)


__all__ = ["build_devops_engineer"]
