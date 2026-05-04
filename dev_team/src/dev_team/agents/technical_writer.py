"""Technical Writer specialist factory.

Per design-reference.md §2.11 — produces / maintains README, API
docs, runbooks, changelogs; logs §11 entries for every phase.

Public surface:
    build_technical_writer(config) -> agno.agent.Agent
"""

from __future__ import annotations

from typing import Any, Mapping

from dev_team.agents.base import build_agent


def build_technical_writer(config: Mapping[str, Any]):
    """Build the Technical Writer Agent."""
    return build_agent("technical_writer", config=config)


__all__ = ["build_technical_writer"]
