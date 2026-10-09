"""`primary_ff.ff_primary_to_dev` against REAL git: a bare remote, the
"primary" clone on dev, and a peer clone that pushes ahead of it."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from primary_ff import ff_primary_to_dev, summary_line  # noqa: E402


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def _commit(repo: Path, name: str, body: str = "x\n") -> None:
    (repo / name).write_text(body)
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"add {name}")


@pytest.fixture
def repos(tmp_path):
    remote, primary, peer = tmp_path / "remote.git", tmp_path / "primary", tmp_path / "peer"
    _git(tmp_path, "init", "-q", "--bare", "-b", "dev", str(remote))
    for clone in (primary, peer):
        _git(tmp_path, "clone", "-q", str(remote), str(clone))
        _git(clone, "config", "user.email", "t@t")
        _git(clone, "config", "user.name", "t")
        _git(clone, "config", "core.hooksPath", "/dev/null")
    _commit(primary, "base.txt")
    _git(primary, "push", "-q", "origin", "HEAD:dev")
    _git(primary, "branch", "-q", "--set-upstream-to=origin/dev")
    _git(peer, "pull", "-q", "origin", "dev")
    return primary, peer


def _peer_pushes(peer: Path, name: str = "new.txt") -> None:
    _commit(peer, name)
    _git(peer, "push", "-q", "origin", "HEAD:dev")


def test_fast_forwards_when_behind(repos):
    primary, peer = repos
    _peer_pushes(peer)

    r = ff_primary_to_dev(str(primary), fetch=True)

    assert r["status"] == "fast_forwarded" and r["commits"] == 1
    assert (primary / "new.txt").exists()
    assert "fast-forwarded" in summary_line(r)


def test_up_to_date_is_quiet(repos):
    primary, _peer = repos

    r = ff_primary_to_dev(str(primary), fetch=True)

    assert r["status"] == "up_to_date" and summary_line(r) == ""


def test_untracked_files_are_left_alone(repos):
    primary, peer = repos
    (primary / "scratch.whl").write_text("mine")
    _peer_pushes(peer)

    r = ff_primary_to_dev(str(primary), fetch=True)

    assert r["status"] == "fast_forwarded"
    assert (primary / "scratch.whl").read_text() == "mine"


def test_untracked_file_the_ff_would_overwrite_is_refused_loudly(repos):
    primary, peer = repos
    (primary / "new.txt").write_text("my untracked copy")
    _peer_pushes(peer, "new.txt")

    r = ff_primary_to_dev(str(primary), fetch=True)

    assert r["status"] == "skipped_ff_failed"
    assert (primary / "new.txt").read_text() == "my untracked copy"
    assert "NOT fast-forwarded" in summary_line(r)


@pytest.mark.parametrize("staged", [False, True])
def test_tracked_modification_is_never_touched(repos, staged):
    primary, peer = repos
    (primary / "base.txt").write_text("local edit\n")
    if staged:
        _git(primary, "add", "base.txt")
    _peer_pushes(peer)
    head = _git(primary, "rev-parse", "HEAD")

    r = ff_primary_to_dev(str(primary), fetch=True)

    assert r["status"] == "skipped_dirty" and r["files"] == ["base.txt"]
    assert _git(primary, "rev-parse", "HEAD") == head
    assert (primary / "base.txt").read_text() == "local edit\n"


def test_non_dev_branch_is_never_touched(repos):
    primary, peer = repos
    _git(primary, "switch", "-q", "-c", "feat/x")
    _peer_pushes(peer)

    assert ff_primary_to_dev(str(primary), fetch=True)["status"] == "skipped_branch"


def test_detached_head_is_never_touched(repos):
    primary, peer = repos
    _git(primary, "switch", "-q", "--detach")
    _peer_pushes(peer)

    assert ff_primary_to_dev(str(primary), fetch=True)["status"] == "skipped_detached"


def test_diverged_dev_is_never_touched(repos):
    primary, peer = repos
    _commit(primary, "local-only.txt")
    _peer_pushes(peer)
    head = _git(primary, "rev-parse", "HEAD")

    r = ff_primary_to_dev(str(primary), fetch=True)

    assert r["status"] == "skipped_diverged"
    assert _git(primary, "rev-parse", "HEAD") == head


def test_without_fetch_uses_the_existing_remote_ref(repos):
    primary, peer = repos
    _peer_pushes(peer)

    # task_branch integrate's case: no fetch; the ref is stale here, so nothing moves
    assert ff_primary_to_dev(str(primary))["status"] == "up_to_date"
    _git(primary, "fetch", "-q", "origin")
    assert ff_primary_to_dev(str(primary))["status"] == "fast_forwarded"


def test_task_branch_integrate_hook_uses_the_runner(repos):
    from tools.noctus.dev.task_branch import _ff_primary_after_integrate

    primary, peer = repos
    _peer_pushes(peer)
    _git(primary, "fetch", "-q", "origin")

    def runner(cmd, cwd=None):
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        return p.returncode, p.stdout, p.stderr

    r = _ff_primary_after_integrate(runner, str(primary), "dev", "origin")

    assert r["status"] == "fast_forwarded"


def test_task_branch_git_wrapper_still_bans_merge():
    from tools.noctus.dev.task_branch import _git as tb_git

    with pytest.raises(ValueError):
        tb_git(lambda *a, **k: (0, "", ""), "merge", "--ff-only", "origin/dev")
