"""``noctus.team.status`` — current dev-team state from memory.

Wraps :func:`dev_team.mcp_facade.team_status`. The facade returns the
:class:`dev_team.memory.MemoryStore.snapshot` shape — a dict whose
keys depend on the engineer-shipped MemoryStore (project / current_phase /
last_verification today, more later). Output is intentionally a dict
passthrough so the schema absorbs new keys without an MCP-side change.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StatusInput(BaseModel):
    project: str | None = Field(
        default=None,
        description=(
            "Optional project scope. When None, the global / unscoped memory "
            "snapshot is returned."
        ),
    )


class StatusOutput(BaseModel):
    snapshot: dict[str, Any] = Field(
        description=(
            "Memory snapshot dict — passthrough from MemoryStore.snapshot(). "
            "Keys: project, current_phase, last_verification, ... (engineer-extensible)."
        )
    )


def register(server) -> None:
    @server.tool(
        name="noctus.team.status",
        description=(
            "Return the dev team's current state from memory: project, "
            "current_phase, last_verification, etc. Read-only; safe to call "
            "frequently."
        ),
    )
    def _handler(payload: StatusInput) -> StatusOutput:
        from dev_team.mcp_facade import team_status

        snapshot = team_status(project=payload.project)
        return StatusOutput(snapshot=snapshot)
