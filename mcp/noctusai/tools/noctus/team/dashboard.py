"""``noctus.team.dashboard`` — dev-team status composite.

Rollup of ``noctus.team.status`` + ``noctus.team.metrics`` +
``noctus.team.agent_metrics`` into a single dashboard read. Eliminates
3+ round-trips when the agent or user just wants *"how is the team
doing right now?"*.

Read-only; pure composition — each upstream tool is the source of
truth for its slice. The dashboard does no aggregation beyond stuffing
the three rollups into one envelope.

Surfaced as fusion candidate by ``noctus.seed.scan_fusions`` (multiple
pairs above 0.50 — all tools take ``payload`` and share the
``team`` / ``agent`` / ``agno`` vocabulary).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field


class DashboardInput(BaseModel):
    project: str | None = Field(
        default=None,
        description=(
            "Optional project scope. Forwarded to status / metrics. "
            "When None, returns the global / unscoped rollups."
        ),
    )
    scope: str | None = Field(
        default=None,
        description=(
            "Optional metrics scope (overrides project for the metrics + "
            "agent-metrics calls if you want a different time window). "
            "When None, falls back to `project`."
        ),
    )
    agents: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of agent role names to include per-agent "
            "metrics for (e.g. ['leader', 'backend_engineer']). When "
            "None, only top-level metrics are returned (agents:{} empty)."
        ),
    )


class DashboardOutput(BaseModel):
    snapshot: dict[str, Any] = Field(
        description="Memory snapshot from team_status (project, current_phase, last_verification, …).",
    )
    metrics: dict[str, Any] = Field(
        description="Top-level metrics rollup (total_events, total_cost_usd, agents breakdown).",
    )
    agents: dict[str, dict[str, Any]] = Field(
        description=(
            "Per-role dev-team TELEMETRY keyed by agno role name (leader, "
            "backend_engineer, ...): `dev_team.mcp_facade.agent_metrics`, the "
            "same source as `metrics` ({agent, events, total_cost_usd, ...}). "
            "Empty dict when the caller didn't pass `agents`. NOT the "
            "slice-score quality rollup -- that is `slice_scores` (Claude "
            "specialists, `noctus.team.agent_metrics`); different domains."
        ),
    )
    slice_scores: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Slice-score rollup from noctus.team.agent_metrics (per agent+model: "
            "mean_q_weighted, first_pass_yield, rework_rate, tokens_per_accepted_slice, "
            "cost_usd_est; `cost_note` explains the estimate; `by_week` is the weekly trend)."
        ),
    )
    errors: list[str] = Field(
        default_factory=list,
        description=(
            "Soft errors per upstream call. The dashboard never raises — "
            "if the agno facade is unavailable, errors[] is populated and "
            "the failed slice is empty."
        ),
    )


def dashboard(
    *,
    project: str | None = None,
    scope: str | None = None,
    agents: list[str] | None = None,
    slice_scores_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compose status + metrics + per-agent metrics into one envelope.

    Returns:
        ``{
          "snapshot": {...},   # team_status passthrough
          "metrics": {...},    # metrics_snapshot passthrough
          "agents": {role: {...}},  # per-agent metrics
          "errors": [str],     # soft errors per slice
        }``
    """
    effective_scope = scope if scope is not None else project
    snapshot: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    per_agent: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    try:
        from dev_team.mcp_facade import team_status
        snapshot = team_status(project=project)
    except Exception as exc:  # noqa: BLE001 — soft-fail by contract
        errors.append(f"team_status: {type(exc).__name__}: {exc}")

    try:
        from dev_team.mcp_facade import metrics_snapshot
        metrics = metrics_snapshot(scope=effective_scope)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"metrics_snapshot: {type(exc).__name__}: {exc}")

    if agents:
        for role in agents:
            try:
                from dev_team.mcp_facade import agent_metrics
                per_agent[role] = agent_metrics(name=role, scope=effective_scope)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"agent_metrics[{role}]: {type(exc).__name__}: {exc}"
                )

    slice_scores: dict[str, Any] = {}
    try:
        if slice_scores_fn is None:
            from tools.noctus.team.agent_metrics import agent_metrics as slice_scores_fn
        name = "*"
        slice_scores = slice_scores_fn(name, effective_scope, False)
        slice_scores["by_week"] = slice_scores_fn(name, effective_scope, True)["groups"]
    except Exception as exc:  # noqa: BLE001 — soft-fail by contract
        slice_scores = {}
        errors.append(f"slice_scores: {type(exc).__name__}: {exc}")

    return {
        "snapshot": snapshot,
        "metrics": metrics,
        "agents": per_agent,
        "slice_scores": slice_scores,
        "errors": errors,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.team.dashboard",
        description=(
            "Dev-team dashboard: composes team.status + team.metrics + "
            "team.agent_metrics into one read. Pass `agents=[role, ...]` "
            "to include per-agent metrics for specific specialists. "
            "Read-only; soft-fails per upstream slice (errors[] populated, "
            "non-failed slices still returned)."
        ),
    )
    def _handler(payload: DashboardInput) -> DashboardOutput:
        result = dashboard(
            project=payload.project,
            scope=payload.scope,
            agents=payload.agents,
        )
        return DashboardOutput(**result)
