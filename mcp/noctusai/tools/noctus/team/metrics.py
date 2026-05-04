"""``noctus.team.metrics`` — top-level dev-team metrics rollup.

Wraps :func:`dev_team.mcp_facade.metrics_snapshot`. The rollup shape is
engineer-extensible (engineer C ships :mod:`dev_team.telemetry.rollups`),
so output is a dict passthrough — schema stays stable while the inner
keys grow.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetricsInput(BaseModel):
    scope: str | None = Field(
        default=None,
        description=(
            "Optional scope filter (project name, time window, agent group). "
            "When None, the global rollup across all events is returned."
        ),
    )


class MetricsOutput(BaseModel):
    rollup: dict[str, Any] = Field(
        description=(
            "Metrics rollup dict — passthrough from telemetry.get_metrics. "
            "Stub keys today: scope, total_events, total_cost_usd, agents (per-agent breakdown)."
        )
    )


def register(server) -> None:
    @server.tool(
        name="noctus.team.metrics",
        description=(
            "Return the top-level metrics rollup across the agno dev team: "
            "total events, total cost (USD), per-agent breakdown. Read-only."
        ),
    )
    def _handler(payload: MetricsInput) -> MetricsOutput:
        from dev_team.mcp_facade import metrics_snapshot

        rollup = metrics_snapshot(scope=payload.scope)
        return MetricsOutput(rollup=rollup)
