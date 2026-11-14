"""noctus.dev.bg_process + the shared core + the launch wrapper + the launch guard + the session-end leg.

Everything runs on FAKE `ps` text and a fake kill; no real process is ever signalled. The only real
child is a benign `echo` that exits by itself (wrapper happy path).
KB § PATTERNS/common/background-agent-lifecycle.md (Background processes)."""
from __future__ import annotations

import importlib.util
import io
import json
import signal
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
HOOKS = Path(__file__).resolve().parents[3] / "scripts" / "hooks"

from tools.noctus.dev import bg_launch_guard as guard  # noqa: E402
from tools.noctus.dev import bg_process as tool  # noqa: E402
from tools.noctus.dev import session_end_sweep as ses  # noqa: E402

core = tool.core
SID = "11111111-2222-3333-4444-555555555555"
CLAUDE = 100
T0 = "Sat Nov 14 10:00:00 2026"


class World:
    """A fake process table: `ps_text` renders it, `kill` mutates it. Nothing real is touched."""

    def __init__(self):
        self.procs: dict[int, dict] = {}
        self.signals: list[tuple[int, int]] = []
        self.stubborn: set[int] = set()  # ignore SIGTERM
        self.add(CLAUDE, 1, "claude", etime="05:00:00")

    def add(self, pid, ppid, cmd, pgid=None, etime="02:00:00", cpu="0:00.01", stat="S"):
        self.procs[pid] = dict(ppid=ppid, pgid=pgid or pid, etime=etime, cpu=cpu, stat=stat, cmd=cmd)

    def ps_text(self) -> str:
        return "\n".join(f"{pid} {p['ppid']} {p['pgid']} {p['etime']} {p['cpu']} {p['stat']} {T0} {p['cmd']}"
                         for pid, p in self.procs.items())

    def kill(self, pid, sig):
        if pid not in self.procs:
            raise ProcessLookupError
        self.signals.append((pid, sig))
        if sig == signal.SIGTERM and pid in self.stubborn:
            return
        del self.procs[pid]
        for p in self.procs.values():  # children of a dead parent are re-parented to init
            if p["ppid"] == pid:
                p["ppid"] = 1


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("NOCTUS_BG_PROCESS_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("NOCTUS_BG_CLAUDE_PID", str(CLAUDE))
    monkeypatch.setenv("NOCTUS_AGENT_TASKS_DIR", str(tmp_path / "tasks"))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SID)
    (tmp_path / "tasks").mkdir()
    return World()


def seams(w, **extra):
    return {"ps_text": w.ps_text, "kill": w.kill, "sleep": lambda _s: None, "lsof": lambda _a: "", **extra}


def call(w, **kw):
    return tool.bg_process(seams=seams(w), **kw)


def poll_loop(w, pid=200):
    """A leftover retry loop: shell child of claude + a sleep child."""
    w.add(pid, CLAUDE, "/bin/zsh -c until grep -q DONE /tmp/run.log; do sleep 30; done")
    w.add(pid + 1, pid, "sleep 30", pgid=pid)
    return pid


# ------------------------------------------------------------------ core: parsing + ownership
def test_parse_ps_reads_etime_cpu_and_identity():
    procs = core.parse_ps(f"42 7 42 02-13:26:08 134:49.25 S+ {T0} /bin/zsh -c echo hi")
    p = procs[42]
    assert p.etime_s == 2 * 86400 + 13 * 3600 + 26 * 60 + 8 and p.cpu_s == pytest.approx(134 * 60 + 49.25)
    assert p.key == f"42:{T0}" and p.command == "/bin/zsh -c echo hi"


def test_session_roots_are_this_sessions_shells_only(world):
    w = world
    w.add(200, CLAUDE, "/bin/zsh -c sleep 5")
    w.add(201, CLAUDE, "/opt/python mcp_server.py")                      # MCP server: not a shell
    w.add(300, 999, "/bin/zsh -c peer")                                   # a peer session's shell
    w.add(301, 1, f"/bin/zsh /tmp/claude-501/p/{SID}/scratchpad/x.sh")    # detached, carries OUR session id
    w.add(302, 1, "/bin/zsh /tmp/claude-501/p/other-session/scratchpad/x.sh")  # detached, someone else's
    procs = core.parse_ps(w.ps_text())
    assert [r.pid for r in core.session_roots(procs, CLAUDE, SID)] == [200, 301]


def test_find_claude_pid_walks_up_from_the_current_process(world):
    w = world
    w.add(500, CLAUDE, "/bin/zsh -c x")
    w.add(501, 500, "python mcp/noctusai/cli.py --bg-process")
    procs = core.parse_ps(w.ps_text())
    assert core.find_claude_pid(procs, start_pid=501) == CLAUDE or core.find_claude_pid(procs, 501) == CLAUDE


# ------------------------------------------------------------------ list / session-end view
def test_list_shows_leftovers_and_sets_infrastructure_and_declared_apart(world):
    w = world
    poll_loop(w)
    w.add(210, CLAUDE, "/bin/zsh -c while true; do sleep 1500; python cli.py --release-steward heartbeat; done")
    w.add(220, CLAUDE, "/bin/zsh -c npm run dev")
    w.add(230, CLAUDE, "/bin/zsh -c ./long_thing.sh")
    w.add(240, CLAUDE, "/bin/zsh -c brand_new_foreground", etime="00:05")        # too young to be a leftover
    out = call(w, action="list")
    assert out["ok"] and [p["pid"] for p in out["processes"]] == [200, 230]
    assert {p["pid"] for p in out["protected"]} == {210, 220}
    assert out["processes"][0]["waiting_on"] and out["processes"][0]["tree_size"] == 2
    d = call(w, action="declare", pid=230, purpose="local build server kept for the session", confirm=True)
    assert d["status"] == "declared" and "max_lifetime_s" not in d["entry"]       # no lease, no cap
    assert [p["pid"] for p in call(w, action="list")["processes"]] == [200]


def test_list_is_unmeasured_without_a_claude_ancestor(world, monkeypatch):
    monkeypatch.delenv("NOCTUS_BG_CLAUDE_PID")
    out = call(world, action="list")
    assert out["ok"] is False and out["status"] == "unmeasured"


# ------------------------------------------------------------------ stop: refusals
def test_stop_refuses_to_signal_without_a_salvage_record(world):
    w = world
    pid = poll_loop(w)
    out = call(w, action="stop", pid=pid, confirm=True)
    assert out["status"] == "refused_no_salvage" and w.signals == [] and pid in w.procs


def test_stop_refuses_peer_infrastructure_declared_and_own_chain(world):
    w = world
    w.add(300, 999, "/bin/zsh -c peer")
    w.add(210, CLAUDE, "/bin/zsh -c while true; do sleep 1500; python cli.py --merge-queue watch; done")
    w.add(230, CLAUDE, "/bin/zsh -c ./svc.sh")
    kw = dict(action="stop", reason="r" * 12, learnings="l" * 12, confirm=True)
    assert call(w, pid=300, **kw)["status"] == "refused_not_session_process"
    assert call(w, pid=210, **kw)["status"] == "refused_protected"
    assert call(w, pid=CLAUDE, **kw)["status"] == "refused_forbidden_pid"
    call(w, action="declare", pid=230, purpose="kept alive on purpose for the session", confirm=True)
    refused = call(w, pid=230, **kw)
    assert refused["status"] == "refused_protected" and "undeclare" in refused["error"]
    assert w.signals == []


def test_stop_dry_run_plans_and_never_signals(world):
    w = world
    pid = poll_loop(w)
    out = call(w, action="stop", pid=pid, reason="r" * 12, learnings="l" * 12)
    assert out["status"] == "planned" and w.signals == [] and not (Path(core.store_dir()) / "salvage.ndjson").exists()


# ------------------------------------------------------------------ stop: salvage first, then tree-kill, then verify
def test_stop_records_salvage_then_terms_root_first_then_children(world, tmp_path):
    w = world
    pid = poll_loop(w)
    log = tmp_path / "run.log"
    log.write_text("line1\nline2\n")
    w.procs[pid]["cmd"] = f"/bin/zsh -c until grep -q DONE {log}; do sleep 30; done"
    out = call(w, action="stop", pid=pid + 1, reason="leftover retry loop, purpose ended", learnings="use bg_run for polls", confirm=True)
    assert out["ok"] and out["status"] == "stopped" and out["survivors"] == [] and out["orphans_remaining"] == []
    assert [s for _, s in w.signals][:2] == [signal.SIGTERM, signal.SIGTERM]
    assert w.signals[0][0] == pid                                    # root first: a `while true` shell cannot respawn
    tail = Path(out["salvage"]["tail_path"]).read_text()
    assert "line2" in tail and "use bg_run for polls" in tail         # tail saved outside git
    rows = core.salvage_rows(core.store_dir())
    assert rows[0]["reason"] and rows[0]["learnings"] and rows[-1]["kind"] == "stop"


def test_stop_escalates_to_kill_and_reports_orphans(world):
    w = world
    pid = poll_loop(w)
    w.stubborn = {pid, pid + 1}
    out = call(w, action="stop", pid=pid, reason="r" * 12, learnings="l" * 12, confirm=True)
    assert out["escalated_to_kill"] and out["status"] == "stopped"
    assert {s for _, s in w.signals} == {signal.SIGTERM, signal.SIGKILL}


def test_stop_reports_survivors_when_kill_cannot_land(world):
    w = world
    pid = poll_loop(w)
    w.kill_real = w.kill

    def kill(p, s):  # a process nothing can end
        w.signals.append((p, s))

    out = tool.bg_process(action="stop", pid=pid, reason="r" * 12, learnings="l" * 12, confirm=True,
                          seams={**seams(w), "kill": kill})
    assert out["ok"] is False and out["status"] == "survivors_remain" and out["survivors"]


def test_orphaned_child_of_a_killed_parent_is_still_found_and_stopped(world):
    w = world
    pid = poll_loop(w)
    w.stubborn = {pid + 1}  # the child outlives its parent's TERM and is re-parented to init
    out = call(w, action="stop", pid=pid, reason="r" * 12, learnings="l" * 12, confirm=True)
    assert out["status"] == "stopped" and (pid + 1, signal.SIGKILL) in w.signals


def test_a_prior_salvage_action_lets_stop_proceed_without_reason(world):
    w = world
    pid = poll_loop(w)
    s = call(w, action="salvage", pid=pid, reason="r" * 12, learnings="l" * 12, confirm=True)
    assert s["status"] == "salvaged"
    assert call(w, action="stop", pid=pid, confirm=True)["status"] == "stopped"


# ------------------------------------------------------------------ session-end leg
def test_session_report_is_never_green_when_unmeasured(world, monkeypatch):
    w = world
    assert tool.session_report(seams={"ps_text": w.ps_text, "lsof": lambda _a: ""})["clean_wrap"] is True
    poll_loop(w)
    rep = tool.session_report(seams={"ps_text": w.ps_text, "lsof": lambda _a: ""})
    assert rep["clean_wrap"] is False and rep["count"] == 1
    monkeypatch.delenv("NOCTUS_BG_CLAUDE_PID")
    assert tool.session_report(seams={"ps_text": w.ps_text})["clean_wrap"] is None


def test_sweep_blocks_a_clean_wrap_on_leftover_processes(tmp_path):
    leftover = lambda: {"status": "ok", "clean_wrap": False, "count": 1, "processes": [{"pid": 7}]}  # noqa: E731
    out = ses.sweep(repo_root=Path("/nonexistent-repo-xyz"), deliver_ledgers=False, heal_pointers=False, bg_report=leftover)
    assert out["clean_wrap"] is False and out["wrap_blockers"] == ["background_processes"]
    clean = ses.sweep(repo_root=Path("/nonexistent-repo-xyz"), deliver_ledgers=False, heal_pointers=False,
                      bg_report=lambda: {"status": "ok", "clean_wrap": True, "processes": []})
    assert clean["clean_wrap"] is True and clean["wrap_blockers"] == []
    unk = ses.sweep(repo_root=Path("/nonexistent-repo-xyz"), deliver_ledgers=False, heal_pointers=False,
                    bg_report=lambda: {"status": "unmeasured", "clean_wrap": None, "processes": []})
    assert unk["clean_wrap"] is None and unk["wrap_blockers"] == []


# ------------------------------------------------------------------ launch wrapper
def test_validate_launch_refuses_open_ended_shapes():
    v = core.validate_launch
    assert v(purpose="", done="x", command="ls", done_when=None, long_lived=False)
    assert v(purpose="wait for ci", done="", command="gh run watch 1", done_when=None, long_lived=False)
    assert v(purpose="wait for ci", done="run ends", command=None, done_when=None, long_lived=False)
    assert v(purpose="poll file", done="DONE shows", command="while true; do sleep 5; done", done_when=None, long_lived=False)
    assert v(purpose="poll file", done="DONE shows", command="while true; do sleep 5; done", done_when="grep -q DONE f", long_lived=False) is None
    assert v(purpose="wait for ci", done="run ends", command="gh run watch 1", done_when=None, long_lived=False) is None
    assert v(purpose="dev server for session", done="", command="npm run dev", done_when=None, long_lived=True) is None


def test_wrapper_runs_a_command_salvages_its_own_output_and_ends(world, tmp_path):
    out = io.StringIO()
    rc = core.run_wrapped(purpose="say hello once", done="the command exits", command="echo hello-from-wrapper",
                          interval_s=0.05, out=out)
    assert rc == 0 and "hello-from-wrapper" in out.getvalue()
    rec = core.salvage_rows(core.store_dir())[-1]
    assert rec["by"] == "bg_run" and "command exited rc=0" in rec["reason"]
    assert "hello-from-wrapper" in Path(rec["tail_path"]).read_text()


def test_wrapper_done_when_ends_a_running_child_and_tree_stops_its_group(world):
    w = world

    class Child:
        pid = 4242
        returncode = None
        stdout = io.BytesIO(b"")

        def poll(self):
            return None

    w.add(4242, 1, "tail -f run.log", pgid=4242)       # the child's group: the orphan net must stop it
    w.add(4243, 4242, "grep x", pgid=4242)
    rc = core.run_wrapped(purpose="watch the run log", done="DONE shows", command="tail -f run.log", done_when="true",
                          interval_s=0.01, out=io.StringIO(), ps_text=w.ps_text, kill=w.kill, popen=lambda *a, **k: Child())
    assert rc == 0
    assert 4242 not in w.procs and 4243 not in w.procs
    assert "done-when" in core.salvage_rows(core.store_dir())[-1]["reason"]


def test_wrapper_refuses_a_bare_loop_without_a_done_condition(world, capsys):
    rc = core.run_wrapped(purpose="poll the file", done="DONE shows", command="until grep -q DONE f; do sleep 5; done")
    assert rc == 2 and "done-when" in capsys.readouterr().err


# ------------------------------------------------------------------ launch guard
def _bash(cmd, bg=True, **extra):
    return {"tool_name": "Bash", "tool_input": {"command": cmd, "run_in_background": bg, **extra}}


@pytest.mark.parametrize("cmd", [
    "while true; do sleep 60; done",
    "tail -f /tmp/x.log",
    "watch -n 5 ls",
    "vitest --watch",
    "until curl -s localhost:1; do sleep 2; done",
    "until grep -q DONE /tmp/run.log; do sleep 30; done",                                # a poll, background or not
    "/bin/zsh -c 'until grep -q DONE f.log; do sleep 5; done'",
    "timeout 590 bash -c 'until [ -s /tmp/tasks/x.output ]; do sleep 10; done'",         # `timeout` does not make a poll acceptable
    "until [ -s $F ]; do sleep 10; done; tail $F",
    "/bin/zsh -c 'while true; do sleep 5; done'",
    'python3 scripts/bg_run.py --done "x" -- echo hi',                                   # no purpose
    'python3 scripts/bg_run.py --purpose "p p p" -- echo hi',                            # no done
    'python3 scripts/bg_run.py --purpose "p p p" --done "d d d" -- \'while true; do work; sleep 1; done\'',  # loop, no done-when
])
def test_guard_denies_open_ended_background_launches(cmd):
    verdict = guard.decide(_bash(cmd))
    assert verdict and "reason" in verdict and "bg_run.py" in verdict["reason"]


@pytest.mark.parametrize("cmd", [
    "sleep 600 && echo done",
    "gh run watch 123",
    "pytest mcp/noctusai/tests/",
    "npm run build",
    "python3 hw_admission.py run --job x -- pytest",
    "git push origin feat/x",
    "ls -la",
])
def test_guard_rewrites_every_other_background_launch_into_the_wrapper(cmd):
    verdict = guard.decide(_bash(cmd, description="run the thing for the owner"))
    ti = verdict["updated_input"]
    assert verdict["decision"] == "allow" and ti["run_in_background"] is True and ti["description"] == "run the thing for the owner"
    assert "bg_run.py" in ti["command"] and "--purpose 'run the thing for the owner'" in ti["command"]
    assert "--done 'the command exits'" in ti["command"]
    assert guard.decide({"tool_name": "Bash", "tool_input": ti}) is None            # idempotent: the rewrite is itself allowed


def test_the_rewritten_command_runs_the_original_and_ends_with_it(world, tmp_path):
    v = guard.decide(_bash("echo ran-by-the-wrapper"))
    import subprocess
    r = subprocess.run(["/bin/sh", "-c", v["updated_input"]["command"]], capture_output=True, text=True, timeout=30,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "NOCTUS_BG_PROCESS_DIR": str(tmp_path / "s2")})
    assert r.returncode == 0 and "ran-by-the-wrapper" in r.stdout and "command exited rc=0" in r.stderr


def test_infrastructure_is_left_untouched_not_rewritten():
    assert guard.decide(_bash("python cli.py --merge-queue watch")) is None
    assert guard.decide(_bash("npm run dev")) is None


@pytest.mark.parametrize("cmd", [
    'python3 scripts/bg_run.py --purpose "wait for ci" --done "run ends" -- gh run watch 123',
    'python3 scripts/bg_run.py --purpose "poll file" --done "DONE" --done-when "grep -q DONE f" -- tail -f f',
    'python3 scripts/bg_run.py --purpose "dev server" --long-lived -- npm run dev',
    "while true; do sleep 1500; .venv/bin/python cli.py --release-steward heartbeat >/dev/null 2>&1; done",
])
def test_guard_allows_wrapped_and_infrastructure_launches_unchanged(cmd):
    assert guard.decide(_bash(cmd)) is None


def test_guard_only_judges_bash():
    assert guard.decide({"tool_name": "Edit", "tool_input": {"command": "while true"}}) is None


def _load_hook():
    sys.path.insert(0, str(HOOKS))
    spec = importlib.util.spec_from_file_location("bg_launch_hook", HOOKS / "claude-guard-background-launch.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    return hook


def test_mode_is_shadow_before_enforce_date_and_enforce_from_it(monkeypatch):
    import datetime as dt
    monkeypatch.delenv("NOC_BG_LAUNCH_MODE", raising=False)
    start = dt.date.fromisoformat(guard.ENFORCE_FROM)
    assert guard.mode(start - dt.timedelta(days=1)) == "shadow"
    assert guard.mode(start) == "enforce"
    monkeypatch.setenv("NOC_BG_LAUNCH_MODE", "shadow")
    assert guard.mode(start) == "shadow"


def test_hook_in_shadow_allows_and_logs_a_warn_event(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NOC_BG_LAUNCH_MODE", "shadow")
    events = tmp_path / "ev.ndjson"
    monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(events))
    hook = _load_hook()
    from _guard_failclosed import run_guard
    out = io.StringIO()
    run_guard("background-launch", hook._judge, stdin=io.StringIO(json.dumps(_bash("while true; do sleep 9; done"))),
              stdout=out, event_log=events)
    assert out.getvalue() == ""  # no deny emitted: the launch proceeds
    rows = [json.loads(line) for line in events.read_text().splitlines()]
    assert [r["outcome"] for r in rows] == ["warn"] and rows[0]["source"] == "shadow"
    assert "[noc-guard:background-launch] WARNING" in capsys.readouterr().err


def test_hook_denies_through_the_fail_closed_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("NOC_BG_LAUNCH_MODE", "enforce")
    sys.path.insert(0, str(HOOKS))
    spec = importlib.util.spec_from_file_location("bg_launch_hook", HOOKS / "claude-guard-background-launch.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    from _guard_failclosed import run_guard
    out = io.StringIO()
    run_guard("background-launch", hook._judge, stdin=io.StringIO(json.dumps(_bash("while true; do sleep 9; done"))),
              stdout=out, event_log=tmp_path / "ev.ndjson")
    body = json.loads(out.getvalue())["hookSpecificOutput"]
    assert body["permissionDecision"] == "deny" and body["permissionDecisionReason"].startswith("[noc-guard:background-launch]")


# ------------------------------------------------------------------ MCP wiring
def test_registered_under_the_dev_namespace():
    seen = {}

    class _Server:
        def tool(self, *, name, description):
            seen["name"], seen["description"] = name, description
            return lambda fn: fn

    tool.register(_Server())
    assert seen["name"] == "noctus.dev.bg_process" and "No lifetime cap" in seen["description"]


def test_no_lifetime_or_idle_parameters_exist_anywhere():
    import inspect
    params = set(inspect.signature(tool.bg_process).parameters)
    assert not {"max_lifetime_s", "min_idle_s", "heartbeat"} & params
    assert not hasattr(core, "IDLE_S")


def test_hook_fast_path_skips_non_background_bash_without_loading(monkeypatch, capsys):
    hook = _load_hook()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_bash("git status", bg=False))))
    assert hook.main() == 0
    assert capsys.readouterr().out == ""


def test_shadow_timeout_is_allowed_not_denied(monkeypatch):
    hook = _load_hook()
    monkeypatch.setenv("NOC_BG_LAUNCH_MODE", "shadow")
    assert hook._shadow_timeout_ok({}) is True
    monkeypatch.setenv("NOC_BG_LAUNCH_MODE", "enforce")
    assert hook._shadow_timeout_ok({}) is False


# ------------------------------------------------------------------ foreground escape + enforce-now + producer-dead
@pytest.mark.parametrize("cmd", [
    "until grep -q 'HW-RUN DONE' /tmp/run.log; do sleep 5; done; tail /tmp/run.log",
    "while true; do sleep 60; done",
    "tail -f /tmp/x.log",
    "vitest --watch",
    "timeout 590 bash -c 'until [ -s /tmp/tasks/x.output ]; do sleep 10; done'",
    "gtimeout 60 bash -c 'while ! pgrep -f foo; do sleep 1; done'",
    "until [ -s $F ]; do sleep 10; done",
])
def test_foreground_open_ended_loop_is_denied_and_teaches_the_right_shape(cmd):
    v = guard.decide(_bash(cmd, bg=False))
    assert v and "run_in_background" in v["reason"] and "never in a loop" in v["reason"] and "notification resumes you" in v["reason"]


@pytest.mark.parametrize("cmd", [
    "timeout 300 tail -f /tmp/x.log",
    "gtimeout 60 bash -c 'for f in a b; do sleep 1; done'",
    "for f in a b c; do echo $f; sleep 1; done",
    'python3 scripts/bg_run.py --purpose "poll f" --done "DONE" --done-when "grep -q DONE f" -- tail -f f',
    "sleep 20",                                    # finite, not a loop
    "pytest -q tests/test_x.py",                   # long but finite
    "git commit -m 'wait until the queue lands'",  # prose, not a loop
    "ls -la",
])
def test_foreground_bounded_or_non_loop_commands_are_allowed(cmd):
    assert guard.decide(_bash(cmd, bg=False)) is None


def test_enforcement_is_in_effect_today_and_the_decision_is_recorded(monkeypatch):
    import datetime as dt
    monkeypatch.delenv("NOC_BG_LAUNCH_MODE", raising=False)
    assert guard.ENFORCE_FROM <= "2026-11-14" and guard.mode(dt.date(2026, 11, 14)) == "enforce"
    assert "2026-11-14" in (guard.__doc__ or "") + Path(guard.__file__).read_text()


def test_hook_fast_path_lets_a_non_loop_foreground_call_through_without_loading(monkeypatch, capsys):
    hook = _load_hook()
    monkeypatch.setattr(hook, "load_module", lambda *_a: pytest.fail("module loaded on the fast path"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_bash("git status", bg=False))))
    assert hook.main() == 0 and capsys.readouterr().out == ""


def test_hook_denies_a_foreground_loop_and_logs_the_deny(tmp_path, monkeypatch):
    monkeypatch.delenv("NOC_BG_LAUNCH_MODE", raising=False)
    hook = _load_hook()
    from _guard_failclosed import run_guard
    out, events = io.StringIO(), tmp_path / "ev.ndjson"
    run_guard("background-launch", hook._judge, stdin=io.StringIO(json.dumps(_bash("until false; do sleep 5; done", bg=False))),
              stdout=out, event_log=events)
    assert json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert [json.loads(line)["outcome"] for line in events.read_text().splitlines()] == ["deny"]


class _Lsof:
    """Fake lsof: `writers` = {path: [pids]} reported as open-for-write."""
    def __init__(self, writers=None):
        self.writers = writers or {}

    def __call__(self, args):
        path = args[-1]
        return "".join(f"p{pid}\nfw\naw\n" for pid in self.writers.get(path, []))


def test_producer_watch_ends_a_wait_whose_declared_producer_is_dead(tmp_path):
    f = tmp_path / "run.log"
    f.write_text("partial\n")
    w = core.ProducerWatch(started_at=0.0, declared_pid=777, lsof=_Lsof(), alive=lambda _p: False, confirm_checks=2)
    assert w.check([f]) is None            # debounce: first observation
    assert "producer gone" in w.check([f]) and "777" in w.check([f])


def test_producer_watch_never_fires_while_anything_can_still_write(tmp_path):
    f = tmp_path / "run.log"
    f.write_text("x")
    alive = _Lsof({str(f): [55]})
    w = core.ProducerWatch(started_at=0.0, lsof=alive, alive=lambda _p: True, confirm_checks=1)
    assert w.check([f]) is None            # a live writer holds it
    w2 = core.ProducerWatch(started_at=0.0, declared_pid=9, lsof=_Lsof(), alive=lambda p: p == 9, confirm_checks=1)
    assert w2.check([f]) is None           # declared producer alive
    w3 = core.ProducerWatch(started_at=0.0, lsof=_Lsof(), confirm_checks=1, mtime=lambda _p: None)
    assert w3.check([tmp_path / "missing.log"]) is None   # a file not yet created may still appear


def test_producer_watch_resets_when_the_file_changes(tmp_path):
    f = tmp_path / "run.log"
    f.write_text("x")
    box = {"m": 100.0}
    w = core.ProducerWatch(started_at=0.0, declared_pid=1, lsof=_Lsof(), alive=lambda _p: False,
                           confirm_checks=2, mtime=lambda _p: box["m"])
    assert w.check([f]) is None
    box["m"] = 200.0                       # written to after the producer was seen dead
    assert w.check([f]) is None and w.streak == 0


def test_wrapped_wait_on_a_dead_producers_file_ends_with_salvage(world, tmp_path):
    f = tmp_path / "run.log"
    f.write_text("never says the magic word\n")
    rc = core.run_wrapped(purpose="wait for HW-RUN DONE", done="the log says DONE", done_when=f"grep -q 'HW-RUN DONE' {f}",
                          interval_s=0.01, out=io.StringIO(), ps_text=world.ps_text, kill=world.kill,
                          producer_pid=424242, alive=lambda _p: False, lsof=_Lsof(), confirm_checks=2)
    assert rc == 4
    rec = core.salvage_rows(core.store_dir())[-1]
    assert "can never fire" in rec["reason"] and "producer gone" in rec["reason"] and rec["by"] == "bg_run"


def test_listing_flags_a_poll_loop_whose_target_has_no_writer_and_did_not_change(world, tmp_path):
    f = tmp_path / "run.log"
    f.write_text("finished long ago\n")
    import os
    os.utime(f, (1.0e9, 1.0e9))
    world.add(300, CLAUDE, f"/bin/zsh -c until grep -q DONE {f}; do sleep 5; done")
    world.add(301, 300, "sleep 5", pgid=300)
    row = call(world, action="list")["processes"][0]
    assert row["producer_dead"].startswith("producer gone") and any("CAN NEVER FIRE" in n for n in row["waiting_on"])


# ------------------------------------------------------------------ runtime-end legs (owner 2026-11-14): structure, scripts, rewrite, parent-death
def _scripted(tmp_path, name, body, mode=0o755):
    (tmp_path / ".git").mkdir(exist_ok=True)       # a repo root: the only place (besides the scratchpad) scripts are opened
    f = tmp_path / name
    f.write_text(body)
    f.chmod(mode)
    return f


POLL_SH = "#!/bin/sh\nuntil grep -q DONE run.log; do sleep 5; done\n"
POLL_PY = "import time\nwhile True:\n    time.sleep(5)\n"


@pytest.mark.parametrize("cmd", ["./poll.sh", "bash poll.sh", "sh ./poll.sh", "python3 poll.py", "cd . && ./poll.sh"])
@pytest.mark.parametrize("bg", [True, False])
def test_a_loop_inside_an_invoked_script_is_judged_foreground_and_background(tmp_path, cmd, bg):
    _scripted(tmp_path, "poll.sh", POLL_SH)
    _scripted(tmp_path, "poll.py", POLL_PY, 0o644)
    v = guard.decide({**_bash(cmd, bg=bg), "cwd": str(tmp_path)})
    assert v and "reason" in v and "poll." in v["reason"] and "script" in v["reason"]


def test_a_script_without_an_endless_loop_is_not_judged(tmp_path):
    _scripted(tmp_path, "ok.sh", "#!/bin/sh\nwhile read l; do echo $l; done < in.txt\nfor i in 1 2; do sleep 1; done\n")
    _scripted(tmp_path, "ok.py", "import time\nwhile True:\n    time.sleep(1)\n    if done():\n        break\n", 0o644)
    assert guard.decide({**_bash("./ok.sh", bg=False), "cwd": str(tmp_path)}) is None
    assert guard.decide({**_bash("python ok.py", bg=False), "cwd": str(tmp_path)}) is None
    assert "updated_input" in guard.decide({**_bash("./ok.sh"), "cwd": str(tmp_path)})  # background: wrapped, not refused


def test_script_reading_is_bounded_to_the_repo_and_scratchpad_and_to_size(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    _scripted(outside, "poll.sh", POLL_SH)
    (outside / ".git").rmdir()
    assert guard.decide({**_bash(f"{outside}/poll.sh", bg=False), "cwd": str(tmp_path / "elsewhere")}) is None  # not a root: not read
    big = _scripted(tmp_path, "big.sh", POLL_SH + "# " + "x" * (core.shell.MAX_SCRIPT_BYTES + 10) + "\n")
    assert guard.decide({**_bash("./big.sh", bg=False), "cwd": str(tmp_path)}) is None                         # too large: not read


def test_a_non_poll_script_loop_bounded_by_timeout_or_the_wrapper_is_allowed_but_a_poll_script_never_is(tmp_path):
    _scripted(tmp_path, "work.sh", "#!/bin/sh\nwhile true; do ./step; sleep 5; done\n")
    _scripted(tmp_path, "poll.sh", POLL_SH)
    ctx = {"cwd": str(tmp_path)}
    assert guard.decide({**_bash("timeout 120 ./work.sh", bg=False), **ctx}) is None
    assert guard.decide({**_bash("./work.sh", bg=False), **ctx})                      # unbounded: refused
    assert guard.decide({**_bash('python3 scripts/bg_run.py --purpose "run work" --done "DONE" --done-when "test -f ok" -- ./work.sh'), **ctx}) is None
    assert guard.decide({**_bash("timeout 120 ./poll.sh", bg=False), **ctx})          # a poll: `timeout` does not help


def test_a_poll_is_denied_bounded_or_not_foreground_or_background_and_a_bounded_non_poll_loop_passes():
    sh = core.shell
    for poll in ("until [ -s /t/x.output ]; do sleep 10; done", "while ! pgrep -f foo; do sleep 1; done",
                 "timeout 590 bash -c 'until [ -s /t/x.output ]; do sleep 10; done'"):
        assert [f.kind for f in sh.open_ended(poll)] == ["poll"]
        for bg in (False, True):
            v = guard.decide(_bash(poll, bg=bg))
            assert v and "never in a loop" in v["reason"] and "notification resumes you" in v["reason"]
    for ok in ("for f in a b c; do echo $f; sleep 1; done", "timeout 30 bash -c 'for f in 1 2; do sleep 1; done'"):
        assert not sh.open_ended(ok) and guard.decide(_bash(ok, bg=False)) is None


def test_shell_structure_not_text_decides_what_is_a_loop():
    sh = core.shell
    assert not sh.open_ended("git commit -m 'wait; until x; do y; done'")                          # quoted prose
    assert not sh.open_ended("cat > /tmp/p.sh <<'EOF'\nuntil false; do sleep 1; done\nEOF\nchmod +x /tmp/p.sh")
    assert not sh.open_ended("git commit -m \"$(cat <<'EOF'\nuntil x; do y; done (z)\nEOF\n)\"")
    assert not sh.open_ended("echo wait until the queue lands")
    assert not sh.open_ended("while read l; do echo $l; done < f")
    assert not sh.open_ended("while true; do sleep 1")                                                # never closed: not a loop
    assert sh.open_ended("bash -c 'until false; do sleep 1; done'")                                  # quoted, but EXECUTED
    assert sh.open_ended("bash <<EOF\nwhile true; do sleep 1; done\nEOF")   # heredoc fed to a shell
    assert sh.open_ended("echo $(while true; do sleep 1; done)")
    assert sh.open_ended("eval 'tail -f x'")
    assert sh.open_ended("timeout 30 bash -c 'until false; do sleep 1; done'")                      # a poll, even bounded
    assert not sh.open_ended("timeout 30 bash -c 'while true; do work; sleep 1; done'")            # bounded, not a poll
    assert not sh.open_ended("nohup timeout -s KILL 30 tail -f x")


def test_the_session_end_sweep_stop_is_logged_as_an_escape_from_runtime_end(world, tmp_path, monkeypatch):
    events = tmp_path / "ev.ndjson"
    monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(events))
    pid = poll_loop(world)
    out = call(world, action="stop", pid=pid + 1, reason="leftover found by the sweep", learnings="should have been wrapped", confirm=True)
    assert out["ok"]
    rows = [json.loads(line) for line in events.read_text().splitlines()]
    assert [r["outcome"] for r in rows if r["outcome"] == "escaped-runtime-end"] == ["escaped-runtime-end"]
    assert rows[0]["guard"] == "background-process" and rows[0]["pid"] == pid


class _Hung:
    """A child that never exits by itself (the thing a wrapper must not outlive its owner for)."""
    pid = 4242
    returncode = None
    stdout = io.BytesIO(b"")

    def poll(self):
        return None


def _wrap_hung(world, **kw):
    world.add(4242, 1, "sleep 9999", pgid=4242)
    return core.run_wrapped(purpose="a long wait for nothing", done="never", command="sleep 9999", interval_s=0.01,
                            out=io.StringIO(), ps_text=world.ps_text, kill=world.kill, popen=lambda *a, **k: _Hung(),
                            owner_check_s=0.0, **kw)


def test_wrapper_ends_its_tree_when_the_owning_session_process_is_gone(world):
    ticks = {"n": 0}
    real_ps = world.ps_text

    def ps_then_claude_dies():
        ticks["n"] += 1
        if ticks["n"] > 3:
            world.procs.pop(CLAUDE, None)       # the session was closed
        return real_ps()
    world.ps_text = ps_then_claude_dies
    assert _wrap_hung(world) == 5
    assert "owning session ended" in core.salvage_rows(core.store_dir())[-1]["reason"] and 4242 not in world.procs


def test_wrapper_ends_when_re_parented_to_init_but_not_when_it_started_detached(world):
    seq = iter([777] + [1] * 50)
    assert _wrap_hung(world, getppid=lambda: next(seq)) == 5
    assert "re-parented" in core.salvage_rows(core.store_dir())[-1]["reason"]
    world2_ticks = {"n": 0}

    class _Child(_Hung):
        def poll(self):
            world2_ticks["n"] += 1
            return 0 if world2_ticks["n"] > 30 else None
        returncode = 0
    world.add(4243, 1, "sleep 1", pgid=4243)
    rc = core.run_wrapped(purpose="detached on purpose", done="exits", command="sleep 1", interval_s=0.01, out=io.StringIO(),
                          ps_text=world.ps_text, kill=world.kill, popen=lambda *a, **k: _Child(), owner_check_s=0.0,
                          getppid=lambda: 1)
    assert rc == 0                                                    # started with ppid 1: only the owner pid decides


def test_hook_rewrites_through_the_fail_closed_runner_and_shadow_does_not(tmp_path, monkeypatch):
    from _guard_failclosed import run_guard
    hook = _load_hook()
    monkeypatch.setenv("NOC_BG_LAUNCH_MODE", "enforce")
    out = io.StringIO()
    run_guard("background-launch", hook._judge, stdin=io.StringIO(json.dumps(_bash("pytest -q tests/x.py"))), stdout=out,
              event_log=tmp_path / "ev.ndjson")
    body = json.loads(out.getvalue())["hookSpecificOutput"]
    assert body["permissionDecision"] == "allow" and "bg_run.py" in body["updatedInput"]["command"]
    monkeypatch.setenv("NOC_BG_LAUNCH_MODE", "shadow")
    out2 = io.StringIO()
    run_guard("background-launch", hook._judge, stdin=io.StringIO(json.dumps(_bash("pytest -q tests/x.py"))), stdout=out2,
              event_log=tmp_path / "ev2.ndjson")
    assert out2.getvalue() == ""
