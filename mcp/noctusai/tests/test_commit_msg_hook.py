"""Tests for scripts/hooks/commit-msg — the ship-consent `Noc-Branch:` trailer.

The hook script is invoked DIRECTLY (as git would, with the message file as
$1) inside a throwaway repo — no hook installation, no hooks-path override.
KB § PATTERNS/devops/ship-consent-riders.md.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "commit-msg"
_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, env=_ENV)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "f").write_text("0\n")
    _git(tmp_path, "add", "f")
    _git(tmp_path, "commit", "-qm", "root")
    _git(tmp_path, "checkout", "-qb", "feat/x")
    return tmp_path


def _hook(repo: Path, text: str) -> str:
    msg = repo / "MSG"
    msg.write_text(text)
    r = subprocess.run(["bash", str(HOOK), str(msg)], cwd=str(repo),
                       capture_output=True, text=True, env=_ENV)
    assert r.returncode == 0, r.stderr  # never blocks a commit
    return msg.read_text()


def test_appends_trailer_on_a_branch(repo):
    out = _hook(repo, "feat: thing\n\nbody\n")
    assert out.rstrip().endswith("Noc-Branch: feat/x")
    assert "\n\nNoc-Branch: feat/x" in out


def test_keeps_other_trailers_in_one_block(repo):
    out = _hook(repo, "feat: thing\n\nCo-Authored-By: A <a@a>\n")
    assert "Co-Authored-By: A <a@a>\nNoc-Branch: feat/x" in out


def test_never_rewrites_an_existing_trailer(repo):
    out = _hook(repo, "feat: thing\n\nNoc-Branch: feat/origin\n")
    assert out.count("Noc-Branch:") == 1 and "feat/origin" in out


def test_skips_detached_head(repo):
    _git(repo, "checkout", "-q", "--detach")
    assert "Noc-Branch" not in _hook(repo, "feat: thing\n")


def test_skips_merge_commits(repo):
    gitdir = Path(_git(repo, "rev-parse", "--absolute-git-dir").strip())
    (gitdir / "MERGE_HEAD").write_text(_git(repo, "rev-parse", "HEAD"))
    assert "Noc-Branch" not in _hook(repo, "Merge branch 'x'\n")


def test_empty_message_stays_empty(repo):
    assert _hook(repo, "# only a comment\n\n") == "# only a comment\n\n"


def test_trailer_survives_cherry_pick_and_rebase(repo):
    (repo / "f").write_text("1\n")
    _git(repo, "add", "f")
    msg = _hook(repo, "feat: carried\n")
    _git(repo, "commit", "-q", "-F", str(repo / "MSG"))
    sha = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "-b", "release/x", "main")
    _git(repo, "cherry-pick", "-x", sha)
    body = _git(repo, "log", "-1", "--format=%B")
    assert "Noc-Branch: feat/x" in body and msg
    trailers = _git(repo, "log", "-1", "--format=%(trailers:key=Noc-Branch,valueonly)").strip()
    assert trailers == "feat/x"
