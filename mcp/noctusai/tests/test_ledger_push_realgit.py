"""REAL-git regression test for the primary/origin divergence loop.

WHY THIS FILE EXISTS AND IS NOT A FAKE. The rest of `_ledger_push`'s coverage
(`test_ledger_push.py`) injects a scriptable fake runner whose ``rebase`` returns
a pre-scripted rc regardless of working-tree state. That fake CANNOT model the
bug this file pins: real ``git rebase`` REFUSES outright when the tree is dirty,
whatever the rebase would otherwise do. Every fake-based test passed while the
bug was live, for four-plus sessions.

THE BUG (fixed 2026-08-31). `commit_and_ff_push_ledger` commits a
``project-history/*.ndjson`` row on the PRIMARY checkout, then rebases onto
``origin/dev`` before pushing. The cost-log pre-commit hook dirties
``project-history/vector-costs.ndjson`` on essentially every commit — including
the one made moments earlier — so the rebase was refused with "cannot rebase: You
have unstaged changes", the helper returned ``committed_locally=True,
pushed=False``, and the primary was left DIVERGED from ``origin/dev``. It was
hand-fixed once per session with ``git -c rebase.autoStash=true rebase
origin/dev`` and accumulated 4+ ledger entries before the cause was pinned.

The old code also MISLABELLED the refusal as a rebase *conflict* — the same
"refused vs conflicted" distinction `task_branch` already knew about as Bug B.

KB § PATTERNS/common/self-branching-mode.md
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tools.noctus.dev._ledger_push import commit_and_ff_push_ledger  # noqa: E402

LEDGER = "project-history/worktree-salvage.ndjson"
COSTS = "project-history/vector-costs.ndjson"


def _git(*args: str, cwd: str | None = None) -> tuple[int, str, str]:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def _identity(repo: str) -> None:
    _git("config", "user.email", "test@noctusai.local", cwd=repo)
    _git("config", "user.name", "noc test", cwd=repo)


@pytest.fixture()
def stale_primary_with_dirty_hook_artifact():
    """Build the exact incident shape:

    * ``origin/dev`` has been advanced by a peer (a worktree ``integrate``), so
      the primary's local ``dev`` is STALE — a rebase is genuinely required.
    * the primary tree is dirty with a known-benign hook artifact
      (``vector-costs.ndjson``) — which is what refuses the rebase.
    """
    tmp = tempfile.mkdtemp(prefix="noc-divloop-")
    origin = os.path.join(tmp, "origin.git")
    primary = os.path.join(tmp, "primary")
    peer = os.path.join(tmp, "peer")

    _git("init", "--bare", "-b", "dev", origin)
    _git("clone", origin, primary)
    _identity(primary)
    pathlib.Path(primary, "project-history").mkdir(parents=True)
    pathlib.Path(primary, LEDGER).write_text('{"row": 0}\n')
    pathlib.Path(primary, COSTS).write_text('{"cost": 0}\n')
    pathlib.Path(primary, ".gitattributes").write_text(
        "project-history/*.ndjson merge=union\n")
    _git("add", "-A", cwd=primary)
    _git("commit", "-m", "base", cwd=primary)
    _git("push", "origin", "HEAD:dev", cwd=primary)

    # A peer advances origin/dev — the primary's local dev is now behind.
    _git("clone", origin, peer)
    _identity(peer)
    pathlib.Path(peer, "PEER.md").write_text("peer work\n")
    _git("add", "-A", cwd=peer)
    _git("commit", "-m", "peer advances dev", cwd=peer)
    _git("push", "origin", "HEAD:dev", cwd=peer)

    # A new ledger row to deliver + the hook artifact dirtying the tree.
    pathlib.Path(primary, LEDGER).write_text(
        '{"row": 0}\n{"row": 1, "recovery": "pointer"}\n')
    pathlib.Path(primary, COSTS).write_text(
        '{"cost": 0}\n{"cost": 1, "hook": "dirtied me"}\n')
    yield origin, primary


def _runner_for(primary: str):
    def runner(cmd, cwd=None):
        r = subprocess.run(cmd, cwd=cwd or primary, capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr
    return runner


def test_stale_primary_with_benign_dirt_still_lands_the_row(
    stale_primary_with_dirty_hook_artifact,
):
    """The regression: the row must reach origin/dev, the primary must end level
    with origin (NOT diverged), the peer's work must survive, and the benign
    artifact must be restored to the working tree."""
    origin, primary = stale_primary_with_dirty_hook_artifact

    res = commit_and_ff_push_ledger(
        runner=_runner_for(primary), root=primary, rel_paths=[LEDGER],
        commit_msg="chore(salvage): record recovery pointer",
        already_committed=False,
    )

    assert res.get("pushed") is True, f"row not pushed: {res!r}"

    # 1. the row actually landed on origin/dev
    _rc, out, _ = _git("show", f"dev:{LEDGER}", cwd=origin)
    assert "recovery" in out, "the ledger row never reached origin/dev"

    # 2. THE LOOP ITSELF: primary must be level with origin, not diverged
    _git("fetch", "origin", cwd=primary)
    _rc, counts, _ = _git("rev-list", "--left-right", "--count",
                          "origin/dev...HEAD", cwd=primary)
    assert counts.strip() == "0\t0", (
        f"primary is diverged from origin/dev ({counts.strip()!r}) — this is the "
        "recurring loop the fix exists to close")

    # 3. the peer's commit was not clobbered
    _rc, peer_out, _ = _git("show", "dev:PEER.md", cwd=origin)
    assert "peer work" in peer_out

    # 4. the benign artifact was restored, not left stashed
    _rc, status, _ = _git("status", "--porcelain", cwd=primary)
    assert COSTS in status, f"benign artifact not restored: {status!r}"
    _rc, stashes, _ = _git("stash", "list", cwd=primary)
    assert not stashes.strip(), f"a stash was left behind: {stashes!r}"


def test_real_uncommitted_work_blocks_loudly_instead_of_diverging_silently(
    stale_primary_with_dirty_hook_artifact,
):
    """Genuine in-progress work must never be silently stashed. It blocks — but
    as an explicit dirty_blocked naming the file, not a mystery divergence."""
    _origin, primary = stale_primary_with_dirty_hook_artifact
    pathlib.Path(primary, "REAL_WORK.py").write_text("x = 1\n")

    res = commit_and_ff_push_ledger(
        runner=_runner_for(primary), root=primary, rel_paths=[LEDGER],
        commit_msg="chore(salvage): record recovery pointer",
        already_committed=False,
    )

    assert res["ok"] is False
    assert res["status"] == "dirty_blocked"
    assert any("REAL_WORK.py" in f for f in res["dirty_files"]), res
    assert "REAL_WORK.py" in res["error"]

    # the real work is untouched and unstashed
    assert pathlib.Path(primary, "REAL_WORK.py").read_text() == "x = 1\n"
    _rc, stashes, _ = _git("stash", "list", cwd=primary)
    assert not stashes.strip(), f"real work was stashed: {stashes!r}"
