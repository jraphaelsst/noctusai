"""incident_response_team — collaborate-mode sub-team.

Per design-reference.md §10 + §1.2:

    DevOps (lead) + Security + Backend + Frontend (situational)

Invoked by the Leader on production incidents, alert pages, runbook
execution, post-mortem authoring. Goal: triage → mitigate →
root-cause → document, with a short feedback loop to the on-call
human. Collaborate mode is fine here — the question is restoration
speed, not token cost (design-reference.md §10).

Frontend is a default member of the assembled team but flagged
*situational* (only adds value when the incident touches the UI).
The Leader can prune Frontend at invocation time when the incident
is purely backend / infra; team membership stays declared so the
assembled object is consistent across contexts.

Public surface:
    build_incident_response_team(config) -> agno.team.Team
"""

from __future__ import annotations

from typing import Any, Mapping


def build_incident_response_team(config: Mapping[str, Any]):
    """Assemble the incident_response_team in collaborate mode.

    Returns
    -------
    agno.team.Team

    Notes
    -----
    Imports are LOCAL — see :func:`dev_team.teams.design_review_team.build_design_review_team`.
    """
    from agno.team import Team

    from dev_team.agents.backend_engineer import build_backend_engineer
    from dev_team.agents.devops_engineer import build_devops_engineer
    from dev_team.agents.frontend_engineer import build_frontend_engineer
    from dev_team.agents.security_engineer import build_security_engineer

    devops = build_devops_engineer(config)
    members = [
        devops,
        build_security_engineer(config),
        build_backend_engineer(config),
        build_frontend_engineer(config),
    ]

    return Team(
        name="incident_response_team",
        members=members,
        mode="collaborate",
    )


__all__ = ["build_incident_response_team"]
