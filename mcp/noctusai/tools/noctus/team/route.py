"""``noctus.team.route`` — team-vs-direct routing recommendation.

Wraps :func:`dev_team.mcp_facade.route_decision`. The heuristic is owned
by ``dev_team.team.recommend_route`` (engineer E ships the real rules);
the MCP layer is a thin pass-through.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RouteInput(BaseModel):
    task: str = Field(
        description=(
            "Task description used to decide between firing the full agno "
            "team or staying direct in Claude Code."
        )
    )


class RouteOutput(BaseModel):
    recommended: str = Field(
        description="One of: 'team' | 'direct' — the recommended route."
    )
    rationale: str = Field(
        description="Short, human-readable justification for the recommendation."
    )


def register(server) -> None:
    @server.tool(
        name="noctus.team.route",
        description=(
            "Recommend whether a task should fire the full agno dev team or "
            "stay direct in Claude Code. Returns {recommended, rationale}. "
            "Trivial / one-shot signals (typo, rename, format, ...) tend "
            "toward 'direct'; multi-domain / ambiguous-scope toward 'team'."
        ),
    )
    def _handler(payload: RouteInput) -> RouteOutput:
        from dev_team.mcp_facade import route_decision

        decision = route_decision(task=payload.task)
        return RouteOutput(
            recommended=decision.get("recommended", "team"),
            rationale=decision.get("rationale", ""),
        )
