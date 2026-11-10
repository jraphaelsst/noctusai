"""Advisor Write-scope guard (D34): pure `decide` + the real hook script (shadow warns, enforce denies, fails closed)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / "scripts" / "hooks" / "claude-guard-advisor-write.py"
_spec = importlib.util.spec_from_file_location("awg_ut", REPO_ROOT / "mcp/noctusai/tools/noctus/dev/advisor_write_guard.py")
awg = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = awg
_spec.loader.exec_module(awg)

AGENTS = REPO_ROOT / ".claude" / "agents"
ROOTS = [REPO_ROOT]


def _decide(agent, path, tool="Write"):
    return awg.decide(tool, {"file_path": path}, agent, AGENTS, ROOTS)


def test_writers_are_derived_from_agent_files():
    assert awg.advisor_writers(AGENTS) == {"product-manager", "product-architect", "product-designer"}


@pytest.mark.parametrize("agent", ["product-manager", "product-architect"])
class TestSpecWriters:
    def test_spec_and_scratchpad_allowed(self, agent):
        assert _decide(agent, f"{REPO_ROOT}/projects/x/spec/feature.md") is None
        assert _decide(agent, "projects/x/spec/notes/backlog.md") is None
        assert _decide(agent, f"{REPO_ROOT}/.claude/worktrees/w/projects/x/spec/a.md") is None
        assert _decide(agent, "/private/tmp/claude-501/s/scratchpad/spec.md") is None

    @pytest.mark.parametrize("path", [
        "products/core/backend/app/main.py", "KNOWLEDGE-BASE/CONTEXT/PATTERNS/x.md", "CLAUDE.md", ".claude/settings.json",
        "projects/x/mockups/a.html", "projects/x/spec/../../../CLAUDE.md", "/etc/hosts", "projects/x/PROJECT.md",
        "/private/tmp/other/spec.md"])
    def test_everything_else_denied(self, agent, path):
        v = _decide(agent, path)
        assert v and agent in v["reason"] and "spec/notes" in v["reason"]

    def test_edit_tools_also_judged(self, agent):
        assert _decide(agent, "products/core/x.py", tool="Edit")
        assert _decide(agent, "products/core/x.py", tool="MultiEdit")


def test_designer_keeps_mockups_not_spec():
    assert _decide("product-designer", f"{REPO_ROOT}/projects/x/mockups/home/index.html") is None
    assert _decide("product-designer", "projects/x/spec/a.md")


@pytest.mark.parametrize("agent", [None, "", "backend-engineer", "architect", "Explore", "product-analyst"])
def test_other_agents_and_main_session_never_judged(agent):
    assert _decide(agent, "products/core/x.py") is None


def test_non_write_tool_and_missing_path():
    assert awg.decide("Read", {"file_path": "x"}, "product-manager", AGENTS, ROOTS) is None
    assert awg.decide("Write", {}, "product-manager", AGENTS, ROOTS)["target"] == ""


def _run(payload, mode=None, log=None):
    env = {**os.environ, "NOCTUS_GUARD_EVENT_LOG": str(log)}
    env.pop("NOC_ADVISOR_WRITE_MODE", None)
    if mode:
        env["NOC_ADVISOR_WRITE_MODE"] = mode
    p = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, timeout=30,
                       cwd=str(REPO_ROOT), env=env)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None)


def _w(agent, path):
    return json.dumps({"tool_name": "Write", "agent_type": agent, "cwd": str(REPO_ROOT),
                       "tool_input": {"file_path": path, "content": "x"}})


def test_hook_shadow_warns_and_allows(tmp_path):
    log = tmp_path / "ev.ndjson"
    code, out = _run(_w("product-manager", "products/core/x.py"), log=log)
    assert code == 0 and out is None
    row = json.loads(log.read_text().splitlines()[-1])
    assert row["guard"] == "advisor-write" and row["outcome"] == "warn" and row["kind"] == "guard"


def test_hook_enforce_denies(tmp_path):
    code, out = _run(_w("product-architect", "products/core/x.py"), mode="enforce", log=tmp_path / "ev.ndjson")
    assert code == 0
    assert out["hookSpecificOutput"]["permissionDecisionReason"].startswith("[noc-guard:advisor-write] ")


def test_hook_allows_spec_path_silently(tmp_path):
    log = tmp_path / "ev.ndjson"
    assert _run(_w("product-manager", "projects/x/spec/a.md"), mode="enforce", log=log) == (0, None)
    assert not log.exists()


def test_hook_bad_stdin_fails_closed(tmp_path):
    code, out = _run("{nope", log=tmp_path / "ev.ndjson")
    assert code == 0 and out["hookSpecificOutput"]["permissionDecisionReason"].startswith("[noc-guard:advisor-write] ")
