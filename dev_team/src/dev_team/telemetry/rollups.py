"""Telemetry rollups — global + per-agent metrics queries.

Two public functions:

- :func:`get_metrics` — global rollup over a scope. Returns totals
  (events, cost, tokens) plus a per-agent breakdown.
- :func:`get_agent_metrics` — per-agent rollup: events, cost,
  avg latency, success rate, tool-call distribution.

``scope`` accepts:
- ``None`` — all-time, no filter.
- ``"last_N_days"`` (e.g. ``"last_7_days"``) — events with
  ``timestamp >= now - N days``.
- any other string — treated as a project slug (filters
  ``project = scope``).
"""
from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

from noctusai_lib.primitives.timeutil import now_utc

from dev_team.telemetry.store import connect

_LAST_N_DAYS_RE = re.compile(r"^last_(\d+)_days?$")


def _scope_clause(scope: str | None) -> tuple[str, list[Any]]:
    """Return (sql_where_fragment, params) for the given scope.

    Empty string + empty list when scope is None (no filter).
    """
    if scope is None:
        return "", []
    match = _LAST_N_DAYS_RE.match(scope)
    if match:
        days = int(match.group(1))
        cutoff = (now_utc() - timedelta(days=days)).isoformat()
        return " WHERE timestamp >= ?", [cutoff]
    # Otherwise: treat as project slug.
    return " WHERE project = ?", [scope]


def get_metrics(scope: str | None = None) -> dict[str, Any]:
    """Global rollup over the given scope.

    Returns::

        {
            "scope": <as-passed>,
            "total_events": int,
            "total_input_tokens": int,
            "total_output_tokens": int,
            "total_cost_usd": float,
            "agents": {
                "<agent>": {
                    "events": int,
                    "cost": float,
                    "input_tokens": int,
                    "output_tokens": int,
                    "avg_latency_ms": float | None,
                    "success_rate": float | None,
                },
                ...
            },
        }
    """
    where, params = _scope_clause(scope)
    with connect() as conn:
        # Globals
        row = conn.execute(
            "SELECT COUNT(*) as n, COALESCE(SUM(input_tokens), 0) as inp,"
            " COALESCE(SUM(output_tokens), 0) as out,"
            " COALESCE(SUM(total_cost_usd), 0.0) as cost"
            " FROM events" + where,
            params,
        ).fetchone()
        total_events = int(row["n"]) if row else 0
        total_input = int(row["inp"]) if row else 0
        total_output = int(row["out"]) if row else 0
        total_cost = float(row["cost"]) if row else 0.0

        # Per-agent
        per_agent_rows = conn.execute(
            "SELECT agent_name,"
            " COUNT(*) as n,"
            " COALESCE(SUM(input_tokens), 0) as inp,"
            " COALESCE(SUM(output_tokens), 0) as out,"
            " COALESCE(SUM(total_cost_usd), 0.0) as cost,"
            " AVG(latency_ms) as avg_lat,"
            " SUM(CASE WHEN outcome = 'ok' THEN 1 ELSE 0 END) as ok_n"
            " FROM events" + where + " GROUP BY agent_name",
            params,
        ).fetchall()

    agents: dict[str, dict[str, Any]] = {}
    for r in per_agent_rows:
        n = int(r["n"])
        agents[r["agent_name"]] = {
            "events": n,
            "cost": float(r["cost"] or 0.0),
            "input_tokens": int(r["inp"] or 0),
            "output_tokens": int(r["out"] or 0),
            "avg_latency_ms": float(r["avg_lat"]) if r["avg_lat"] is not None else None,
            "success_rate": (int(r["ok_n"]) / n) if n else None,
        }

    return {
        "scope": scope,
        "total_events": total_events,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cost_usd": total_cost,
        "agents": agents,
    }


def get_agent_metrics(name: str, scope: str | None = None) -> dict[str, Any]:
    """Per-agent rollup: events, cost, avg latency, success rate, tool dist.

    Returns::

        {
            "agent": <name>,
            "scope": <as-passed>,
            "events": int,
            "total_cost_usd": float,
            "input_tokens": int,
            "output_tokens": int,
            "avg_latency_ms": float | None,
            "success_rate": float | None,
            "tool_call_distribution": {
                "<tool_name>": int,
                ...
            },
        }
    """
    where, params = _scope_clause(scope)
    if where:
        where += " AND agent_name = ?"
    else:
        where = " WHERE agent_name = ?"
    params = [*params, name]

    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as n,"
            " COALESCE(SUM(input_tokens), 0) as inp,"
            " COALESCE(SUM(output_tokens), 0) as out,"
            " COALESCE(SUM(total_cost_usd), 0.0) as cost,"
            " AVG(latency_ms) as avg_lat,"
            " SUM(CASE WHEN outcome = 'ok' THEN 1 ELSE 0 END) as ok_n"
            " FROM events" + where,
            params,
        ).fetchone()
        tool_rows = conn.execute(
            "SELECT tool_calls FROM events" + where + " AND tool_calls IS NOT NULL",
            params,
        ).fetchall()

    n = int(row["n"]) if row else 0
    distribution: dict[str, int] = {}
    for tr in tool_rows:
        raw = tr["tool_calls"]
        if not raw:
            continue
        try:
            calls = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(calls, list):
            continue
        for call in calls:
            if isinstance(call, dict):
                tn = call.get("name") or "unknown"
            else:
                tn = str(call)
            distribution[tn] = distribution.get(tn, 0) + 1

    return {
        "agent": name,
        "scope": scope,
        "events": n,
        "total_cost_usd": float(row["cost"] or 0.0) if row else 0.0,
        "input_tokens": int(row["inp"] or 0) if row else 0,
        "output_tokens": int(row["out"] or 0) if row else 0,
        "avg_latency_ms": (
            float(row["avg_lat"]) if row and row["avg_lat"] is not None else None
        ),
        "success_rate": (int(row["ok_n"]) / n) if (row and n) else None,
        "tool_call_distribution": distribution,
    }


__all__ = ["get_metrics", "get_agent_metrics"]
