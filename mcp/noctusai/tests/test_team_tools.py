"""Tests for ``noctus.team.*`` MCP tools.

Covers:
  - ``register_all`` registers all 6 tools without error.
  - Each tool's Pydantic In / Out schema has the expected fields.
  - Each handler wraps the corresponding ``dev_team.mcp_facade`` function
    and shapes its return as the typed Output.

Patches at the wrap boundary (``dev_team.mcp_facade.<fn>``) per the
``unittest.mock.patch.object`` carve-out for external integrations: the
``dev_team`` package is treated as an independent system from the MCP
layer, so patching its public facade is the natural seam (NOT
patching ``mcp/noctusai`` internals).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Standard test bootstrap mirrored from sibling MCP test files
# (e.g. tests/test_google_calendar_tools.py): add mcp/noctusai/ to sys.path
# so the bare-name imports (`from tools.noctus.team...`) resolve.
MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

# Also add dev_team/src to sys.path so `from dev_team.mcp_facade import ...`
# resolves from inside the lazy handler imports. dev_team isn't pip-installed
# in this worktree's MCP venv yet — engineer D wires that in a later batch.
REPO_ROOT = MCP_ROOT.parents[1]
DEV_TEAM_SRC = REPO_ROOT / "dev_team" / "src"
if str(DEV_TEAM_SRC) not in sys.path:
    sys.path.insert(0, str(DEV_TEAM_SRC))

import pytest  # noqa: E402

from tools.noctus.team import register_all  # noqa: E402
from tools.noctus.team.agent_metrics import (  # noqa: E402
    AgentMetricsInput,
    AgentMetricsOutput,
)
from tools.noctus.team.agent_metrics import register as agent_metrics_register  # noqa: E402
from tools.noctus.team.configure import (  # noqa: E402
    ConfigureInput,
    ConfigureOutput,
)
from tools.noctus.team.configure import register as configure_register  # noqa: E402
from tools.noctus.team.metrics import (  # noqa: E402
    MetricsInput,
    MetricsOutput,
)
from tools.noctus.team.metrics import register as metrics_register  # noqa: E402
from tools.noctus.team.route import RouteInput, RouteOutput  # noqa: E402
from tools.noctus.team.route import register as route_register  # noqa: E402
from tools.noctus.team.run import RunInput, RunOutput  # noqa: E402
from tools.noctus.team.run import register as run_register  # noqa: E402
from tools.noctus.team.status import StatusInput, StatusOutput  # noqa: E402
from tools.noctus.team.status import register as status_register  # noqa: E402


# ---------------------------------------------------------------------------
# Test FastMCP — minimal stand-in that records every @server.tool registration.
# Mirrors the pattern other MCP tool tests use to avoid spinning a real
# FastMCP just to assert wiring shape.
# ---------------------------------------------------------------------------


class _RecordingServer:
    """Records ``@server.tool(...)`` registrations for assertion.

    Captures (name, description, handler) tuples. The decorator returns
    the original function unchanged so the handler stays callable.
    """

    def __init__(self) -> None:
        self.registered: list[tuple[str, str, callable]] = []

    def tool(self, *, name: str, description: str = ""):
        def _decorator(fn):
            self.registered.append((name, description, fn))
            return fn

        return _decorator


# ---------------------------------------------------------------------------
# register_all — wiring shape
# ---------------------------------------------------------------------------


def test_register_all_registers_all_seven_tools():
    server = _RecordingServer()
    register_all(server)
    names = [name for name, _, _ in server.registered]

    # `noctus.team.dashboard` (the scan_fusions-built rollup) joined the set;
    # the count assertion was frozen at 6 and went stale when it landed.
    expected = {
        "noctus.team.agent_metrics",
        "noctus.team.configure",
        "noctus.team.dashboard",
        "noctus.team.metrics",
        "noctus.team.route",
        "noctus.team.run",
        "noctus.team.status",
    }
    assert set(names) == expected
    assert len(names) == 7, f"expected 7 unique tools, got {len(names)}: {names}"


def test_register_all_descriptions_are_non_empty():
    server = _RecordingServer()
    register_all(server)
    for name, desc, _ in server.registered:
        assert desc, f"{name} has empty description"


# ---------------------------------------------------------------------------
# Pydantic schemas — expected fields
# ---------------------------------------------------------------------------


def test_run_input_fields():
    fields = set(RunInput.model_fields.keys())
    assert fields == {"task", "project", "config", "dry_run"}


def test_run_output_fields():
    fields = set(RunOutput.model_fields.keys())
    assert {"status", "summary"}.issubset(fields)
    # Optional echo + dry-run fields
    assert {"task", "project", "config", "members"}.issubset(fields)


def test_status_input_fields():
    assert set(StatusInput.model_fields.keys()) == {"project"}


def test_status_output_fields():
    assert set(StatusOutput.model_fields.keys()) == {"snapshot"}


def test_route_input_fields():
    assert set(RouteInput.model_fields.keys()) == {"task"}


def test_route_output_fields():
    assert set(RouteOutput.model_fields.keys()) == {"recommended", "rationale"}


def test_metrics_input_fields():
    assert set(MetricsInput.model_fields.keys()) == {"scope"}


def test_metrics_output_fields():
    assert set(MetricsOutput.model_fields.keys()) == {"rollup"}


def test_agent_metrics_input_fields():
    assert set(AgentMetricsInput.model_fields.keys()) == {"name", "scope"}


def test_agent_metrics_output_fields():
    assert set(AgentMetricsOutput.model_fields.keys()) == {"metrics"}


def test_configure_input_fields():
    assert set(ConfigureInput.model_fields.keys()) == {
        "name",
        "model",
        "provider",
        "config_name",
    }


def test_configure_output_fields():
    assert set(ConfigureOutput.model_fields.keys()) == {"config"}


# ---------------------------------------------------------------------------
# Handler dry calls — patch the dev_team.mcp_facade boundary, verify
# the returned envelope shape lands on the typed Output.
# ---------------------------------------------------------------------------


def _register_one(register_fn) -> tuple[str, callable]:
    """Helper: register one tool on a fresh server, return (name, handler)."""
    server = _RecordingServer()
    register_fn(server)
    assert len(server.registered) == 1, "register() should add exactly one tool"
    name, _, handler = server.registered[0]
    return name, handler


def test_run_handler_wraps_facade_envelope():
    name, handler = _register_one(run_register)
    assert name == "noctus.team.run"

    fake_envelope = {
        "status": "switch-not-flipped",
        "summary": "ANTHROPIC_API_KEY is not set.",
        "task": "do the thing",
    }
    with patch("dev_team.mcp_facade.run_team", return_value=fake_envelope) as m:
        out = handler(RunInput(task="do the thing"))

    assert isinstance(out, RunOutput)
    assert out.status == "switch-not-flipped"
    assert out.summary == "ANTHROPIC_API_KEY is not set."
    assert out.task == "do the thing"
    m.assert_called_once_with(
        task="do the thing", project=None, config="default", dry_run=False
    )


def test_run_handler_dry_run_passes_through_members():
    _, handler = _register_one(run_register)
    fake = {
        "status": "dry-run",
        "summary": "Team built; no LLM call made.",
        "members": ["leader", "product_manager", "backend_engineer"],
    }
    with patch("dev_team.mcp_facade.run_team", return_value=fake):
        out = handler(RunInput(task="x", dry_run=True))
    assert out.status == "dry-run"
    assert out.members == ["leader", "product_manager", "backend_engineer"]


def test_status_handler_wraps_snapshot():
    name, handler = _register_one(status_register)
    assert name == "noctus.team.status"

    fake_snapshot = {
        "project": "agno-dev-team-rollout",
        "current_phase": "B2",
        "last_verification": "2026-05-04T03:14:15-03:00",
    }
    with patch("dev_team.mcp_facade.team_status", return_value=fake_snapshot) as m:
        out = handler(StatusInput(project="agno-dev-team-rollout"))

    assert isinstance(out, StatusOutput)
    assert out.snapshot == fake_snapshot
    m.assert_called_once_with(project="agno-dev-team-rollout")


def test_status_handler_default_project_is_none():
    _, handler = _register_one(status_register)
    with patch("dev_team.mcp_facade.team_status", return_value={}) as m:
        handler(StatusInput())
    m.assert_called_once_with(project=None)


def test_route_handler_wraps_decision():
    name, handler = _register_one(route_register)
    assert name == "noctus.team.route"

    fake_decision = {
        "recommended": "direct",
        "rationale": "Trivial / one-shot signal in task description.",
    }
    with patch("dev_team.mcp_facade.route_decision", return_value=fake_decision) as m:
        out = handler(RouteInput(task="rename x to y"))

    assert isinstance(out, RouteOutput)
    assert out.recommended == "direct"
    assert "Trivial" in out.rationale
    m.assert_called_once_with(task="rename x to y")


def test_route_handler_handles_missing_keys_safely():
    """If facade returns an unexpected shape, handler defaults gracefully."""
    _, handler = _register_one(route_register)
    with patch("dev_team.mcp_facade.route_decision", return_value={}):
        out = handler(RouteInput(task="x"))
    # Default fallbacks per route.py: recommended='team', rationale=''
    assert out.recommended == "team"
    assert out.rationale == ""


def test_metrics_handler_wraps_rollup():
    name, handler = _register_one(metrics_register)
    assert name == "noctus.team.metrics"

    fake_rollup = {
        "scope": "agno-dev-team-rollout",
        "total_events": 42,
        "total_cost_usd": 1.23,
        "agents": {"leader": {"events": 10, "cost_usd": 0.50}},
    }
    with patch("dev_team.mcp_facade.metrics_snapshot", return_value=fake_rollup) as m:
        out = handler(MetricsInput(scope="agno-dev-team-rollout"))

    assert isinstance(out, MetricsOutput)
    assert out.rollup == fake_rollup
    m.assert_called_once_with(scope="agno-dev-team-rollout")


def test_agent_metrics_handler_wraps_per_agent():
    name, handler = _register_one(agent_metrics_register)
    assert name == "noctus.team.agent_metrics"

    fake = {
        "agent": "leader",
        "scope": None,
        "events": 5,
        "total_cost_usd": 0.42,
        "avg_latency_ms": 2200,
        "success_rate": 0.8,
        "tool_call_distribution": {"delegate": 5},
    }
    with patch("dev_team.mcp_facade.agent_metrics", return_value=fake) as m:
        out = handler(AgentMetricsInput(name="leader"))

    assert isinstance(out, AgentMetricsOutput)
    assert out.metrics == fake
    m.assert_called_once_with(name="leader", scope=None)


def test_configure_handler_wraps_set_agent_config():
    name, handler = _register_one(configure_register)
    assert name == "noctus.team.configure"

    fake_cfg = {
        "agents": {
            "leader": {"provider": "anthropic", "model": "claude-opus-4-7"},
            "backend_engineer": {"provider": "openai", "model": "gpt-5-codex"},
        }
    }
    with patch("dev_team.mcp_facade.set_agent_config", return_value=fake_cfg) as m:
        out = handler(
            ConfigureInput(
                name="backend_engineer",
                model="gpt-5-codex",
                provider="openai",
            )
        )

    assert isinstance(out, ConfigureOutput)
    assert out.config == fake_cfg
    m.assert_called_once_with(
        name="backend_engineer",
        model="gpt-5-codex",
        provider="openai",
        config_name="default",
    )


def test_configure_handler_partial_patch_only_model():
    """Provider can be left None; named config can be overridden."""
    _, handler = _register_one(configure_register)
    fake_cfg = {"agents": {"leader": {"provider": "anthropic", "model": "claude-opus-4-7"}}}
    with patch("dev_team.mcp_facade.set_agent_config", return_value=fake_cfg) as m:
        handler(
            ConfigureInput(
                name="leader",
                model="claude-opus-4-7",
                config_name="aggressive",
            )
        )
    m.assert_called_once_with(
        name="leader", model="claude-opus-4-7", provider=None, config_name="aggressive"
    )


# ---------------------------------------------------------------------------
# Top-level umbrella wiring — verify mcp/noctusai/tools/noctus.register_all
# now invokes team.register_all alongside dev.register_all.
# ---------------------------------------------------------------------------


def test_noctus_umbrella_register_all_includes_team():
    """mcp.noctusai.tools.noctus.register_all wires both dev.* and team.*."""
    from tools.noctus import register_all as noctus_register_all

    server = _RecordingServer()
    noctus_register_all(server)
    names = {name for name, _, _ in server.registered}

    # Sanity — dev tools still register.
    assert any(n.startswith("noctus.dev.") for n in names), (
        "expected at least one noctus.dev.* registration"
    )
    # New surface — every team tool registered.
    expected_team = {
        "noctus.team.agent_metrics",
        "noctus.team.configure",
        "noctus.team.metrics",
        "noctus.team.route",
        "noctus.team.run",
        "noctus.team.status",
    }
    assert expected_team.issubset(names), (
        f"missing team tools: {expected_team - names}"
    )


if __name__ == "__main__":  # pragma: no cover — convenience runner
    sys.exit(pytest.main([__file__, "-v"]))
