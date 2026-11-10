"""task_branch resolves a slug's worktree from `git worktree list --porcelain`
by BRANCH, not by the canonical `.claude/worktrees/<slug>` path.

Root cause (N=3, 2026-11-07): an engineer worked in an Agent-tool isolation
worktree `.claude/worktrees/agent-<id>` holding `feat/<slug>`; enqueue assumed
the canonical path and failed with ENOENT. Real temp git repo, injected runner
(no monkeypatching of our own guards).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import task_branch as T  # noqa: E402


def _sh(*cmd: str, cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def _repo(tmp_path: Path, wt_dir_name: str | None) -> Path:
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    _sh("git", "init", "--bare", "-b", "dev", str(origin), cwd=tmp_path)
    _sh("git", "clone", str(origin), str(repo), cwd=tmp_path)
    _sh("git", "checkout", "-b", "dev", cwd=repo)
    (repo / "a.txt").write_text("a\n")
    _sh("git", "add", "a.txt", cwd=repo)
    _sh("git", "commit", "-m", "init", cwd=repo)
    _sh("git", "push", "origin", "dev", cwd=repo)
    if wt_dir_name:
        wt = repo / ".claude" / "worktrees" / wt_dir_name
        _sh("git", "worktree", "add", str(wt), "-b", "feat/x", "origin/dev", cwd=repo)
        (wt / "b.txt").write_text("b\n")
        _sh("git", "add", "b.txt", cwd=wt)
        _sh("git", "commit", "-m", "feat: b", cwd=wt)
    return repo


def _runner(repo: Path):
    def run(cmd, cwd=None):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or str(repo))
        return r.returncode, r.stdout or "", r.stderr or ""
    return run


_CONTRACT = {"deliverable_kwargs": {
    "derived_check": lambda head: {"ok": True, "measured": True, "detail": "n/a", "results": []},
    "scoped_check": lambda branch, head: {"ok": True, "detail": "n/a"}}}


def test_enqueue_plan_resolves_an_agent_isolation_worktree(tmp_path):
    repo = _repo(tmp_path, "agent-abc123")
    # enqueue is a pure push: it needs the branch PUSHED + clean (delivery contract), not a rebase
    _sh("git", "push", "origin", "feat/x", cwd=repo / ".claude/worktrees/agent-abc123")
    res = T.task_branch(action="enqueue", slug="x", confirm=False,
                        run=_runner(repo), primary_root=str(repo), **_CONTRACT)
    assert res["status"] == "planned", res
    assert res["worktree"].endswith(".claude/worktrees/agent-abc123"), res
    assert os.path.isabs(res["worktree"])
    assert res["worktree_resolved_from"] == "git_worktree_list"


def test_canonical_path_is_preferred_when_present(tmp_path):
    repo = _repo(tmp_path, "x")
    _sh("git", "push", "origin", "feat/x", cwd=repo / ".claude/worktrees/x")
    res = T.task_branch(action="enqueue", slug="x", confirm=False,
                        run=_runner(repo), primary_root=str(repo), **_CONTRACT)
    assert res["status"] == "planned", res
    assert res["worktree"] == ".claude/worktrees/x"
    assert res["worktree_resolved_from"] == "canonical"


def test_branch_checked_out_nowhere_names_expected_path_and_branch(tmp_path):
    repo = _repo(tmp_path, None)
    _sh("git", "branch", "feat/x", "origin/dev", cwd=repo)
    # `integrate` (the legacy local-gates path) still needs a worktree holding the branch;
    # `enqueue` is a pure push and does not (its tree-clean item notes "no worktree holds the branch").
    res = T.task_branch(action="integrate", slug="x", confirm=False,
                        run=_runner(repo), primary_root=str(repo))
    assert res["status"] == "error" and res["exit_code"] == 1, res
    assert "feat/x" in res["error"] and ".claude/worktrees/x" in res["error"]


def test_resolver_unit_matches_by_branch_not_dirname():
    porcelain = ("worktree /r\nHEAD m\nbranch refs/heads/dev\n\n"
                 "worktree /r/.claude/worktrees/agent-1\nHEAD a\nbranch refs/heads/feat/x\n\n")
    assert T._resolve_worktree_for_branch(porcelain, "feat/x", ".claude/worktrees/x") == (
        "/r/.claude/worktrees/agent-1", "git_worktree_list", "/r/.claude/worktrees/agent-1")
    assert T._resolve_worktree_for_branch("", "feat/x", ".claude/worktrees/x") == (
        ".claude/worktrees/x", "canonical", None)


def test_start_adopts_a_branch_already_checked_out_elsewhere(tmp_path):
    repo = _repo(tmp_path, "agent-abc123")
    res = T.task_branch(action="start", slug="x", confirm=True, wire_env=False,
                        run=_runner(repo), primary_root=str(repo))
    assert res["status"] == "started" and res["already_existed"] is True, res
    assert res["worktree"].endswith("agent-abc123")
