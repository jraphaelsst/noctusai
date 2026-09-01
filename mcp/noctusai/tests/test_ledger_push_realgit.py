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


# ── take 2: the divergence loop RECURRED after the 2026-08-31 fix above ───────
#
# THE BUG (fixed 2026-08-31, later same day). The first fix stashes a
# PRE-EXISTING dirty benign artifact before the rebase. It does NOT cover a
# DIFFERENT mechanism: `git commit -m msg -- rel_paths` (`--only` included)
# does NOT actually restrict the resulting commit to `rel_paths` — that only
# controls what git stages FOR YOU from the pathspec. Whatever a pre-commit
# HOOK further stages *during* that same `git commit` invocation (via its own
# `git add`) rides into the SAME commit regardless. Verified empirically with
# plain git (no python involved): a pre-commit hook that `git add`s a second
# file mid-commit puts that file in the resulting tree even under
# `git commit --only -- <pathspec>`.
#
# Our own pre-commit hook's step 10c does exactly this on EVERY commit — it
# drains the vector-costs spool into `project-history/vector-costs.ndjson` and
# unconditionally `git add`s it (BY DESIGN: KB § PATTERNS/common/
# vector-cost-tracking.md — "rides along with whatever is being committed").
# So the ledger commit this helper makes ends up touching TWO files:
# `rel_paths` (the caller's ledger) AND `vector-costs.ndjson` (the hook's
# rider) — but the divergence guard's `ledger_set` only ever knew about
# `rel_paths`. It saw a commit touching a path outside `ledger_set`, correctly
# by ITS OWN (incomplete) rule, and refused: `committed_locally=True,
# retryable=False`. Collapsed through `task_branch._push_salvage_ledger_from_
# primary`'s old `bool(res.get("pushed"))` return, that surfaced as a bare
# `salvage_pushed: false` with no reason.
#
# WORSE than the first bug: the stranded commit does not go away on its own.
# Every subsequent salvage-push call sees the SAME tainted commit still ahead
# of origin/dev and refuses again — SELF-LATCHING, unlike a dirty-tree refusal
# (which clears the moment the tree is clean). This matches the observed
# "8 behind / 1 ahead, needed manual `git rebase`+`push` once per session"
# shape exactly.
#
# THE FIX. The divergence guard now tolerates a rider IFF it is a
# known-benign refresh artifact (`_benign_stash.is_benign` — the SAME
# predicate the stash pre-check already uses, not a second hand-maintained
# list). A rider that is NOT declared benign still blocks loudly, preserving
# "real work never leaks onto dev, no matter how it got staged."
def _install_cost_ledger_drain_hook(repo: str) -> None:
    """A REAL `.git/hooks/pre-commit` that mimics the noc pre-commit hook's
    step 10c: unconditionally append a row to `project-history/vector-costs.
    ndjson` + `git add` it, on EVERY commit — the exact mid-commit staging
    side effect that rode into the ledger commit and stranded it."""
    hook = pathlib.Path(repo, ".git", "hooks", "pre-commit")
    hook.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'echo \'{{"cost": "drained"}}\' >> {COSTS}\n'
        f"git add -- {COSTS}\n"
    )
    hook.chmod(0o755)


@pytest.fixture()
def stale_primary_with_hook_that_stages_mid_commit():
    """The take-2 incident shape: origin/dev has advanced (rebase genuinely
    required), the primary tree starts CLEAN (no pre-existing dirt — the first
    fix's stash pre-check is a no-op here), and a REAL pre-commit hook stages a
    second ledger-shaped file DURING the commit this helper makes."""
    tmp = tempfile.mkdtemp(prefix="noc-divloop2-")
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
    _install_cost_ledger_drain_hook(primary)

    # A peer advances origin/dev — the primary's local dev is now behind.
    _git("clone", origin, peer)
    _identity(peer)
    pathlib.Path(peer, "PEER.md").write_text("peer work\n")
    _git("add", "-A", cwd=peer)
    _git("commit", "-m", "peer advances dev", cwd=peer)
    _git("push", "origin", "HEAD:dev", cwd=peer)

    # A new ledger row to deliver. The tree is otherwise CLEAN — the hook is
    # the only source of the second file, not pre-existing dirt.
    pathlib.Path(primary, LEDGER).write_text(
        '{"row": 0}\n{"row": 1, "recovery": "pointer"}\n')
    yield origin, primary


def _old_divergence_guard_would_block(changed: list[str], ledger_set: set[str]) -> bool:
    """The EXACT pre-fix predicate `_push_leg` used (before `is_benign` was
    added) — pinned here as the control. `changed` = one ahead-commit's
    `git diff-tree --name-only` output."""
    return any(f not in ledger_set for f in changed)


def test_hook_injected_rider_no_longer_strands_the_commit(
    stale_primary_with_hook_that_stages_mid_commit,
):
    """THE FIX, end to end with real git: a hook that stages a known-benign
    rider mid-commit must not strand the ledger commit — the row lands on
    origin/dev, and the primary ends up level with it."""
    origin, primary = stale_primary_with_hook_that_stages_mid_commit

    # ── control run: prove the commit is genuinely two-file (the mechanism) ──
    res = commit_and_ff_push_ledger(
        runner=_runner_for(primary), root=primary, rel_paths=[LEDGER],
        commit_msg="chore(salvage): record recovery pointer",
        already_committed=False,
    )

    # The ledger commit the helper made is on local dev; inspect what it
    # actually touched (real git, not an assumption).
    _rc, tip, _ = _git("rev-parse", "HEAD", cwd=primary)
    _rc, changed_out, _ = _git(
        "diff-tree", "--no-commit-id", "--name-only", "-r", tip.strip(), cwd=primary)
    changed = [f for f in changed_out.splitlines() if f.strip()]
    assert LEDGER in changed and COSTS in changed, (
        f"expected the hook's rider to ride into the SAME commit: {changed!r}")

    # CONTROL: the pre-fix predicate, run against this SAME real commit,
    # would have blocked it — proving the bug is real, not merely theorized.
    assert _old_divergence_guard_would_block(changed, {LEDGER}) is True, (
        "control failed: the pre-fix predicate should flag this commit as "
        "non-ledger (that IS the bug being fixed)")

    # THE FIX: the actual helper call above must still have succeeded.
    assert res.get("pushed") is True, f"row not pushed despite a benign rider: {res!r}"
    assert res.get("status") == "pushed"

    _rc, out, _ = _git("show", f"dev:{LEDGER}", cwd=origin)
    assert "recovery" in out, "the ledger row never reached origin/dev"

    _git("fetch", "origin", cwd=primary)
    _rc, counts, _ = _git("rev-list", "--left-right", "--count",
                          "origin/dev...HEAD", cwd=primary)
    assert counts.strip() == "0\t0", (
        f"primary is diverged from origin/dev ({counts.strip()!r}) — the "
        "self-latching loop the fix exists to close")


def test_a_stranded_pre_existing_benign_only_commit_self_heals_on_the_next_call(
    stale_primary_with_hook_that_stages_mid_commit,
):
    """The self-latching property, killed: a commit already stranded by the
    OLD code (rel_paths + a benign rider, sitting ahead of origin/dev from a
    PRIOR call) must push cleanly on the VERY NEXT call — no manual
    intervention, no growing 'N behind / M ahead' forever."""
    origin, primary = stale_primary_with_hook_that_stages_mid_commit

    # Simulate a commit stranded by the pre-fix code: rel_paths + a benign
    # rider, made directly (bypassing the helper) so this run starts from
    # "already stranded" rather than creating it via the fixed helper. (The
    # fixture already wrote LEDGER's first recovery row before yielding —
    # commit that AS the stranded commit.)
    pathlib.Path(primary, COSTS).write_text('{"cost": 0}\n{"cost": "drained"}\n')
    _git("add", "--", LEDGER, COSTS, cwd=primary)
    _git("commit", "-m", "chore(salvage): stranded by the pre-fix code", cwd=primary)
    _rc, stranded_tip, _ = _git("rev-parse", "HEAD", cwd=primary)

    # A SECOND, DISTINCT salvage row to deliver on this call — must differ from
    # what the stranded commit already carries, else the commit leg's own
    # `git status --porcelain -- LEDGER` sees no diff and short-circuits
    # `already_clean` before ever reaching the push leg (the thing under test).
    pathlib.Path(primary, LEDGER).write_text(
        '{"row": 0}\n{"row": 1, "recovery": "pointer"}\n'
        '{"row": 2, "recovery": "pointer #2"}\n')

    res = commit_and_ff_push_ledger(
        runner=_runner_for(primary), root=primary, rel_paths=[LEDGER],
        commit_msg="chore(salvage): record recovery pointer #2",
        already_committed=False,
    )

    assert res.get("pushed") is True, (
        f"a pre-existing benign-only-tainted commit should NOT self-latch: {res!r}")
    # the stranded commit's ledger content reached origin/dev too (rebase
    # replays it, not just the newest one).
    _rc, out, _ = _git("show", "dev:" + LEDGER, cwd=origin)
    assert "recovery" in out
    _git("fetch", "origin", cwd=primary)
    _rc, counts, _ = _git("rev-list", "--left-right", "--count",
                          "origin/dev...HEAD", cwd=primary)
    assert counts.strip() == "0\t0", f"still diverged after self-heal: {counts.strip()!r}"


def test_a_genuinely_non_benign_rider_still_blocks_loudly(
    stale_primary_with_hook_that_stages_mid_commit,
):
    """The property the fix must preserve: a rider that is NOT a declared
    benign artifact (e.g. a real code/doc change some other hook step swept
    in) must still block — the guard's job is stopping REAL work from
    leaking onto dev, and that must survive this fix."""
    origin, primary = stale_primary_with_hook_that_stages_mid_commit

    # Replace the benign-only hook with one that ALSO stages a non-benign file
    # (a fresh untracked doc — never committed/pushed anywhere, so this cannot
    # corrupt the fixture's peer-advanced origin/dev).
    hook = pathlib.Path(primary, ".git", "hooks", "pre-commit")
    hook.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "echo 'real change' >> REAL_DOC.md\n"
        "git add -- REAL_DOC.md\n"
    )
    hook.chmod(0o755)

    res = commit_and_ff_push_ledger(
        runner=_runner_for(primary), root=primary, rel_paths=[LEDGER],
        commit_msg="chore(salvage): record recovery pointer",
        already_committed=False,
    )

    # NOTE on which path blocks it: git leaves a peculiar post-commit index
    # state for a file a hook swept into a pathspec-limited commit that is NOT
    # itself a benign pattern — REAL_DOC.md ends up in HEAD's tree (confirmed:
    # `git show --stat` on the resulting commit lists it) yet the real index
    # still reports it dirty (`D ` + `??` — two porcelain lines for one path).
    # That means this scenario is caught by the PRE-rebase `dirty_blocked`
    # check rather than the push-leg's non-ledger-commit guard — a different
    # code path than the benign case, but the property under test is the same
    # either way: a non-benign rider must never reach dev, and it must block
    # LOUDLY (named), not silently.
    assert res.get("ok") is False
    assert res.get("committed_locally") is True
    assert res.get("pushed") is not True
    assert "REAL_DOC.md" in (res.get("error") or "") or any(
        "REAL_DOC.md" in f for f in res.get("dirty_files") or []
    ), res
    _rc, remote_show, _ = _git("show", "dev:REAL_DOC.md", cwd=origin)
    assert _rc != 0, "the non-benign rider must NEVER reach origin/dev"


# ── take 3: the divergence loop RECURRED for a THIRD reason (fixed 2026-09-01) ─
#
# THE BUG. Take 2's fix made the divergence guard tolerate a rider IFF
# `_benign_stash.is_benign()` says so. But `BENIGN_REFRESH_PATTERNS` was itself
# a hand-copied list, and it was INCOMPLETE: the pre-commit hook's step 2
# (`--update-kb-counts`) rewrites THREE marker-block targets —
# `KNOWLEDGE-BASE/AGENT-CONTEXT.md`, `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, and
# `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` — and only the first two were ever
# copied into the list. `02-LANDSCAPE.md` gets rewritten (and step 2
# auto-`git add`s it, since it starts clean) on essentially every commit that
# changes the product/schema/tool counts, so it rides into the SAME commit as
# a ledger row exactly like `vector-costs.ndjson` did in take 2 — but
# `is_benign('KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md')` said False, so the
# divergence guard refused it as "non-ledger", stranding the commit.
#
# THIS TEST is real git end-to-end, mirroring take 2's harness exactly but
# with a hook that regenerates a 02-LANDSCAPE.md-SHAPED file (not
# vector-costs.ndjson again — that would only re-prove take 2). It proves the
# fix at the level that matters: `_benign_stash`'s DERIVED pattern set (read
# from `kb_sync._regions()`, not hand-copied) closes this specific gap, and a
# stale/behind primary's ledger-only push now succeeds where the old
# hand-copied list would have stranded it.
def _install_kb_counts_regen_hook(repo: str) -> None:
    """A REAL `.git/hooks/pre-commit` that mimics step 2 of the noc pre-commit
    hook for ONE of its three targets: rewrite `KNOWLEDGE-BASE/CONTEXT/
    02-LANDSCAPE.md` (append a line, simulating a changed auto-derived count
    block) and `git add` it — on EVERY commit, exactly like the real hook's
    "auto-staged (machine count-refresh of a clean file)" leg does when the
    file was clean beforehand."""
    hook = pathlib.Path(repo, ".git", "hooks", "pre-commit")
    hook.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "echo '<!-- count refreshed -->' >> KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md\n"
        "git add -- KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md\n"
    )
    hook.chmod(0o755)


@pytest.fixture()
def stale_primary_with_kb_counts_hook_that_stages_mid_commit():
    """Take-3 incident shape: origin/dev has advanced (rebase genuinely
    required), the primary tree starts CLEAN, and a REAL pre-commit hook
    regenerates + stages `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` (a
    kb_sync-owned marker-block target, NOT one of the four ndjson ledgers)
    DURING the commit this helper makes."""
    tmp = tempfile.mkdtemp(prefix="noc-divloop3-")
    origin = os.path.join(tmp, "origin.git")
    primary = os.path.join(tmp, "primary")
    peer = os.path.join(tmp, "peer")

    _git("init", "--bare", "-b", "dev", origin)
    _git("clone", origin, primary)
    _identity(primary)
    pathlib.Path(primary, "project-history").mkdir(parents=True)
    pathlib.Path(primary, "KNOWLEDGE-BASE", "CONTEXT").mkdir(parents=True)
    pathlib.Path(primary, LEDGER).write_text('{"row": 0}\n')
    pathlib.Path(primary, "KNOWLEDGE-BASE", "CONTEXT", "02-LANDSCAPE.md").write_text(
        "# Landscape\n<!-- kb-counts:start:inventory -->\nstub\n<!-- kb-counts:end:inventory -->\n")
    pathlib.Path(primary, ".gitattributes").write_text(
        "project-history/*.ndjson merge=union\n")
    _git("add", "-A", cwd=primary)
    _git("commit", "-m", "base", cwd=primary)
    _git("push", "origin", "HEAD:dev", cwd=primary)
    _install_kb_counts_regen_hook(primary)

    # A peer advances origin/dev — the primary's local dev is now behind.
    _git("clone", origin, peer)
    _identity(peer)
    pathlib.Path(peer, "PEER.md").write_text("peer work\n")
    _git("add", "-A", cwd=peer)
    _git("commit", "-m", "peer advances dev", cwd=peer)
    _git("push", "origin", "HEAD:dev", cwd=peer)

    # A new ledger row to deliver. The tree is otherwise CLEAN — the hook is
    # the only source of the second file, not pre-existing dirt.
    pathlib.Path(primary, LEDGER).write_text(
        '{"row": 0}\n{"row": 1, "recovery": "pointer"}\n')
    yield origin, primary


def test_kb_counts_regen_rider_no_longer_strands_the_commit(
    stale_primary_with_kb_counts_hook_that_stages_mid_commit,
):
    """THE FIX, end to end with real git, for the THIRD reason the loop
    recurred: a hook that regenerates + stages a kb_sync-owned marker-block
    doc (not one of the four ndjson ledgers already covered by take 2) must
    not strand the ledger commit — the row lands on origin/dev, and the
    primary ends up level with it."""
    origin, primary = stale_primary_with_kb_counts_hook_that_stages_mid_commit
    landscape_rel = "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md"

    res = commit_and_ff_push_ledger(
        runner=_runner_for(primary), root=primary, rel_paths=[LEDGER],
        commit_msg="chore(branch-pointer): record recovery pointer",
        already_committed=False,
    )

    # ── control: prove the commit is genuinely two-file (the mechanism) ──
    _rc, tip, _ = _git("rev-parse", "HEAD", cwd=primary)
    _rc, changed_out, _ = _git(
        "diff-tree", "--no-commit-id", "--name-only", "-r", tip.strip(), cwd=primary)
    changed = [f for f in changed_out.splitlines() if f.strip()]
    assert LEDGER in changed and landscape_rel in changed, (
        f"expected the kb-counts hook's rider to ride into the SAME commit: {changed!r}")

    # CONTROL: the pre-fix predicate, run against this SAME real commit,
    # would have blocked it — proving the bug is real, not merely theorized.
    assert _old_divergence_guard_would_block(changed, {LEDGER}) is True, (
        "control failed: the pre-fix predicate should flag this commit as "
        "non-ledger (that IS the bug being fixed)")

    # THE FIX: the actual helper call above must still have succeeded, closing
    # the gap that a hand-copied BENIGN_REFRESH_PATTERNS list left open.
    assert res.get("pushed") is True, (
        f"row not pushed despite a kb-counts-regen rider: {res!r}")
    assert res.get("status") == "pushed"

    _rc, out, _ = _git("show", f"dev:{LEDGER}", cwd=origin)
    assert "recovery" in out, "the ledger row never reached origin/dev"

    _git("fetch", "origin", cwd=primary)
    _rc, counts, _ = _git("rev-list", "--left-right", "--count",
                          "origin/dev...HEAD", cwd=primary)
    assert counts.strip() == "0\t0", (
        f"primary is diverged from origin/dev ({counts.strip()!r}) — the "
        "self-latching loop the fix exists to close")
