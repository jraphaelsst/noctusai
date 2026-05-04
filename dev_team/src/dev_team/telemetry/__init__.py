"""dev_team telemetry — captures every agent turn for measurability.

Captured per event:
    timestamp, project, agent_name, sub_team (or null), turn_index,
    input_tokens, output_tokens, total_cost_usd, latency_ms,
    tool_calls (jsonb-shaped list), outcome ("ok" | "error" | "timeout"),
    output_chars

Stored at ``dev_team/src/dev_team/memory/store/telemetry.sqlite`` —
sibling to the project memory SQLite. Schema-versioned via a
``schema_version`` table; migrations land in ``telemetry/migrations/``.

Public surface (contract):
    capture_event(event: TelemetryEvent) -> None
    get_metrics(scope: str | None = None) -> dict        # rollup
    get_agent_metrics(name: str, scope: str | None = None) -> dict

Stub behavior (until engineer ships): :func:`capture_event` is a no-op;
:func:`get_metrics` returns an empty rollup. Real impl by C engineer.
"""

from __future__ import annotations

from typing import Any

# Re-export real implementation if engineer's modules have shipped.
try:  # pragma: no cover — flips to real impl when engineer ships
    from dev_team.telemetry.capture import capture_event  # type: ignore
    from dev_team.telemetry.rollups import get_agent_metrics, get_metrics  # type: ignore
except ImportError:

    def capture_event(event: dict[str, Any]) -> None:  # type: ignore[no-redef]
        """Stub — no-op until C engineer ships dev_team.telemetry.capture."""
        return None

    def get_metrics(scope: str | None = None) -> dict[str, Any]:  # type: ignore[no-redef]
        """Stub — returns empty rollup until engineer ships rollups.py."""
        return {
            "scope": scope,
            "total_events": 0,
            "total_cost_usd": 0.0,
            "agents": {},
        }

    def get_agent_metrics(name: str, scope: str | None = None) -> dict[str, Any]:  # type: ignore[no-redef]
        """Stub — returns empty per-agent metrics until engineer ships."""
        return {
            "agent": name,
            "scope": scope,
            "events": 0,
            "total_cost_usd": 0.0,
            "avg_latency_ms": None,
            "success_rate": None,
            "tool_call_distribution": {},
        }


__all__ = ["capture_event", "get_metrics", "get_agent_metrics"]
