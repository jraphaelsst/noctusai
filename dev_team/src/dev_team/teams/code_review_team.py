"""code_review_team — collaborate-mode sub-team.

Per design-reference.md §1.2 + §2.10 (Code Reviewer LEADS):

    Code Reviewer (lead) + Security + QA

Invoked by the Leader after every code-touching phase
(design-reference.md §1.3 step 9). Code Reviewer covers
maintainability + idiomatic + standards; Security covers OWASP /
auth / secrets / threat modelling; they sit together for parallel
review (not redundant) per design-reference.md §2.10.

Public surface:
    build_code_review_team(config) -> agno.team.Team
"""

from __future__ import annotations

from typing import Any, Mapping


def build_code_review_team(config: Mapping[str, Any]):
    """Assemble the code_review_team in collaborate mode.

    Returns
    -------
    agno.team.Team

    Notes
    -----
    Imports are LOCAL — see :func:`dev_team.teams.design_review_team.build_design_review_team`
    for the rationale.
    """
    from agno.team import Team

    from dev_team.agents.code_reviewer import build_code_reviewer
    from dev_team.agents.qa_engineer import build_qa_engineer
    from dev_team.agents.security_engineer import build_security_engineer

    code_reviewer = build_code_reviewer(config)
    members = [
        code_reviewer,
        build_security_engineer(config),
        build_qa_engineer(config),
    ]

    return Team(
        name="code_review_team",
        members=members,
        mode="collaborate",
    )


__all__ = ["build_code_review_team"]
