"""One ordered rewrite chain for Bash PreToolUse: heavy-run wrap innermost, bg_run outermost, a deny always wins.

Two independent hooks that each return `updatedInput` run in parallel on the ORIGINAL input and one silently wins,
so a background heavy command lost one of its two wraps. `claude-guard-bash-rewrite.py` is the single hook.
KB § PATTERNS/common/background-agent-lifecycle.md (Rewrite chain).
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2].parent
HOOK = REPO / "scripts/hooks/claude-guard-bash-rewrite.py"
sys.path.insert(0, str(REPO / "mcp" / "noctusai"))
from tools.noctus.dev import bash_rewrite_chain as chain  # noqa: E402

HEAVY = "pytest mcp/noctusai/tests/test_x.py -q"


@pytest.fixture(autouse=True)
def _enforce(monkeypatch, tmp_path):
    monkeypatch.setenv("NOC_BG_LAUNCH_MODE", "enforce")
    monkeypatch.delenv("NOC_HW_UNGATED_OK", raising=False)
    monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(tmp_path / "events.ndjson"))


def _payload(cmd, bg=False, **extra):
    return {"tool_name": "Bash", "session_id": "s", "cwd": str(REPO),
            "tool_input": {"command": cmd, "run_in_background": bg, **extra}}


def _cmd(v):
    return v["updated_input"]["command"]


def test_background_heavy_is_bg_run_of_hw_admission_exactly_once():
    v = chain.decide(_payload(HEAVY, bg=True, description="run the suite"))
    c = _cmd(v)
    assert c.count("bg_run.py") == 1 and c.count("hw_admission.py") == 1
    assert c.index("bg_run.py") < c.index("hw_admission.py")  # bg_run outermost
    inner = next(a.split("=", 1)[1] for a in shlex.split(c) if a.startswith("--command="))
    assert "hw_admission.py" in inner and "bg_run.py" not in inner and HEAVY in inner
    assert [s["guard"] for s in v["steps"]] == ["heavy-run", "background-launch"]


def test_foreground_heavy_is_hw_admission_only():
    c = _cmd(chain.decide(_payload(HEAVY)))
    assert c.count("hw_admission.py") == 1 and "bg_run.py" not in c


def test_background_light_is_bg_run_only():
    c = _cmd(chain.decide(_payload("echo hi && sleep 1", bg=True)))
    assert c.count("bg_run.py") == 1 and "hw_admission.py" not in c


def test_foreground_light_is_untouched():
    assert chain.decide(_payload("git status")) is None


def test_already_wrapped_is_unchanged():
    once = _cmd(chain.decide(_payload(HEAVY, bg=True)))
    assert chain.decide(_payload(once, bg=True)) is None
    gated = _cmd(chain.decide(_payload(HEAVY)))
    assert chain.decide(_payload(gated)) is None
    # gated but not yet backgrounded: only the outer wrap is added, the inner one is not doubled
    c = _cmd(chain.decide(_payload(gated, bg=True)))
    assert c.count("bg_run.py") == 1 and c.count("hw_admission.py") == 1


def test_deny_from_either_guard_wins_over_a_rewrite():
    whisper = chain.decide(_payload("whisper audio.mp3", bg=True))
    assert "reason" in whisper and whisper["guard"] == "heavy-run" and "updated_input" not in whisper
    poll = chain.decide(_payload("pytest x.py; while true; do sleep 5; done", bg=True))
    assert "reason" in poll and "updated_input" not in poll  # heavy would rewrite, the open-ended loop denies
    assert poll["guard"] == "background-launch"


def test_infra_background_is_left_alone():
    assert chain.decide(_payload("npm run dev", bg=True)) is None


def _run_hook(payload, env_extra=None):
    env = {**os.environ, "NOC_BG_LAUNCH_MODE": "enforce", **(env_extra or {})}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True,
                          text=True, env=env, timeout=30)


def test_hook_emits_one_rewrite_and_one_event_per_guard(tmp_path):
    log = tmp_path / "ev.ndjson"
    r = _run_hook(_payload(HEAVY, bg=True), {"NOCTUS_GUARD_EVENT_LOG": str(log)})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "allow" and out["updatedInput"]["command"].count("bg_run.py") == 1
    rows = [json.loads(x) for x in log.read_text().splitlines()]
    assert sorted((x["guard"], x["outcome"]) for x in rows) == [("background-launch", "rewrite"), ("heavy-run", "rewrite")]


def test_hook_deny_is_attributed_to_the_member_guard(tmp_path):
    log = tmp_path / "ev.ndjson"
    r = _run_hook(_payload("whisper a.mp3"), {"NOCTUS_GUARD_EVENT_LOG": str(log)})
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and out["permissionDecisionReason"].startswith("[noc-guard:heavy-run]")
    rows = [json.loads(x) for x in log.read_text().splitlines()]
    assert [(x["guard"], x["outcome"]) for x in rows] == [("heavy-run", "deny")]


def test_hook_non_matching_call_is_silent():
    r = _run_hook(_payload("git status"))
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_settings_wires_exactly_one_bash_rewriting_hook():
    s = json.loads((REPO / ".claude/settings.json").read_text())
    cmds = [h["command"] for e in s["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert sum("claude-guard-bash-rewrite.py" in c for c in cmds) == 1
    assert not any("claude-guard-heavy-run.py" in c or "claude-guard-background-launch.py" in c for c in cmds)


def test_importing_the_chain_never_puts_the_toolkit_dev_dir_on_sys_path():
    """The dev dir holds a context.py; on sys.path it shadows mcp/noctusai/context.py for every later import (2026-11-16)."""
    dev = str(Path(chain.__file__).resolve().parent)
    assert dev not in sys.path
