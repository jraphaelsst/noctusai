"""``noctus.team.run`` — fire the agno dev team on a task.

Wraps :func:`dev_team.mcp_facade.run_team`. Returns a JSON-serializable
envelope describing what happened (or why nothing happened — e.g. the
``ANTHROPIC_API_KEY`` switch hasn't been flipped yet).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunInput(BaseModel):
    task: str = Field(description="Task description handed to the team Leader.")
    project: str | None = Field(
        default=None,
        description=(
            "Optional project scope (used by memory + telemetry to bucket the "
            "session). Examples: 'agno-dev-team-rollout', 'pf-metas-seed-wiring'."
        ),
    )
    config: str = Field(
        default="default",
        description=(
            "Named YAML config under dev_team/src/dev_team/configs/<config>.yaml. "
            "Picks model / provider per agent role."
        ),
    )
    dry_run: bool = Field(
        default=False,
        description=(
            "If true, build the team but do NOT make any LLM call. Useful for "
            "smoke-testing wiring without spending API tokens."
        ),
    )


class RunOutput(BaseModel):
    status: str = Field(
        description=(
            "One of: 'ok' (team ran), 'dry-run' (built, no LLM call), "
            "'switch-not-flipped' (no ANTHROPIC_API_KEY)."
        )
    )
    summary: str = Field(
        description="Human-readable summary or the team's content output."
    )
    task: str | None = Field(default=None, description="Echo of the input task.")
    project: str | None = Field(default=None, description="Echo of the project scope.")
    config: str | None = Field(default=None, description="Echo of the config name.")
    members: list[str] | None = Field(
        default=None,
        description="Dry-run only: list of agent member names assembled.",
    )


def _to_output(envelope: dict[str, Any]) -> RunOutput:
    """Adapt the facade's dict envelope to the typed output."""
    return RunOutput(
        status=envelope.get("status", "unknown"),
        summary=envelope.get("summary", ""),
        task=envelope.get("task"),
        project=envelope.get("project"),
        config=envelope.get("config"),
        members=envelope.get("members"),
    )


def register(server) -> None:
    @server.tool(
        name="noctus.team.run",
        description=(
            "Fire the agno dev team on a task. Returns an envelope with "
            "status (ok / dry-run / switch-not-flipped) and a summary. "
            "Use dry_run=True to verify wiring without an LLM call."
        ),
    )
    def _handler(payload: RunInput) -> RunOutput:
        # Lazy import: keeps MCP server cold-start light; agno only loads
        # when this tool is actually invoked.
        from dev_team.mcp_facade import run_team

        envelope = run_team(
            task=payload.task,
            project=payload.project,
            config=payload.config,
            dry_run=payload.dry_run,
        )
        return _to_output(envelope)
