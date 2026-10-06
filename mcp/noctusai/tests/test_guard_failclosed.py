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

    def test_engineer_seed_is_derived_as_executor(self):
        code, out = _run(EXEC, self._agent("engineer-seed"))
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
