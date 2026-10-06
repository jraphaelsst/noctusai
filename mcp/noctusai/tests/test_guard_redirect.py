"""Primary-write REDIRECT + the two false-positive fixes — real subprocess runs of the hook.

Owner-approved 2026-10-06 (KB § PATTERNS/common/self-branching-mode.md §11):
a refused Edit/Write whose session CLAIMED a worktree is rewritten into it
(visible `REDIRECTED` note), never for Bash, never into a shared branch, never
on a stale/malformed claim. Plus: `W=<abs>; cd $W` is resolved, and the
post-hook never reports a pre-existing path as new dirt.

Each test builds a throwaway repo (primary on `dev` + a linked worktree) and
pipes a real hook payload through the real script — no patching of the guard.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / "scripts" / "hooks" / "claude-guard-primary-write.py"
GUARD_PATH = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "primary_write_guard.py"


def _guard():
    spec = importlib.util.spec_from_file_location("noc_pwg_redirect_ut", GUARD_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


pwg = _guard()


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def layout(tmp_path: Path) -> tuple[Path, Path]:
    primary = tmp_path / "repo"
    primary.mkdir()
    _git("init", "-q", "-b", "dev", cwd=primary)
    _git("config", "user.email", "t@example.com", cwd=primary)
    _git("config", "user.name", "t", cwd=primary)
    (primary / "app.py").write_text("x = 1\n")
    (primary / ".gitignore").write_text(".claude/cache/\n.claude/worktrees/\n")
    _git("add", ".", cwd=primary)
    _git("commit", "-q", "-m", "init", cwd=primary)
    wt = primary / ".claude" / "worktrees" / "feat-x"
    _git("worktree", "add", "-q", "-b", "feat/x", str(wt), cwd=primary)
    return primary.resolve(), wt.resolve()


def _hook(payload: dict) -> dict | None:
    proc = subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, timeout=30,
        env={k: v for k, v in os.environ.items() if k != "NOCTUS_ALLOW_PRIMARY_WRITE"},
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["hookSpecificOutput"] if proc.stdout.strip() else None


def _write(primary: Path, session: str = "s1", rel: str = "app.py", tool: str = "Write") -> dict:
    return {
        "hook_event_name": "PreToolUse", "tool_name": tool, "session_id": session,
        "tool_input": {"file_path": str(primary / rel), "content": "x = 2\n"},
        "cwd": str(primary), "transcript_path": "/dev/null", "tool_use_id": "t",
    }


class TestRedirect:
    def test_claimed_session_is_redirected_visibly(self, layout):
        primary, wt = layout
        assert pwg.write_claim(str(primary), "s1", str(wt))["status"] == "claimed"
        out = _hook(_write(primary))
        assert out["permissionDecision"] == "allow"
        assert out["updatedInput"]["file_path"] == str(wt / "app.py")
        assert out["updatedInput"]["content"] == "x = 2\n"
        assert out["additionalContext"].startswith("[noc-guard:primary-write] REDIRECTED ")

    def test_edit_is_redirected_too(self, layout):
        primary, wt = layout
        pwg.write_claim(str(primary), "s1", str(wt))
        payload = _write(primary, tool="Edit")
        payload["tool_input"] = {"file_path": str(primary / "app.py"), "old_string": "1", "new_string": "2"}
        out = _hook(payload)
        assert out["permissionDecision"] == "allow"
        assert out["updatedInput"] == {"file_path": str(wt / "app.py"), "old_string": "1", "new_string": "2"}

    def test_no_claim_still_refuses(self, layout):
        primary, _ = layout
        out = _hook(_write(primary))
        assert out["permissionDecision"] == "deny"

    def test_another_sessions_claim_does_not_apply(self, layout):
        primary, wt = layout
        pwg.write_claim(str(primary), "other", str(wt))
        assert _hook(_write(primary, session="s1"))["permissionDecision"] == "deny"

    def test_bash_is_never_redirected(self, layout):
        primary, wt = layout
        pwg.write_claim(str(primary), "s1", str(wt))
        payload = _write(primary)
        payload["tool_name"] = "Bash"
        payload["tool_input"] = {"command": f"echo x > {primary / 'app.py'}"}
        assert _hook(payload)["permissionDecision"] == "deny"

    def test_claim_on_shared_branch_is_refused_and_never_redirects(self, layout, tmp_path):
        primary, _ = layout
        shared = primary / ".claude" / "worktrees" / "on-main"
        _git("worktree", "add", "-q", "-b", "main", str(shared), cwd=primary)
        result = pwg.write_claim(str(primary), "s1", str(shared))
        assert result["status"] == "error" and "shared branch" in result["error"]
        # Even a hand-written claim pointing at it must not redirect.
        claims = primary / pwg.CLAIMS_REL
        claims.parent.mkdir(parents=True, exist_ok=True)
        claims.write_text(json.dumps({"s1": {"worktree": str(shared.resolve()), "branch": "main"}}))
        assert _hook(_write(primary))["permissionDecision"] == "deny"

    def test_unregistered_directory_cannot_be_claimed(self, layout, tmp_path):
        primary, _ = layout
        stray = tmp_path / "stray"
        stray.mkdir()
        assert pwg.write_claim(str(primary), "s1", str(stray))["status"] == "error"

    def test_malformed_claim_file_refuses_not_crashes(self, layout):
        primary, _ = layout
        claims = primary / pwg.CLAIMS_REL
        claims.parent.mkdir(parents=True, exist_ok=True)
        claims.write_text("{not json")
        out = _hook(_write(primary))
        assert out["permissionDecision"] == "deny"
        assert "failed closed" not in out["permissionDecisionReason"]

    def test_release_and_teardown_drop_the_claim(self, layout):
        primary, wt = layout
        pwg.write_claim(str(primary), "s1", str(wt))
        assert pwg.write_claim(str(primary), "s1", None)["status"] == "released"
        pwg.write_claim(str(primary), "s2", str(wt))
        assert pwg.release_claims_for(str(primary), str(wt)) == ["s2"]
        assert pwg.read_claims(str(primary)) == {}


class TestLiteralAssignmentCd:
    def test_cd_into_assigned_worktree_is_not_a_primary_write(self, layout):
        primary, wt = layout
        payload = _write(primary)
        payload["tool_name"] = "Bash"
        payload["tool_input"] = {"command": f"W={wt}; cd $W; echo x > notes.txt"}
        assert _hook(payload) is None  # allowed: resolves into the worktree

    def test_braced_and_quoted_forms(self):
        cmd = "W='/a b'; X=/c; cd \"${W}\" && cd $X/d"
        assert pwg.expand_literal_assignments(cmd) == "W='/a b'; X=/c; cd \"/a b\" && cd /c/d"

    def test_non_literal_value_stays_unresolved(self):
        cmd = "W=$(pwd); cd $W"
        assert pwg.expand_literal_assignments(cmd) == cmd

    def test_use_before_assignment_is_not_expanded(self):
        assert pwg.expand_literal_assignments("cd $W; W=/x") == "cd $W; W=/x"

    def test_cd_into_assigned_primary_still_refuses(self, layout):
        primary, _ = layout
        payload = _write(primary)
        payload["tool_name"] = "Bash"
        payload["tool_input"] = {"command": f"P={primary}; cd $P; echo x > app.py"}
        assert _hook(payload)["permissionDecision"] == "deny"


class TestPostHookPathIdentity:
    def test_unstaging_preexisting_files_is_not_new_dirt(self):
        before = "A  owner.jpeg\nA  owner.docx"
        after = "?? owner.jpeg\n?? owner.docx"
        assert pwg.diff_new_primary_dirt(before, after) == []

    def test_no_baseline_reports_nothing(self):
        assert pwg.diff_new_primary_dirt(None, "?? anything.txt") == []

    def test_genuinely_new_path_is_reported(self):
        assert pwg.diff_new_primary_dirt("?? old.txt", "?? old.txt\n?? new.txt") == ["new.txt"]
