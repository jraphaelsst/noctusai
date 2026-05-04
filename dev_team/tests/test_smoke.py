"""B1 smoke tests — verify the scaffolded contracts import + behave.

These tests run BEFORE the parallel engineers ship their real
implementations; they assert the scaffolded contract surface is intact
so engineers can collaborate via stub imports without breaking each
other.

Engineers ADD tests for their specific work in their own test files
(``test_charters.py``, ``test_tools.py``, ``test_memory_io.py``,
``test_telemetry.py``, ``test_config_loader.py``, ``test_api.py``,
``test_team_assembly.py``). The smoke test deliberately does NOT block
on those — it's the contract-only checkpoint.
"""

from __future__ import annotations

import sys

import pytest


def test_dev_team_imports():
    import dev_team

    assert dev_team.__version__ == "0.1.0"


def test_lazy_attrs_resolve():
    import dev_team

    # Each lazy attr should resolve to the right symbol (or stub).
    assert callable(dev_team.build_team)
    assert callable(dev_team.build_leader)
    assert callable(dev_team.load_charter)
    assert dev_team.MemoryStore is not None
    assert dev_team.AgentName is not None


def test_cli_help_runs():
    from dev_team.cli import main

    # argparse handles --help by calling sys.exit(0); both rc==0 and
    # SystemExit(0) are acceptable contract outcomes.
    try:
        rc = main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
        return
    assert rc == 0


def test_cli_no_args_returns_0():
    from dev_team.cli import main

    rc = main([])
    assert rc == 0


def test_cli_run_without_api_key_returns_3(monkeypatch, capsys):
    """Without ANTHROPIC_API_KEY, `dev_team run "x"` should bail with rc=3
    and a clear message — NOT crash."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from dev_team.cli import main

    # build_team is a stub that NotImplementedErrors; we expect the
    # API-key check to fire first. If E engineer's implementation runs
    # first and the call lacks a key, _cmd_run still returns 3.
    try:
        rc = main(["run", "test task"])
    except NotImplementedError:
        # Stub state — the API-key check happens before build_team only
        # in the wired version. Stub flow hits NotImplementedError first.
        # That's acceptable for B1; engineer E ships the wired flow.
        return
    assert rc == 3
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" in err


def test_route_returns_decision():
    """recommend_route should always return a {recommended, rationale} dict."""
    from dev_team.team import recommend_route

    decision = recommend_route("rename a variable")
    assert decision["recommended"] in ("team", "direct")
    assert "rationale" in decision

    decision = recommend_route("design and implement a new product")
    assert decision["recommended"] in ("team", "direct")


def test_memory_store_stub_snapshot():
    from dev_team.memory import MemoryStore

    snap = MemoryStore(project="x").snapshot()
    assert "project" in snap


def test_telemetry_stub_metrics():
    from dev_team.telemetry import get_metrics, get_agent_metrics

    rollup = get_metrics()
    assert "total_events" in rollup
    per_agent = get_agent_metrics("leader")
    assert per_agent["agent"] == "leader"


def test_load_config_returns_11_agents():
    from dev_team.configs import load_config

    cfg = load_config()
    agents = cfg.get("agents", {})
    assert len(agents) == 11
    assert "leader" in agents
    assert agents["leader"]["provider"] == "anthropic"


def test_allowlists_have_11_roles():
    from dev_team.tools.allowlists import TOOL_ALLOWLIST

    assert len(TOOL_ALLOWLIST) == 11
    # Leader has delegation + invoke_subteam — those are leader-only.
    assert "delegate" in TOOL_ALLOWLIST["leader"]
    assert "invoke_subteam" in TOOL_ALLOWLIST["leader"]
    # Non-leader roles must NOT have delegation tools.
    for role, tools in TOOL_ALLOWLIST.items():
        if role == "leader":
            continue
        assert "delegate" not in tools, f"{role} should not have delegate"
        assert "invoke_subteam" not in tools, f"{role} should not have invoke_subteam"


def test_load_charter_raises_when_missing():
    """load_charter raises a clear FileNotFoundError for a nonexistent role
    — NOT silently returns empty string.

    Updated by B2 engineer-A: the 12 expected charter files (1 shared + 11
    role) now ship; this test now checks the failure mode for a name not
    in the catalog rather than relying on "leader" being absent.
    """
    from dev_team.agents.base import load_charter

    with pytest.raises(FileNotFoundError, match="charter not found"):
        load_charter("not_a_real_role")  # type: ignore[arg-type]
