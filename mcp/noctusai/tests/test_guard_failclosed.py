"""PreToolUse guard scripts fail CLOSED — real subprocess runs of the hook scripts.

Claude Code lets a tool call run when a command hook crashes or times out, so
each failure mode must produce an explicit `deny` carrying `[noc-guard:<name>]`.
The timeout/crash legs drive the shared runner through its `judge` / `deadline_s`
parameters (a documented seam, no patching); bad-stdin / crash / allow / false-
green legs run the actual scripts end to end.
"""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOKS = REPO_ROOT / "scripts" / "hooks"
PRIMARY = HOOKS / "claude-guard-primary-write.py"
SEAMS = HOOKS / "claude-guard-test-seams.py"
TEST_PATH = str(REPO_ROOT / "products" / "social-wiring" / "backend" / "tests" / "test_auth_x.py")


def _runner():
    spec = importlib.util.spec_from_file_location("noc_guard_failclosed_ut", HOOKS / "_guard_failclosed.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


runner = _runner()


def _run(script: Path, stdin: str) -> tuple[int, dict | None]:
    proc = subprocess.run(
        [sys.executable, str(script)], input=stdin, capture_output=True, text=True, timeout=30,
        cwd=str(REPO_ROOT),
    )
    out = json.loads(proc.stdout) if proc.stdout.strip() else None
    return proc.returncode, out


def _reason(out: dict) -> str:
    h = out["hookSpecificOutput"]
    assert h["permissionDecision"] == "deny"
    return h["permissionDecisionReason"]


@pytest.mark.parametrize("script,name", [(PRIMARY, "primary-write"), (SEAMS, "test-seams")])
class TestBadInputDenies:
    def test_empty_stdin(self, script, name):
        code, out = _run(script, "")
        assert code == 0
        assert _reason(out).startswith(f"[noc-guard:{name}] ")

    def test_malformed_json(self, script, name):
        code, out = _run(script, "{not json")
        assert code == 0
        assert _reason(out).startswith(f"[noc-guard:{name}] ")

    def test_non_object_payload(self, script, name):
        code, out = _run(script, "[1, 2]")
        assert code == 0
        assert "failed closed" in _reason(out)

    def test_real_internal_crash_denies(self, script, name):
        """A string `tool_input` makes the real guard raise — must deny, not wave through."""
        code, out = _run(script, json.dumps({"tool_name": "Bash", "tool_input": "oops", "cwd": str(REPO_ROOT)}))
        assert code == 0
        reason = _reason(out)
        assert reason.startswith(f"[noc-guard:{name}] ")
        assert "guard crashed" in reason and "do not bypass" in reason


@pytest.mark.parametrize("script", [PRIMARY, SEAMS])
def test_unrelated_call_still_passes(script):
    payload = {"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}, "cwd": str(REPO_ROOT)}
    code, out = _run(script, json.dumps(payload))
    assert code == 0 and out is None


class TestRunnerSeam:
    def test_judge_exception_denies_with_class_name(self):
        out = io.StringIO()

        def boom(_p):
            raise KeyError("x")

        assert runner.run_guard("g", boom, stdin=io.StringIO("{}"), stdout=out) == 0
        reason = json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecisionReason"]
        assert reason.startswith("[noc-guard:g] ") and "KeyError" in reason

    def test_deadline_denies_even_through_an_inner_except_exception(self):
        out = io.StringIO()

        def hang(_p):
            try:
                time.sleep(5)
            except Exception:  # the timeout must NOT be swallowable here
                return None

        t0 = time.monotonic()
        runner.run_guard("g", hang, stdin=io.StringIO("{}"), stdout=out, deadline_s=0.2)
        assert time.monotonic() - t0 < 3
        reason = json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecisionReason"]
        assert "timed out (failed closed)" in reason

    def test_verdict_reason_gets_marker_and_allow_is_silent(self):
        out = io.StringIO()
        runner.run_guard("g", lambda _p: {"reason": "nope"}, stdin=io.StringIO("{}"), stdout=out)
        assert json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecisionReason"] == "[noc-guard:g] nope"
        out2 = io.StringIO()
        assert runner.run_guard("g", lambda _p: None, stdin=io.StringIO("{}"), stdout=out2) == 0
        assert out2.getvalue() == ""

    def test_default_deadline_is_below_settings_timeout(self):
        settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
        timeouts = [h["timeout"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]]
        assert runner.DEFAULT_DEADLINE_S < min(timeouts)


class TestAuthFalseGreenAtWriteTime:
    def _write(self, content):
        return json.dumps({"tool_name": "Write", "cwd": str(REPO_ROOT),
                           "tool_input": {"file_path": TEST_PATH, "content": content}})

    @pytest.mark.parametrize("expr", ["(401, 404)", "{401, 422}", "[422, 401]"])
    def test_false_green_denied(self, expr):
        code, out = _run(SEAMS, self._write(f"def test_a(c):\n    assert c.get('/x').status_code in {expr}\n"))
        assert code == 0
        reason = _reason(out)
        assert reason.startswith("[noc-guard:test-seams] ") and "false-green" in reason

    def test_strict_401_and_403_pair_allowed(self):
        body = "def test_a(c):\n    assert c.get('/x').status_code == 401\n    assert c.get('/y').status_code in (401, 403)\n"
        code, out = _run(SEAMS, self._write(body))
        assert code == 0 and out is None

    def test_non_test_file_ignored(self):
        payload = {"tool_name": "Write", "cwd": str(REPO_ROOT),
                   "tool_input": {"file_path": str(REPO_ROOT / "scripts" / "x.py"),
                                  "content": "assert s in (401, 404)\n"}}
        code, out = _run(SEAMS, json.dumps(payload))
        assert code == 0 and out is None

    def test_bash_heredoc_into_test_path_denied(self):
        cmd = f"cat > {TEST_PATH} <<'EOF'\ndef test_a(c):\n    assert c.status_code in (401, 404)\nEOF\n"
        code, out = _run(SEAMS, json.dumps({"tool_name": "Bash", "cwd": str(REPO_ROOT), "tool_input": {"command": cmd}}))
        assert code == 0 and "false-green" in _reason(out)


EXEC = HOOKS / "claude-guard-executor-dispatch.py"


class TestExecutorDispatch:
    def _agent(self, subagent, prompt="do it", **extra):
        return json.dumps({"tool_name": "Agent", "cwd": str(REPO_ROOT),
                           "tool_input": {"subagent_type": subagent, "prompt": prompt, **extra}})

    def _existing_slug(self):
        roots = [REPO_ROOT]
        if REPO_ROOT.parent.name == "worktrees":
            roots.append(REPO_ROOT.parent.parent.parent)
        for r in roots:
            wt = r / ".claude" / "worktrees"
            if wt.is_dir():
                for d in sorted(wt.iterdir()):
                    if d.is_dir():
                        return d
        pytest.skip("no worktree directory on disk")

    def test_executor_without_worktree_denied(self):
        code, out = _run(EXEC, self._agent("backend-engineer"))
        assert code == 0
        r = _reason(out)
        assert r.startswith("[noc-guard:executor-dispatch] ") and "task_branch action=start" in r

    def test_product_engineer_is_derived_as_executor(self):
        code, out = _run(EXEC, self._agent("product-engineer"))
        assert "executor-dispatch" in _reason(out)

    def test_nonexistent_worktree_reference_denied(self):
        code, out = _run(EXEC, self._agent("frontend-engineer", "work in .claude/worktrees/no-such-slug-xyz"))
        assert "executor-dispatch" in _reason(out)

    def test_existing_worktree_abs_and_relative_pass(self):
        d = self._existing_slug()
        for ref in (str(d), f".claude/worktrees/{d.name}"):
            code, out = _run(EXEC, self._agent("devops-engineer", f"Worktree: {ref}"))
            assert code == 0 and out is None, ref

    def test_isolation_worktree_passes(self):
        code, out = _run(EXEC, self._agent("backend-engineer", isolation="worktree"))
        assert code == 0 and out is None

    @pytest.mark.parametrize("who", ["architect", "security", "Explore", "general-purpose"])
    def test_advisors_and_others_pass(self, who):
        code, out = _run(EXEC, self._agent(who))
        assert code == 0 and out is None

    def test_task_tool_name_also_guarded(self):
        p = json.dumps({"tool_name": "Task", "tool_input": {"subagent_type": "backend-engineer", "prompt": "x"}})
        assert "executor-dispatch" in _reason(_run(EXEC, p)[1])

    def test_bad_stdin_fails_closed(self):
        code, out = _run(EXEC, "{nope")
        assert code == 0 and _reason(out).startswith("[noc-guard:executor-dispatch] ")


# ── shared `load_module` (the one importlib idiom all six guards use) ──────────

HEAVY = HOOKS / "claude-guard-heavy-run.py"
SIGNATURE = HOOKS / "claude-guard-harness-signature.py"
POST = HOOKS / "claude-guard-primary-write-post.py"


class TestLoadModule:
    def test_loads_by_path_and_registers_in_sys_modules(self):
        mod = runner.load_module(HOOKS / "_guard_failclosed.py", "noc_load_module_ut")
        assert mod.marker("x") == "[noc-guard:x]" and sys.modules["noc_load_module_ut"] is mod

    def test_default_name_is_noc_stem(self):
        mod = runner.load_module(HOOKS / "_guard_failclosed.py")
        assert mod.__name__ == "noc_" + "_guard_failclosed"

    def test_missing_file_raises_never_returns_none(self):
        with pytest.raises((ImportError, FileNotFoundError)):
            runner.load_module(HOOKS / "no_such_guard_module.py")

    def test_load_failure_inside_judge_denies_with_marker(self):
        out = io.StringIO()
        runner.run_guard(
            "g", lambda _p: runner.load_module(HOOKS / "no_such_guard_module.py"),
            stdin=io.StringIO("{}"), stdout=out,
        )
        reason = json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecisionReason"]
        assert reason.startswith("[noc-guard:g] ") and "guard crashed" in reason


def _bash(cmd):
    return json.dumps({"tool_name": "Bash", "cwd": str(REPO_ROOT), "tool_input": {"command": cmd}})


class TestEndToEndAllowDeny:
    """One allow + one deny per guard, real subprocess, JSON on stdin."""

    def test_primary_write(self):
        code, out = _run(PRIMARY, json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}, "cwd": str(REPO_ROOT)}))
        assert code == 0 and out is None
        code, out = _run(PRIMARY, "[1]")
        assert _reason(out).startswith("[noc-guard:primary-write] ")

    def test_test_seams(self):
        code, out = _run(SEAMS, json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}, "cwd": str(REPO_ROOT)}))
        assert code == 0 and out is None
        code, out = _run(SEAMS, "")
        assert _reason(out).startswith("[noc-guard:test-seams] ")

    def test_executor_dispatch(self):
        agent = lambda s, **x: json.dumps({"tool_name": "Agent", "cwd": str(REPO_ROOT),
                                           "tool_input": {"subagent_type": s, "prompt": "x", **x}})
        code, out = _run(EXEC, agent("backend-engineer", isolation="worktree"))
        assert code == 0 and out is None
        code, out = _run(EXEC, agent("backend-engineer"))
        assert _reason(out).startswith("[noc-guard:executor-dispatch] ")

    def test_heavy_run(self):
        code, out = _run(HEAVY, _bash("ls -la"))
        assert code == 0 and out is None
        code, out = _run(HEAVY, _bash("pytest some/test_file.py"))
        assert _reason(out).startswith("[noc-guard:heavy-run] ")

    def test_harness_signature_advisory(self):
        silent = {"tool_name": "Bash", "tool_response": {"stdout": "ok", "exit_code": 0}}
        code, out = _run(SIGNATURE, json.dumps(silent))
        assert code == 0 and out is None
        hit = {"tool_name": "Bash", "tool_response": {
            "stdout": "", "stderr": "migration_replay: INCONCLUSIVE node missing", "exit_code": 1}}
        code, out = _run(SIGNATURE, json.dumps(hit))
        assert code == 0
        assert "HARNESS SIGNATURE MATCHED" in out["hookSpecificOutput"]["additionalContext"]

    def test_primary_write_post_advisory(self):
        # Never blocks: non-Bash and malformed payloads stay silent, exit 0.
        code, out = _run(POST, json.dumps({"tool_name": "Read"}))
        assert code == 0 and out is None
        code, out = _run(POST, _bash("true"))
        assert code == 0 and (out is None or "additionalContext" in out["hookSpecificOutput"])


def test_deny_and_rewrite_are_logged_one_json_line_each(tmp_path):
    # 2026-11-05: guard friction is measured from this log, not transcripts.
    mod = _runner()
    log = tmp_path / "events.ndjson"
    payload = {"tool_name": "Bash", "tool_input": {"command": "pytest"}, "session_id": "s1", "cwd": "/x"}
    mod.run_guard("heavy-run", lambda p: {"reason": "ungated"}, stdin=io.StringIO(json.dumps(payload)),
                  stdout=io.StringIO(), event_log=log)
    mod.run_guard("primary-write", lambda p: {"decision": "allow", "updated_input": {"command": "cd w && ls"},
                                              "context": "redirected"},
                  stdin=io.StringIO(json.dumps(payload)), stdout=io.StringIO(), event_log=log)
    mod.run_guard("heavy-run", lambda p: None, stdin=io.StringIO(json.dumps(payload)),
                  stdout=io.StringIO(), event_log=log)
    rows = [json.loads(x) for x in log.read_text().splitlines()]
    assert [(r["guard"], r["outcome"]) for r in rows] == [("heavy-run", "deny"), ("primary-write", "rewrite")]
    assert rows[0]["target"] == "pytest" and rows[0]["session"] == "s1"


def test_unwritable_event_log_never_changes_the_verdict(tmp_path, capsys):
    mod = _runner()
    blocker = tmp_path / "file"
    blocker.write_text("x")
    out = io.StringIO()
    mod.run_guard("heavy-run", lambda p: {"reason": "ungated"},
                  stdin=io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {}})),
                  stdout=out, event_log=blocker / "sub" / "log.ndjson")
    assert "deny" in out.getvalue()
    assert "log write failed" in capsys.readouterr().err
