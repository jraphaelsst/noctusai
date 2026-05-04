"""Single chokepoint between product HTTP routes and the engine.

Every router endpoint imports from this module instead of `dev_team.*`
directly. Reasons (per MASTER-PROMPT.md):
  - Test isolation: tests can `patch.object(dev_team_proxy, "<fn>", ...)`.
  - Per-tenant injection: `org_id` scoping lands here when the engine
    grows multi-tenant primitives.
  - Engine evolution insulation: facade signature drift is a one-file
    change here, not 4 router patches.

The functions here intentionally stay thin — they pass through to
:mod:`dev_team.mcp_facade` and :mod:`dev_team.configs`.

The ``last_24h_cost``-style snapshot enrichments for the agents-grid
endpoint live here too (engine doesn't ship a "snapshot per agent"
operation; the product needs it for the grid; one wrap call assembles it
from existing facade ops).
"""
from __future__ import annotations

from typing import Any

# These imports are lazy-resolved through the dev_team package; the engine
# uses PEP 562 lazy attrs so importing dev_team itself is cheap.
from dev_team import mcp_facade as _facade  # type: ignore[import-not-found]
from dev_team.configs import list_configs as _list_configs  # type: ignore[import-not-found]
from dev_team.configs import load_config as _load_config  # type: ignore[import-not-found]


# Canonical 11-agent roster (mirrors dev_team.configs default + sibling
# spec). Kept here so the agents-grid endpoint has a stable order that
# isn't dict-key-iteration-order-dependent.
AGENT_NAMES = (
    "leader",
    "product_manager",
    "ux_designer",
    "solution_architect",
    "backend_engineer",
    "frontend_engineer",
    "devops_engineer",
    "security_engineer",
    "qa_engineer",
    "code_reviewer",
    "technical_writer",
)


def run_team(task: str, project: str | None = None, config: str = "default") -> dict[str, Any]:
    """Fire the team. Pass-through with explicit kw-mapping."""
    return _facade.run_team(task=task, project=project, config=config)


def metrics_snapshot(scope: str | None = None) -> dict[str, Any]:
    """Global rollup."""
    return _facade.metrics_snapshot(scope=scope)


def agent_metrics(name: str, scope: str | None = None) -> dict[str, Any]:
    """Per-agent rollup."""
    return _facade.agent_metrics(name=name, scope=scope)


def list_configs() -> list[str]:
    """Names of all configs the engine knows about."""
    return list(_list_configs())


def load_config(name: str = "default") -> dict[str, Any]:
    """Full config dict for one named config."""
    return _load_config(name)


def set_agent_config(
    config_name: str,
    *,
    agent_name: str,
    model: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Patch one agent's model / provider in the named config."""
    return _facade.set_agent_config(
        agent_name,
        model=model,
        provider=provider,
        config_name=config_name,
    )


def list_agents_snapshot(scope: str = "last_24_hours") -> list[dict[str, Any]]:
    """Build the agents-grid snapshot.

    For each of the 11 canonical agents, return:
        {name, model, last_24h_events, last_24h_cost, success_rate}

    Implementation: one engine round-trip per agent (cheap — engine returns
    pre-rolled aggregates from SQLite). Model is read from the active
    "default" config, not the runtime team (we don't instantiate agno just
    to render a grid).
    """
    cfg = _load_config("default")
    agents_cfg = cfg.get("agents", {}) if isinstance(cfg, dict) else {}
    out: list[dict[str, Any]] = []
    for name in AGENT_NAMES:
        per_agent_cfg = agents_cfg.get(name, {}) or {}
        model = per_agent_cfg.get("model", "unknown")
        try:
            metrics = _facade.agent_metrics(name=name, scope=scope) or {}
        except Exception:
            # Engine surfaces empty rollups for unknown scopes; keep this
            # endpoint resilient — a missing rollup is a 0-event agent,
            # not an HTTP error.
            metrics = {}
        out.append(
            {
                "name": name,
                "model": model,
                "last_24h_events": int(metrics.get("events", 0) or 0),
                "last_24h_cost": float(metrics.get("cost", 0.0) or 0.0),
                "success_rate": float(metrics.get("success_rate", 0.0) or 0.0),
            }
        )
    return out
