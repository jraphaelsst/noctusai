"""Code Reviewer specialist factory.

Per design-reference.md §2.10 — reviews for quality / maintainability
/ standards; authors the bundled phase proposal; cross-checks
language-time triggers (replication-to-seed-symmetry); LEADS
code_review_team.

Public surface:
    build_code_reviewer(config) -> agno.agent.Agent
"""

from __future__ import annotations

from typing import Any, Mapping

from dev_team.agents.base import build_agent


def build_code_reviewer(config: Mapping[str, Any]):
    """Build the Code Reviewer Agent."""
    return build_agent("code_reviewer", config=config)


__all__ = ["build_code_reviewer"]
