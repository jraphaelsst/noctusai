"""dev_team sub-teams — design_review_team, code_review_team,
incident_response_team.

Each sub-team module exports ``build_<sub_team>(config) -> Team`` that
returns an agno collaborate-mode Team. The Leader invokes these via the
``invoke_subteam`` tool (Leader-only allowlist entry).

Implementations land in E engineer's scope.
"""

from __future__ import annotations

try:  # pragma: no cover
    from dev_team.teams.code_review_team import build_code_review_team  # type: ignore
    from dev_team.teams.design_review_team import build_design_review_team  # type: ignore
    from dev_team.teams.incident_response_team import build_incident_response_team  # type: ignore
except ImportError:

    def build_design_review_team(config):  # type: ignore[no-redef]
        raise NotImplementedError(
            "design_review_team not wired yet — E engineer ships teams/design_review_team.py"
        )

    def build_code_review_team(config):  # type: ignore[no-redef]
        raise NotImplementedError(
            "code_review_team not wired yet — E engineer ships teams/code_review_team.py"
        )

    def build_incident_response_team(config):  # type: ignore[no-redef]
        raise NotImplementedError(
            "incident_response_team not wired yet — E engineer ships teams/incident_response_team.py"
        )


__all__ = [
    "build_design_review_team",
    "build_code_review_team",
    "build_incident_response_team",
]
