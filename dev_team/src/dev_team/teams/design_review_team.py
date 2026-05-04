"""design_review_team — collaborate-mode sub-team.

Per design-reference.md §1.2 + §2 sub-team-membership annotations:

    Architect (lead) + Backend + Frontend + DevOps + Security

Invoked by the Leader for non-trivial design phases (per
design-reference.md §1.3 step 4). Members appearing in both the main
team and a sub-team are *the same agent instance* — agno handles
this cleanly + preserves voice + memory + craft notes across contexts.

Public surface:
    build_design_review_team(config) -> agno.team.Team
"""

from __future__ import annotations

from typing import Any, Mapping


def build_design_review_team(config: Mapping[str, Any]):
    """Assemble the design_review_team in collaborate mode.

    Returns
    -------
    agno.team.Team

    Notes
    -----
    Imports are LOCAL so importing this module doesn't require agno
    installed — mirrors the pattern in :func:`dev_team.agents.base.build_agent`
    + :func:`dev_team.team.build_team`. Smoke tests rely on this.
    """
    from agno.team import Team  # local import keeps top-level cheap

    from dev_team.agents.backend_engineer import build_backend_engineer
    from dev_team.agents.devops_engineer import build_devops_engineer
    from dev_team.agents.frontend_engineer import build_frontend_engineer
    from dev_team.agents.security_engineer import build_security_engineer
    from dev_team.agents.solution_architect import build_solution_architect

    architect = build_solution_architect(config)
    members = [
        architect,
        build_backend_engineer(config),
        build_frontend_engineer(config),
        build_devops_engineer(config),
        build_security_engineer(config),
    ]

    return Team(
        name="design_review_team",
        members=members,
        mode="collaborate",
    )


__all__ = ["build_design_review_team"]
