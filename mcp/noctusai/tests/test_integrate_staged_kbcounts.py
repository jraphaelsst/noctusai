"""2026-10-09: a failed KB-counts commit left 02-LANDSCAPE.md STAGED; the next
integrate retry's rebase was refused ("Your index contains uncommitted
changes") and reported `Dirty files: []`. Real git throughout."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import _benign_stash as BS  # noqa: E402
from tools.noctus.dev import task_branch as T  # noqa: E402

LANDSCAPE = "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md"


def _git(cwd: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "dev")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "KNOWLEDGE-BASE/CONTEXT").mkdir(parents=True)
    (tmp_path / LANDSCAPE).write_text("Social Wiring | 401 tests\n")
    (tmp_path / "work.py").write_text("x = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _run_git(cwd):
    def run(*a):
        p = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr
    return run


def test_discard_derived_returns_staged_derived_doc_to_head(repo):
    (repo / LANDSCAPE).write_text("Social Wiring | 402 tests\n")
    _git(repo, "add", LANDSCAPE)
    stash_before = _git(repo, "stash", "list")

    r = BS.discard_derived(_run_git(repo), [LANDSCAPE])

    assert r["discarded"] == [LANDSCAPE] and r["dropped"] is True
    assert _git(repo, "status", "--porcelain") == ""
    assert _git(repo, "stash", "list") == stash_before  # no entry left behind


def test_discard_derived_refuses_real_work(repo):
    (repo / "work.py").write_text("x = 2\n")
    _git(repo, "add", "work.py")

    r = BS.discard_derived(_run_git(repo), ["work.py"])

    assert r["discarded"] == [] and r["refused"] == ["work.py"]
    assert (repo / "work.py").read_text() == "x = 2\n"  # never touched


def test_failed_kb_counts_commit_leaves_nothing_staged(repo):
    hooks = repo / ".git" / "hooks"
    (hooks / "pre-commit").write_text("#!/bin/sh\necho blocked by keeper >&2\nexit 1\n")
    (hooks / "pre-commit").chmod(0o755)

    def regen(_root):
        (repo / LANDSCAPE).write_text("Social Wiring | 402 tests\n")
        return {"ok": True}

    def runner(cmd, cwd=None):
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    r = T._regenerate_and_commit_kb_counts(runner, str(repo), str(repo), regen, False)

    assert r["ok"] is False and "commit failed" in r["error"]
    assert r["discard"]["discarded"] == [LANDSCAPE]
    assert _git(repo, "diff", "--cached", "--name-only") == ""
    assert _git(repo, "status", "--porcelain") == ""
    # a rebase is no longer refused by the index
    assert subprocess.run(["git", "rebase", "HEAD"], cwd=repo, capture_output=True).returncode == 0
