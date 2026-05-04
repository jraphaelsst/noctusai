"""Solution Architect / Tech Lead specialist factory.

Per design-reference.md §2.4 — owns the *how* at the system level;
runs Phase 0 audits, recurrence scans, produces ADRs / contracts /
schemas. Leads the design_review_team sub-team.

Public surface:
    build_solution_architect(config) -> agno.agent.Agent
"""

from __future__ import annotations

from typing import Any, Mapping

from dev_team.agents.base import build_agent


def build_solution_architect(config: Mapping[str, Any]):
    """Build the Solution Architect Agent."""
    return build_agent("solution_architect", config=config)


__all__ = ["build_solution_architect"]
