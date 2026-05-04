"""``noctus.team.agent_metrics`` — per-agent metrics rollup.

Wraps :func:`dev_team.mcp_facade.agent_metrics`. Returns a dict
passthrough so the schema absorbs new keys (avg_latency_ms,
success_rate, tool_call_distribution, ...) as engineer C extends
:mod:`dev_team.telemetry.rollups`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentMetricsInput(BaseModel):
    name: str = Field(
        description=(
            "Agent role name (e.g. 'leader', 'product_manager', "
            "'backend_engineer', 'security_engineer', 'code_reviewer')."
        )
    )
    scope: str | None = Field(
        default=None,
        description="Optional scope filter (project / time window).",
    )


class AgentMetricsOutput(BaseModel):
    metrics: dict[str, Any] = Field(
        description=(
            "Per-agent metrics dict — passthrough from telemetry.get_agent_metrics. "
            "Stub keys today: agent, scope, events, total_cost_usd, "
            "avg_latency_ms, success_rate, tool_call_distribution."
        )
    )


def register(server) -> None:
    @server.tool(
        name="noctus.team.agent_metrics",
        description=(
            "Return per-agent metrics for one of the 11 dev-team specialists: "
            "events, total cost (USD), avg latency, success rate, tool-call "
            "distribution. Read-only."
        ),
    )
    def _handler(payload: AgentMetricsInput) -> AgentMetricsOutput:
        from dev_team.mcp_facade import agent_metrics

        rollup = agent_metrics(name=payload.name, scope=payload.scope)
        return AgentMetricsOutput(metrics=rollup)
