"""`branch_pointer.ensure_for_push` + `cli.py --ensure-branch-pointer`: the pre-push construction leg.

Class 12 of the 2026-11-14 CI-refusal inventory: 72 pre-push refusals because a branch had no branch-tree
pointer (or one older than the keeper's 72h), fixed by hand every time. The writer is `branch_pointer.append` /
`update` - the one writer; `ensure_for_push` only decides WHETHER to call it. Real git, Fake ledger store.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.noctus.dev.branch_pointer as BP  # noqa: E402
from tools.noctus.dev.compliance import check_branch_tree_mirror  # noqa: E402

CLI = Path(__file__).resolve().parents[1] / "cli.py"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "test-session-id")
    monkeypatch.setattr(BP, "LEDGER_PATH", tmp_path / "ledger" / "branch-tree.ndjson")


def _git(cwd, *a, when: datetime | None = None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when.isoformat()
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-b", "dev")
    (r / "a.txt").write_text("a\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-m", "init")
    _git(r, "update-ref", "refs/remotes/origin/dev", "HEAD")
    _git(r, "checkout", "-b", "feat/x")
    (r / "b.txt").write_text("b\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-m", "feat: b")
    return r


def _seed(row: dict) -> None:
    BP.LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BP.LEDGER_PATH.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _row(repo, *, ts: datetime, status="on_going", commit=None, branch="feat/x"):
    return {"ts": ts.isoformat(), "branch": branch, "base": "origin/dev", "commit": commit or _git(repo, "rev-parse", branch),
            "worktree": None, "role": "orchestrator", "agent": "a", "parent": "dev", "session": "s", "paths": [],
            "status": status, "brief": "b", "notes": ""}


def _rows():
    return [json.loads(x) for x in BP.LEDGER_PATH.read_text().splitlines() if x.strip()]


def test_a_branch_with_no_pointer_gets_one_that_the_keeper_accepts(repo):
    assert check_branch_tree_mirror(branch="feat/x", repo_root=repo)  # refused before the construction leg runs
    r = BP.ensure_for_push(branch="feat/x", root=repo)
    assert r["ok"] and r["action"] == "appended"
    rows = _rows()
    assert len(rows) == 1 and rows[0]["branch"] == "feat/x" and rows[0]["status"] == "on_going"
    assert rows[0]["commit"] == _git(repo, "rev-parse", "feat/x") and rows[0]["session"] == "test-session-id"
    assert rows[0]["paths"] == ["b.txt"] and rows[0]["base"].startswith("origin/dev@")
    ledger = repo / "project-history" / "branch-tree.ndjson"
    ledger.parent.mkdir()
    ledger.write_text(BP.LEDGER_PATH.read_text())  # the keeper reads the root's own copy in Fake mode
    assert check_branch_tree_mirror(branch="feat/x", repo_root=repo) == []


def test_a_fresh_pointer_is_a_no_op_that_writes_nothing(repo):
    _seed(_row(repo, ts=datetime.now(timezone.utc)))
    r = BP.ensure_for_push(branch="feat/x", root=repo)
    assert r["ok"] and r["action"] == "unchanged"
    assert len(_rows()) == 1


def test_a_pointer_older_than_the_refresh_margin_is_refreshed_before_the_keepers_72h(repo):
    tip = datetime.now(timezone.utc)
    _seed(_row(repo, ts=tip - timedelta(hours=BP.ENSURE_REFRESH_HOURS + 5)))
    r = BP.ensure_for_push(branch="feat/x", root=repo)
    assert r["ok"] and r["action"] == "updated" and "behind the branch tip" in r["reasons"][0]
    assert len(_rows()) == 2 and _rows()[-1]["ts"] > _rows()[0]["ts"]


def test_a_shipped_pointer_on_a_branch_that_moved_on_is_revived_not_left_to_block(repo):
    old = _git(repo, "rev-parse", "HEAD~1")
    _seed(_row(repo, ts=datetime.now(timezone.utc), status="shipped", commit=old))
    r = BP.ensure_for_push(branch="feat/x", root=repo)
    assert r["ok"] and r["action"] == "updated"
    assert _rows()[-1]["status"] == "on_going" and _rows()[-1]["commit"] == _git(repo, "rev-parse", "feat/x")


def test_a_pointer_whose_commit_does_not_resolve_is_repointed_at_the_tip(repo):
    _seed(_row(repo, ts=datetime.now(timezone.utc), commit="deadbeef" * 5))
    r = BP.ensure_for_push(branch="feat/x", root=repo)
    assert r["ok"] and r["action"] == "updated"
    assert _rows()[-1]["commit"] == _git(repo, "rev-parse", "feat/x")


def test_a_name_that_is_not_a_local_branch_is_refused_naming_why(repo):
    """The pre-push hook is handed a bare sha as the 'branch' of a sha push: never invent a pointer for it."""
    r = BP.ensure_for_push(branch=_git(repo, "rev-parse", "HEAD"), root=repo)
    assert not r["ok"] and "not a local branch" in r["error"]
    assert not BP.LEDGER_PATH.exists()


def test_a_pointer_that_cannot_be_written_is_refused_naming_why(repo, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    monkeypatch.setattr(BP, "_resolve_session_id", lambda: None)
    r = BP.ensure_for_push(branch="feat/x", root=repo)
    assert not r["ok"] and "session" in r["error"]


def test_the_cli_flag_is_registered_and_refuses_with_exit_1_naming_why(repo):
    env = {**os.environ, "NOCTUS_HOOK_QUIET": "1", "CLAUDE_CODE_SESSION_ID": ""}
    r = subprocess.run([sys.executable, str(CLI), "--ensure-branch-pointer", "not-a-branch",
                        "--worktree-path", str(repo)], capture_output=True, text=True, env=env)
    assert r.returncode == 1 and "could not be written" in r.stdout and "not a local branch" in r.stdout


def test_a_hooked_keeper_flag_judges_the_worktree_path_tree_not_the_toolkits_own(repo):
    """15a: the hook runs the PRIMARY's cli.py with --worktree-path <worktree>; the keeper must read THAT tree."""
    ledger = repo / "project-history" / "branch-tree.ndjson"
    ledger.parent.mkdir()
    ledger.write_text(json.dumps(_row(repo, ts=datetime.now(timezone.utc))) + "\n")
    env = {**os.environ, "NOCTUS_HOOK_QUIET": "1"}

    def run(branch):
        return subprocess.run([sys.executable, str(CLI), "--check-branch-tree-mirror", branch,
                               "--worktree-path", str(repo)], capture_output=True, text=True, env=env).stdout

    assert "No branch-pointer found for 'feat/zzz'" in run("feat/zzz")
    assert "No branch-pointer found" not in run("feat/x")
