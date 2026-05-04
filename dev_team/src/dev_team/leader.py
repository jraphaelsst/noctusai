"""dev_team Team Leader factory.

Per design-reference.md §2.1 — orchestrator; decides who acts next,
when to invoke sub-teams, when to pause; aggregates specialist
outputs into the user-facing reply; writes the end-of-work summary.

The Leader is built via :func:`dev_team.agents.base.build_agent`
under the role name ``"leader"``. Its allowlist is the only one
containing ``delegate`` and ``invoke_subteam`` (per
design-reference.md §3 + tests/test_smoke.py::test_allowlists_have_11_roles).

Public surface:
    build_leader(config) -> agno.agent.Agent
"""

from __future__ import annotations

from typing import Any, Mapping

from dev_team.agents.base import build_agent


def build_leader(config: Mapping[str, Any]):
    """Build the Team Leader Agent.

    The Leader is a regular agno Agent with the leader-specific charter
    + tool allowlist. It is the agent the agno Team passes the user task
    to first; it then delegates via ``delegate`` / ``invoke_subteam``.
    """
    return build_agent("leader", config=config)


__all__ = ["build_leader"]
