"""Facade imported by ``mcp/noctusai/tools/noctus/team/*`` MCP tools.

Centralizes the small set of operations the MCP layer needs from
:mod:`dev_team` so the MCP tools stay thin.

Public surface (contract):
    run_team(task: str, project: str | None, config: str = "default") -> dict
    team_status(project: str | None = None) -> dict
    route_decision(task: str) -> dict
    metrics_snapshot(scope: str | None = None) -> dict
    agent_metrics(name: str, scope: str | None = None) -> dict
    set_agent_config(name: str, model: str | None, provider: str | None,
                     config_name: str = "default") -> dict

The MCP F engineer wraps each of these in a Pydantic-In/Out tool module.
"""

from __future__ import annotations

import os
from typing import Any

from dev_team.configs import list_configs, load_config, save_config
from dev_team.memory import MemoryStore
from dev_team.team import build_team, recommend_route
from dev_team.telemetry import get_agent_metrics, get_metrics


def run_team(
    task: str,
    project: str | None = None,
    config: str = "default",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fire the team. Returns a JSON-serializable result envelope.

    If ``ANTHROPIC_API_KEY`` is missing AND ``dry_run`` is False, returns
    an explicit "switch not flipped" envelope rather than crashing — the
    MCP caller (Claude Code) surfaces this to the user verbatim.
    """
    if not dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        return {
            "status": "switch-not-flipped",
            "summary": (
                "ANTHROPIC_API_KEY is not set. The agno team is scaffolded and "
                "ready, but no LLM provider key is configured. To activate: "
                "export ANTHROPIC_API_KEY=sk-ant-... then re-invoke."
            ),
            "task": task,
        }
    team = build_team(config_name=config)
    if dry_run:
        return {
            "status": "dry-run",
            "summary": "Team built; no LLM call made.",
            "members": [getattr(m, "name", repr(m)) for m in getattr(team, "members", [])],
        }
    result = team.run(task)
    return {
        "status": "ok",
        "summary": getattr(result, "content", str(result)),
        "task": task,
        "project": project,
        "config": config,
    }


def team_status(project: str | None = None) -> dict[str, Any]:
    """Return current team state from memory."""
    return MemoryStore(project=project).snapshot()


def route_decision(task: str) -> dict[str, Any]:
    """Team-vs-direct heuristic."""
    return recommend_route(task)


def metrics_snapshot(scope: str | None = None) -> dict[str, Any]:
    """Top-level metrics rollup across all agents in the scope."""
    return get_metrics(scope=scope)


def agent_metrics(name: str, scope: str | None = None) -> dict[str, Any]:
    """Per-agent metrics rollup."""
    return get_agent_metrics(name, scope=scope)


def set_agent_config(
    name: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    config_name: str = "default",
) -> dict[str, Any]:
    """Customize an agent's model / provider in the named YAML config.

    Loads → patches → saves. Returns the new config dict.
    """
    cfg = load_config(config_name)
    agents = cfg.setdefault("agents", {})
    role = agents.setdefault(name, {})
    if model is not None:
        role["model"] = model
    if provider is not None:
        role["provider"] = provider
    save_config(config_name, cfg)
    return cfg


__all__ = [
    "run_team",
    "team_status",
    "route_decision",
    "metrics_snapshot",
    "agent_metrics",
    "set_agent_config",
    "list_configs",
]
