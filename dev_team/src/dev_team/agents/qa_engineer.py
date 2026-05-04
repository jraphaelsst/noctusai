"""QA / Test Engineer specialist factory.

Per design-reference.md §2.9 — independently verifies built ↔
specified; designs and writes tests; never patches own code in tests
(no self-monkeypatching). Member of code_review_team.

Public surface:
    build_qa_engineer(config) -> agno.agent.Agent
"""

from __future__ import annotations

from typing import Any, Mapping

from dev_team.agents.base import build_agent


def build_qa_engineer(config: Mapping[str, Any]):
    """Build the QA Engineer Agent."""
    return build_agent("qa_engineer", config=config)


__all__ = ["build_qa_engineer"]
