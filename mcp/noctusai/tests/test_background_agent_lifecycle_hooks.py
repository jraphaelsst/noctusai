"""Detection logic of the background-agent-idle and dev-advance advisory hooks, on fixtures
(fake tasks dir + transcripts; real git repos with a local `origin/dev` ref). Both hooks must
fail OPEN and never block. KB § PATTERNS/common/background-agent-lifecycle.md."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "scripts" / "hooks"


def _load(name):
    import sys
    sys.path.insert(0, str(HOOKS))
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HOOKS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


IDLE = _load("claude-guard-background-agent-idle")
ADV = _load("claude-guard-dev-advance")
SID = "sess-1"


# ---- background-agent-idle -------------------------------------------------
def _agent(tmp, aid, finished=True, age=600):
    tasks, subs = tmp / "tasks", tmp / "subagents"
    tasks.mkdir(exist_ok=True); subs.mkdir(exist_ok=True)
    j = subs / f"agent-{aid}.jsonl"
    j.write_text("{}\n")
    t = time.time() - age
    os.utime(j, (t, t))
    meta = {"agentType": "backend-engineer", "description": "d"}
    if finished:
        meta["finished"] = True
    (subs / f"agent-{aid}.meta.json").write_text(json.dumps(meta))
    (tasks / f"{aid}.output").symlink_to(j)


def _env(monkeypatch, tmp):
    monkeypatch.setenv("NOCTUS_AGENT_TASKS_DIR", str(tmp / "tasks"))
    monkeypatch.setenv("NOCTUS_BG_AGENT_STATE", str(tmp / "st.json"))
    monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(tmp / "ev.ndjson"))
    monkeypatch.setenv("NOCTUS_DEV_ADVANCE_STATE", str(tmp / "adv.json"))


def test_idle_reports_finished_quiet_agent_only(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    _agent(tmp_path, "aaa", finished=True, age=600)     # red: idle after hand-back
    _agent(tmp_path, "bbb", finished=False, age=600)    # green: still running
    _agent(tmp_path, "ccc", finished=True, age=20)      # green: inside the grace window
    idle = IDLE.find_idle(SID, None)
    assert [c["agent_id"] for c in idle] == ["aaa"]


def test_idle_skips_agent_the_leader_already_stopped(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    _agent(tmp_path, "aaa"); _agent(tmp_path, "bbb")
    tr = tmp_path / "leader.jsonl"
    tr.write_text(json.dumps({"name": "TaskStop", "input": {"task_id": "aaa"}}) + "\n")
    assert [c["agent_id"] for c in IDLE.find_idle(SID, str(tr))] == ["bbb"]


def test_idle_skips_agent_whose_taskstop_said_no_task_found(tmp_path, monkeypatch):
    """The harness already released it: a `TaskStop` error result for the id counts as stopped."""
    _env(monkeypatch, tmp_path)
    _agent(tmp_path, "aaa"); _agent(tmp_path, "bbb")
    tr = tmp_path / "leader.jsonl"
    tr.write_text(json.dumps({"type": "user", "message": {"content": [{
        "type": "tool_result", "is_error": True,
        "content": "<tool_use_error>No task found with ID: aaa</tool_use_error>"}]}}) + "\n")
    assert [c["agent_id"] for c in IDLE.find_idle(SID, str(tr))] == ["bbb"]


def test_idle_run_reports_once_logs_telemetry_and_skips_subagents(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    _agent(tmp_path, "aaa")
    payload = {"session_id": SID, "hook_event_name": "PostToolUse"}
    assert IDLE.run({**payload, "agent_id": "x"}) is None        # inside a subagent
    out = IDLE.run(payload, now=time.time())
    assert out and "aaa" in out and "TaskStop" in out
    assert IDLE.run(payload, now=time.time() + 60) is None        # reported; reminder not due
    rows = [json.loads(l) for l in (tmp_path / "ev.ndjson").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["guard"] == "background-agent-idle" and rows[0]["agent_id"] == "aaa"


def test_idle_never_stops_or_crashes_without_tasks_dir(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    assert IDLE.run({"session_id": SID}) is None


# ---- dev-advance -----------------------------------------------------------
def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()


def _repo(tmp):
    r = tmp / "repo"; r.mkdir()
    _git(r, "init", "-q", "-b", "dev")
    _git(r, "config", "user.email", "t@t"); _git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("1")
    _git(r, "add", "."); _git(r, "commit", "-qm", "base")
    _git(r, "update-ref", "refs/remotes/origin/dev", "HEAD")
    return r


def _land(r, rel, msg="peer"):
    p = r / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(msg)
    _git(r, "add", "."); _git(r, "commit", "-qm", msg)
    _git(r, "update-ref", "refs/remotes/origin/dev", "HEAD")


def _ledger(session, paths, status="on_going"):
    return json.dumps({"branch": "feat/x", "session": session, "paths": paths, "status": status}) + "\n"


def test_advance_methodology_change_is_reported(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    r = _repo(tmp_path)
    p = {"session_id": SID, "hook_event_name": "SessionStart", "cwd": str(r)}
    assert ADV.run(p, str(r)) is None                      # baseline recorded, silent
    _land(r, ".claude/skills/noc-x/SKILL.md", "feat(skills): x")
    out = ADV.run({**p, "hook_event_name": "UserPromptSubmit"}, str(r), now=time.time() + 100)
    assert out and "METHODOLOGY" in out and ".claude/skills/noc-x/SKILL.md" in out and "feat(skills): x" in out
    assert ADV.run({**p, "hook_event_name": "UserPromptSubmit"}, str(r), now=time.time() + 200) is None  # baseline moved
    rows = [json.loads(l) for l in (tmp_path / "ev.ndjson").read_text().splitlines()]
    assert rows[0]["guard"] == "dev-advance" and rows[0]["methodology_files"] == 1


def test_advance_unrelated_change_is_silent_but_moves_baseline(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    r = _repo(tmp_path)
    p = {"session_id": SID, "cwd": str(r), "hook_event_name": "UserPromptSubmit"}
    ADV.run(p, str(r))
    _land(r, "products/other/app.py")
    assert ADV.run(p, str(r), now=time.time() + 100) is None
    assert json.loads((tmp_path / "adv.json").read_text())[SID]["sha"] == _git(r, "rev-parse", "origin/dev")
    assert not (tmp_path / "ev.ndjson").exists()


def test_pointer_overlap_logic():
    led = _ledger(SID, ["products/core/backend"]) + _ledger("other", ["zzz"]).replace("feat/x", "feat/y")
    assert ADV.own_pointer_paths(led, SID, None) == ["products/core/backend"]
    assert ADV.own_pointer_paths(_ledger(SID, ["a"], status="shipped"), SID, None) == []
    assert ADV.paths_overlap("products/core/backend/app/x.py", "products/core/backend")
    assert not ADV.paths_overlap("products/core2/x.py", "products/core")


def test_advance_overlap_with_own_pointer_reported_peer_pointer_ignored(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    r = _repo(tmp_path)
    base = _git(r, "rev-parse", "HEAD")
    _land(r, "products/core/backend/app.py")
    cur = _git(r, "rev-parse", "HEAD")
    rep = ADV.analyse(str(r), base, cur, _ledger(SID, ["products/core"]), SID, None, [])
    assert rep and rep["overlap"] == ["products/core/backend/app.py"]
    assert ADV.analyse(str(r), base, cur, _ledger("peer", ["products/core"]), SID, None, []) is None
    # own worktree diff counts even without a pointer
    assert ADV.analyse(str(r), base, cur, "", SID, None, ["products/core/backend/app.py"])


def test_advance_fails_open_on_unknown_seen_and_missing_ref(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    r = _repo(tmp_path)
    (tmp_path / "adv.json").write_text(json.dumps({SID: {"sha": "deadbeef" * 5, "last_scan": 0}}))
    assert ADV.run({"session_id": SID, "cwd": str(r)}, str(r)) is None
    assert ADV.run({"session_id": SID}, str(tmp_path / "nogit")) is None
    assert ADV.run({"session_id": SID, "agent_id": "sub"}, str(r)) is None
