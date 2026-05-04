"""Product Manager specialist factory.

Per design-reference.md §2.2 — owns the *what* + *why*; converts user
requests into stories + acceptance criteria; runs the data-protection
five questions at intake (split with Security).

Public surface:
    build_product_manager(config) -> agno.agent.Agent
"""

from __future__ import annotations

from typing import Any, Mapping

from dev_team.agents.base import build_agent


def build_product_manager(config: Mapping[str, Any]):
    """Build the Product Manager Agent."""
    return build_agent("product_manager", config=config)


__all__ = ["build_product_manager"]
