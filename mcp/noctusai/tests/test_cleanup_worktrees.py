"""Tests for the noctus.dev.cleanup_stale_worktrees tool.

Behaviour parity with scripts/cleanup-stale-worktrees.sh: merged-branch
worktrees are stale; unmerged are active (kept); uncommitted work routes to
`dirty` (force does NOT override); dry-run unless force=True.

Builds real git repos + real `git worktree add` so the merge/ancestry/
patch-id/dirty predicates exercise the real git plumbing (no monkey-patch
of our own code — the no-workarounds rule).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.cleanup_worktrees import cleanup_stale_worktrees


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True,
        capture_output=True, text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo with `dev`, an `origin/dev` ref, and a .claude/worktrees dir.

    Engineer worktrees integrate to the `dev` integration branch, so the
    tool keys staleness off `origin/dev` (KB § branching-and-merging § 0).
    `origin/dev` is faked as a local ref so the tool's base-resolution
    (`origin/dev` then fallback `dev`) resolves deterministically.

    Commits an EMPTY `project-history/branch-tree.ndjson` into the base
    commit. Without this, `pointer_status_for_branch`'s
    `git show origin/dev:project-history/branch-tree.ndjson` fails (the
    path never existed in this fake repo's history) and
    `branch_pointer._read_dev_ledger` falls back to the REAL production
    ledger at the module-level `LEDGER_PATH` (derived from the real
    `settings.REPO_ROOT`, not this fixture's `tmp_path`) — a genuine test-
    isolation hazard the pointer-guard tests below must never depend on.
    An always-present (even if empty) ledger blob makes `git show` succeed
    every time, so the fallback path is never reached from this fixture.
    """
    r = tmp_path / "noc"
    r.mkdir()
    _git(r, "init", "-q", "-b", "dev")
    _git(r, "config", "user.email", "t@t.t")
    _git(r, "config", "user.name", "t")
    (r / "f").write_text("base\n")
    (r / "project-history").mkdir(parents=True)
    (r / "project-history" / "branch-tree.ndjson").write_text("")
    _git(r, "add", "f", "project-history/branch-tree.ndjson")
    _git(r, "commit", "-qm", "base")
    # Fake origin/dev pointing at current dev tip.
    _git(r, "update-ref", "refs/remotes/origin/dev", "HEAD")
    (r / ".claude" / "worktrees").mkdir(parents=True)
    return r


def _add_worktree(
    repo: Path, name: str, branch: str, *, publish_shipped_pointer: bool = True,
) -> Path:
    """Register a worktree. By default ALSO publishes a terminal `shipped`
    pointer for its branch (2026-09-17: `pointer_blocks_removal` now fails
    CLOSED on an unpublished/unknown pointer, so every test exercising a
    DIFFERENT predicate — merge/dirty/age/mtime — needs its branch to carry
    a resolvable terminal status or it would incidentally get POINTER_BLOCKED
    instead of reaching the predicate under test). Tests that want to
    exercise the pointer guard itself publish their own status afterwards
    (later-appended row wins by ts tie-break) or pass
    `publish_shipped_pointer=False` to test the genuinely-unknown case."""
    wt = repo / ".claude" / "worktrees" / name
    _git(repo, "worktree", "add", "-q", "-b", branch, str(wt))
    if publish_shipped_pointer:
        _publish_pointer_row(repo, branch=branch, status="shipped")
    return wt


def _publish_pointer_row(repo: Path, *, branch: str, status: str) -> None:
    """Append a branch-tree pointer row for `branch` to the ndjson and move
    `origin/dev` to the new commit, so `pointer_status_for_branch` sees it
    via `git show origin/dev:project-history/branch-tree.ndjson`."""
    import json as _json

    ledger = repo / "project-history" / "branch-tree.ndjson"
    row = _json.dumps({
        "branch": branch, "status": status,
        "ts": "2026-09-16T19:05:00+00:00",
    })
    with ledger.open("a") as fh:
        fh.write(row + "\n")
    _git(repo, "add", "project-history/branch-tree.ndjson")
    _git(repo, "commit", "-qm", f"pointer: {branch} {status}")
    _git(repo, "update-ref", "refs/remotes/origin/dev", "HEAD")


class TestDryRunDefault:
    def test_no_worktree_dir_status_nothing(self, tmp_path):
        r = tmp_path / "empty"
        r.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(r), check=True)
        result = cleanup_stale_worktrees(repo_root=r)
        assert result["status"] == "nothing"
        assert result["stale"] == []
        assert result["dry_run"] is True

    def test_merged_worktree_is_stale_but_dry_run_keeps_it(self, repo):
        # Branch with NO new commits beyond dev → merge-base ancestor → merged.
        # min_age_minutes=0 + recent_mtime_minutes=0: this test is about the
        # MERGE predicate, not the (separately tested) age/mtime guards — a
        # freshly-created worktree is otherwise always "too young" AND
        # "recently active" under the real defaults.
        wt = _add_worktree(repo, "agent-merged", "wt-merged")
        result = cleanup_stale_worktrees(
            repo_root=repo, min_age_minutes=0, recent_mtime_minutes=0,
        )  # force defaults False
        assert str(wt) in result["stale"]
        assert result["dry_run"] is True
        assert result["status"] == "dry_run"
        assert result["removed"] == 0
        assert wt.exists(), "dry-run must NOT remove the worktree"

    def test_non_agent_named_worktree_is_stale(self, repo):
        # Regression (2026-05-25): self-branch worktrees from a raw
        # `git worktree add` or `task_branch` feat/<slug> are NOT named
        # `agent-*`, so the old `agent-` path filter skipped them entirely —
        # un-sweepable, the bare-`git worktree remove` hazard. They must now
        # sweep like any other; the merged + clean gates are the real safety.
        wt = _add_worktree(repo, "my-task", "feat/my-task")
        result = cleanup_stale_worktrees(
            repo_root=repo, min_age_minutes=0, recent_mtime_minutes=0,
        )
        assert str(wt) in result["stale"], "merged non-agent worktree must be stale"
        assert wt.exists(), "dry-run must NOT remove it"


class TestMergePredicate:
    def test_unmerged_branch_is_active_kept(self, repo):
        wt = _add_worktree(repo, "agent-wip", "wt-wip")
        # Add an unmerged commit on the worktree's branch.
        (wt / "g").write_text("new\n")
        _git(wt, "add", "g")
        _git(wt, "commit", "-qm", "feat: unmerged work")
        result = cleanup_stale_worktrees(repo_root=repo, force=True)
        assert str(wt) in result["active"]
        assert str(wt) not in result["stale"]
        assert wt.exists(), "unmerged WIP worktree must be kept"

    def test_cherry_picked_branch_detected_as_merged(self, repo):
        wt = _add_worktree(repo, "agent-cp", "wt-cp")
        (wt / "h").write_text("cp\n")
        _git(wt, "add", "h")
        _git(wt, "commit", "-qm", "feat: work to be cherry-picked")
        # Cherry-pick that commit onto dev (new SHA, same patch-id), then
        # bump the fake origin/dev ref.
        sha = _git(wt, "rev-parse", "HEAD").strip()
        _git(repo, "cherry-pick", sha)
        _git(repo, "update-ref", "refs/remotes/origin/dev", "HEAD")
        # min_age_minutes=0 + recent_mtime_minutes=0: isolates the patch-id
        # predicate from the age/mtime guards (this worktree was just
        # created in this test run).
        result = cleanup_stale_worktrees(
            repo_root=repo, min_age_minutes=0, recent_mtime_minutes=0,
        )
        assert str(wt) in result["stale"], (
            "cherry-picked-to-dev branch must classify as stale (patch-id)"
        )


class TestMergedIntoBaseFallback:
    """2026-09-20 — the second, positive liveness signal that closes the
    6.4 GB ledger-less-immortal-branch gap: 36 of 37 blocked worktrees
    carried NO branch-tree pointer at all, yet were fully merged into
    origin/dev by true SHA ancestry (verified by hand). Consulted ONLY
    when `pointer_status_for_branch` resolves nothing at all — never when a
    LIVE non-terminal pointer exists."""

    def test_true_ancestor_diverged_no_pointer_is_removed_via_merged_into_base(
        self, repo,
    ):
        wt = _add_worktree(
            repo, "agent-ancestor", "wt-ancestor",
            publish_shipped_pointer=False,
        )
        (wt / "i.txt").write_text("real work\n")
        _git(wt, "add", "i.txt")
        _git(wt, "commit", "-qm", "feat: real work landed via ff, not cherry")
        sha = _git(wt, "rev-parse", "HEAD").strip()
        # The REAL `task_branch action=integrate` shape: fast-forward-PUSH
        # the branch's own commit onto dev (true SHA ancestry), not a
        # cherry-pick.
        _git(repo, "merge", "--ff-only", sha)
        # Advance dev one more commit past it so branch-tip != base-tip —
        # the documented divergence requirement (see
        # merged_into_base_confirms_dead's docstring for the narrow window
        # this excludes on purpose).
        (repo / "j.txt").write_text("later unrelated work\n")
        _git(repo, "add", "j.txt")
        _git(repo, "commit", "-qm", "chore: later work landed after wt-ancestor")
        _git(repo, "update-ref", "refs/remotes/origin/dev", "HEAD")
        # No pointer was EVER published for wt-ancestor.
        result = cleanup_stale_worktrees(
            repo_root=repo, force=True, min_age_minutes=0,
            recent_mtime_minutes=0,
        )
        assert str(wt) not in [p["path"] for p in result["pointer_blocked"]]
        assert str(wt) in result["stale"]
        assert result["stale_signals"][str(wt)] == "merged_into_base"
        assert not wt.exists(), (
            "confirmed-dead via merged_into_base must actually be removed"
        )

    def test_dry_run_reports_the_signal_without_removing(self, repo):
        wt = _add_worktree(
            repo, "agent-ancestor-dry", "wt-ancestor-dry",
            publish_shipped_pointer=False,
        )
        (wt / "i2.txt").write_text("real work\n")
        _git(wt, "add", "i2.txt")
        _git(wt, "commit", "-qm", "feat: real work")
        sha = _git(wt, "rev-parse", "HEAD").strip()
        _git(repo, "merge", "--ff-only", sha)
        (repo / "j2.txt").write_text("later\n")
        _git(repo, "add", "j2.txt")
        _git(repo, "commit", "-qm", "chore: later")
        _git(repo, "update-ref", "refs/remotes/origin/dev", "HEAD")
        result = cleanup_stale_worktrees(
            repo_root=repo, min_age_minutes=0, recent_mtime_minutes=0,
        )
        assert result["dry_run"] is True
        assert str(wt) in result["stale"]
        assert result["stale_signals"][str(wt)] == "merged_into_base"
        assert wt.exists(), "dry-run must never remove"

    def test_cherry_picked_landing_with_no_pointer_is_NOT_authorized(self, repo):
        # is_merged() (the FIRST gate, checked before ever reaching the
        # pointer step) accepts patch-id/cherry-pick equivalence — a
        # weaker automated signal. merged_into_base_confirms_dead is
        # deliberately STRICTER (true SHA ancestry only) and must refuse
        # here, absent a ledger pointer.
        wt = _add_worktree(
            repo, "agent-cp-nopointer", "wt-cp-np",
            publish_shipped_pointer=False,
        )
        (wt / "m.txt").write_text("cherry-picked work\n")
        _git(wt, "add", "m.txt")
        _git(wt, "commit", "-qm", "feat: will be cherry-picked, not ff-merged")
        sha = _git(wt, "rev-parse", "HEAD").strip()
        _git(repo, "cherry-pick", sha)
        _git(repo, "update-ref", "refs/remotes/origin/dev", "HEAD")
        result = cleanup_stale_worktrees(
            repo_root=repo, force=True, min_age_minutes=0,
            recent_mtime_minutes=0,
        )
        assert str(wt) not in result["stale"]
        blocked = next(
            p for p in result["pointer_blocked"] if p["path"] == str(wt)
        )
        assert blocked["status"] is None
        assert wt.exists(), (
            "patch-id-only equivalence must NOT authorize removal via the "
            "stricter merged_into_base fallback"
        )

    def test_dirty_worktree_with_no_pointer_still_routes_to_dirty(self, repo):
        wt = _add_worktree(
            repo, "agent-dirty-nopointer", "wt-dirty-np",
            publish_shipped_pointer=False,
        )
        (wt / "n.txt").write_text("uncommitted\n")
        result = cleanup_stale_worktrees(
            repo_root=repo, force=True, min_age_minutes=0,
            recent_mtime_minutes=0,
        )
        dirty_paths = [d["path"] for d in result["dirty"]]
        assert str(wt) in dirty_paths
        assert str(wt) not in result["stale"]
        assert wt.exists(), (
            "a dirty worktree must never reach the merged_into_base "
            "fallback at all — the dirty gate runs first"
        )

    def test_unmerged_branch_with_no_pointer_stays_active_not_authorized(
        self, repo,
    ):
        wt = _add_worktree(
            repo, "agent-unmerged-nopointer", "wt-unmerged-np",
            publish_shipped_pointer=False,
        )
        (wt / "o.txt").write_text("still in progress\n")
        _git(wt, "add", "o.txt")
        _git(wt, "commit", "-qm", "feat: not yet landed anywhere")
        result = cleanup_stale_worktrees(repo_root=repo, force=True)
        assert str(wt) in result["active"]
        assert str(wt) not in result["stale"]
        assert wt.exists()


class TestSafetyGates:
    def test_dirty_worktree_routes_to_dirty_not_stale(self, repo):
        wt = _add_worktree(repo, "agent-dirty", "wt-dirty")
        # Branch is merged (no new commits) BUT has uncommitted work.
        (wt / "uncommitted.txt").write_text("dirty\n")
        result = cleanup_stale_worktrees(repo_root=repo, force=True)
        dirty_paths = [d["path"] for d in result["dirty"]]
        assert str(wt) in dirty_paths
        assert str(wt) not in result["stale"]
        assert wt.exists(), "force must NOT remove a dirty merged worktree"

    def test_force_removes_clean_merged_worktree(self, repo):
        wt = _add_worktree(repo, "agent-clean", "wt-clean")
        assert wt.exists()
        # recent_mtime_minutes=0: isolates force-removal from the mtime
        # guard (never force-bypassable) — this test is about force
        # overriding the age guard, tested separately below.
        result = cleanup_stale_worktrees(
            repo_root=repo, force=True, recent_mtime_minutes=0,
        )
        assert result["status"] == "removed"
        assert result["removed"] >= 1
        assert not wt.exists(), "force=True must remove a clean merged worktree"

    def test_main_repo_never_classified(self, repo):
        _add_worktree(repo, "agent-clean2", "wt-clean2")
        result = cleanup_stale_worktrees(repo_root=repo, force=True)
        assert str(repo) not in result["stale"]
        assert str(repo) not in result["active"]
        assert str(repo) == result["main"]

    def test_non_agent_sibling_dir_never_stale(self, repo):
        # A non-agent dir under worktrees/ must be ignored entirely.
        sibling = repo / ".claude" / "worktrees" / "sibling-workspace"
        sibling.mkdir()
        (sibling / "x").write_text("y")
        result = cleanup_stale_worktrees(repo_root=repo, force=True)
        assert str(sibling) not in result["stale"]


class TestOrphanDetection:
    def test_orphan_agent_dir_classified_stale(self, repo):
        # On-disk agent-* dir that git doesn't know about → orphan → stale.
        orphan = repo / ".claude" / "worktrees" / "agent-orphan"
        orphan.mkdir()
        (orphan / "leftover").write_text("junk")
        result = cleanup_stale_worktrees(repo_root=repo)
        assert str(orphan) in result["stale"]


class TestMcpRegistration:
    def test_register_callable(self):
        from tools.noctus.dev.cleanup_worktrees import register
        assert callable(register)

    def test_register_wires_tool_onto_a_server(self):
        """The module's own register() wires the tool. (Global build_server()
        wiring lands when the architect adds cleanup_worktrees to
        tools/noctus/dev/__init__.py per the integration recipe.)"""
        from mcp.server.fastmcp import FastMCP

        from tools.noctus.dev.cleanup_worktrees import register
        s = FastMCP(name="t")
        register(s)
        assert "noctus.dev.cleanup_stale_worktrees" in s._tool_manager._tools


# ═══════════ 2026-09-16 incident: the two false-positive-removal guards ═════
# `community-m1-backend` / `community-m1-frontend` were ~6 minutes old, 0
# commits ahead of origin/dev (trivially "merged"), and were removed by
# `force=True` while two engineers were actively working in them. These
# classes pin the fix at the tool level (see test_worktree_staleness.py for
# the underlying predicate-level tests).
class TestLivePointerGuard:
    def test_on_going_pointer_blocks_even_though_merged_and_clean(self, repo):
        wt = _add_worktree(repo, "agent-live", "feat/live")
        _publish_pointer_row(repo, branch="feat/live", status="on_going")
        result = cleanup_stale_worktrees(repo_root=repo, min_age_minutes=0)
        assert str(wt) not in result["stale"]
        blocked_paths = [p["path"] for p in result["pointer_blocked"]]
        assert str(wt) in blocked_paths
        assert wt.exists()

    def test_force_does_not_bypass_the_pointer_guard(self, repo):
        wt = _add_worktree(repo, "agent-live2", "feat/live2")
        _publish_pointer_row(repo, branch="feat/live2", status="on_going")
        result = cleanup_stale_worktrees(
            repo_root=repo, force=True, min_age_minutes=0,
        )
        assert str(wt) not in result["stale"]
        blocked_paths = [p["path"] for p in result["pointer_blocked"]]
        assert str(wt) in blocked_paths
        assert wt.exists(), "force=True must NEVER remove a live-pointer worktree"

    def test_shipped_pointer_does_not_block(self, repo):
        wt = _add_worktree(repo, "agent-done", "feat/done")
        _publish_pointer_row(repo, branch="feat/done", status="shipped")
        result = cleanup_stale_worktrees(
            repo_root=repo, min_age_minutes=0, recent_mtime_minutes=0,
        )
        assert str(wt) in result["stale"]
        assert result["pointer_blocked"] == []

    def test_reason_names_the_status(self, repo):
        wt = _add_worktree(repo, "agent-blocked-reason", "feat/blocked-reason")
        _publish_pointer_row(
            repo, branch="feat/blocked-reason", status="blocked",
        )
        result = cleanup_stale_worktrees(repo_root=repo, min_age_minutes=0)
        row = next(p for p in result["pointer_blocked"] if p["path"] == str(wt))
        assert row["status"] == "blocked"
        assert "blocked" in row["reason"]


class TestMinAgeGuardTool:
    def test_fresh_worktree_is_too_young_by_default_not_stale(self, repo):
        # Uses the REAL DEFAULT min_age_minutes (60) — a worktree created
        # microseconds ago in this test run is nowhere near it.
        # recent_mtime_minutes=0 isolates the age guard from the (separately
        # tested) mtime guard, which would otherwise also fire here.
        wt = _add_worktree(repo, "agent-fresh", "feat/fresh")
        result = cleanup_stale_worktrees(
            repo_root=repo, recent_mtime_minutes=0,
        )  # force=False
        assert str(wt) not in result["stale"]
        young_paths = [p["path"] for p in result["too_young"]]
        assert str(wt) in young_paths
        assert wt.exists()

    def test_force_bypasses_the_age_guard_but_not_when_pointer_blocks(self, repo):
        # recent_mtime_minutes=0: force MAY bypass age but never mtime — this
        # test is isolated to the age guard (the mtime-never-bypassed case is
        # covered separately in TestRecentMtimeGuardTool).
        wt = _add_worktree(repo, "agent-fresh-force", "feat/fresh-force")
        result = cleanup_stale_worktrees(
            repo_root=repo, force=True, recent_mtime_minutes=0,
        )
        assert result["status"] == "removed"
        assert not wt.exists(), (
            "force=True MAY override the age guard (never the pointer guard)"
        )

    def test_min_age_zero_admits_a_fresh_worktree_to_stale(self, repo):
        wt = _add_worktree(repo, "agent-fresh-zero", "feat/fresh-zero")
        result = cleanup_stale_worktrees(
            repo_root=repo, min_age_minutes=0, recent_mtime_minutes=0,
        )
        assert str(wt) in result["stale"]
        assert result["too_young"] == []

    def test_skip_reason_names_the_thresholds(self, repo):
        wt = _add_worktree(repo, "agent-young-reason", "feat/young-reason")
        result = cleanup_stale_worktrees(
            repo_root=repo, min_age_minutes=45, recent_mtime_minutes=0,
        )
        row = next(p for p in result["too_young"] if p["path"] == str(wt))
        assert row["min_age_seconds"] == 45 * 60.0
        assert row["age_seconds"] is not None
        assert "45" in row["reason"]


class TestRecentMtimeGuardTool:
    """2026-09-17 incident fix (Leg 2): a recently-touched tracked file
    blocks removal INDEPENDENT of the pointer/age guards, and is NEVER
    bypassed by force=True."""

    def test_fresh_worktree_is_recently_active_by_default(self, repo):
        # Uses the REAL DEFAULT recent_mtime_minutes (60) — files checked
        # out by `git worktree add` moments ago are nowhere near stale.
        wt = _add_worktree(repo, "agent-recent", "feat/recent")
        result = cleanup_stale_worktrees(repo_root=repo, min_age_minutes=0)
        assert str(wt) not in result["stale"]
        active_paths = [p["path"] for p in result["recently_active"]]
        assert str(wt) in active_paths
        assert wt.exists()

    def test_force_does_not_bypass_the_mtime_guard(self, repo):
        wt = _add_worktree(repo, "agent-recent-force", "feat/recent-force")
        result = cleanup_stale_worktrees(
            repo_root=repo, force=True, min_age_minutes=0,
        )
        assert str(wt) not in result["stale"]
        active_paths = [p["path"] for p in result["recently_active"]]
        assert str(wt) in active_paths
        assert wt.exists(), (
            "force=True must NEVER remove a recently-touched worktree"
        )

    def test_recent_mtime_zero_admits_a_worktree_to_stale(self, repo):
        wt = _add_worktree(repo, "agent-recent-zero", "feat/recent-zero")
        result = cleanup_stale_worktrees(
            repo_root=repo, min_age_minutes=0, recent_mtime_minutes=0,
        )
        assert str(wt) in result["stale"]
        assert result["recently_active"] == []

    def test_skip_reason_names_the_window(self, repo):
        wt = _add_worktree(repo, "agent-recent-reason", "feat/recent-reason")
        result = cleanup_stale_worktrees(
            repo_root=repo, min_age_minutes=0, recent_mtime_minutes=45,
        )
        row = next(p for p in result["recently_active"] if p["path"] == str(wt))
        assert row["window_seconds"] == 45 * 60.0
        assert row["age_seconds"] is not None
        assert "45" in row["reason"]

    def test_pointer_guard_wins_over_mtime_when_both_apply(self, repo):
        # Pointer guard runs first — a live pointer is reported as
        # pointer_blocked, never recently_active, even though the worktree
        # is ALSO freshly touched.
        wt = _add_worktree(repo, "agent-both", "feat/both")
        _publish_pointer_row(repo, branch="feat/both", status="on_going")
        result = cleanup_stale_worktrees(repo_root=repo, min_age_minutes=0)
        assert str(wt) not in result["stale"]
        assert str(wt) not in [p["path"] for p in result["recently_active"]]
        assert str(wt) in [p["path"] for p in result["pointer_blocked"]]


# ═══════════ 2026-09-17 incident: unknown-pointer fail-closed + the actual
# incident shape (terminal pointer + existing dir + recent mtime) ═══════════
class TestUnknownPointerFailsClosed:
    def test_no_pointer_at_all_blocks_removal(self, repo):
        # No `_add_worktree` auto-publish here — the genuinely unknown case.
        wt = _add_worktree(
            repo, "agent-unknown", "feat/unknown",
            publish_shipped_pointer=False,
        )
        result = cleanup_stale_worktrees(
            repo_root=repo, min_age_minutes=0, recent_mtime_minutes=0,
        )
        assert str(wt) not in result["stale"]
        blocked = next(p for p in result["pointer_blocked"] if p["path"] == str(wt))
        assert blocked["status"] is None
        assert wt.exists()

    def test_force_does_not_bypass_the_unknown_pointer_guard(self, repo):
        wt = _add_worktree(
            repo, "agent-unknown-force", "feat/unknown-force",
            publish_shipped_pointer=False,
        )
        result = cleanup_stale_worktrees(
            repo_root=repo, force=True, min_age_minutes=0,
            recent_mtime_minutes=0,
        )
        assert str(wt) not in result["stale"]
        assert wt.exists(), (
            "force=True must NEVER remove a worktree with unresolvable "
            "pointer liveness"
        )


class TestActualIncidentShape:
    """Reproduces the 2026-09-16→17 incident exactly: a branch already
    flipped to a TERMINAL pointer status by auto-heal, its worktree
    directory STILL on disk, and files touched moments ago. Must be refused
    — this is precisely the scenario the old code waved through."""

    def test_terminal_pointer_plus_existing_dir_plus_recent_mtime_is_refused(
        self, repo,
    ):
        wt = _add_worktree(repo, "agent-incident", "feat/incident")
        # `_add_worktree` already publishes `shipped` (the terminal status a
        # buggy auto-heal would have written) — the worktree directory is
        # still on disk (as-created) and its files were touched moments ago.
        # Under the pre-fix code this would have classified STALE.
        result = cleanup_stale_worktrees(repo_root=repo, force=True)
        assert str(wt) not in result["stale"]
        assert wt.exists(), (
            "terminal pointer + live directory + recent mtime must be "
            "refused even with force=True — this is the exact incident shape"
        )
        active_paths = [p["path"] for p in result["recently_active"]]
        assert str(wt) in active_paths


class TestGuardResultShape:
    def test_both_guard_keys_present_even_with_nothing_to_report(self, repo):
        result = cleanup_stale_worktrees(repo_root=repo)
        assert result["pointer_blocked"] == []
        assert result["recently_active"] == []
        assert result["too_young"] == []

    def test_both_guard_keys_present_in_the_no_worktree_dir_shape(self, tmp_path):
        r = tmp_path / "empty"
        r.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(r), check=True)
        result = cleanup_stale_worktrees(repo_root=r)
        assert result["pointer_blocked"] == []
        assert result["recently_active"] == []
        assert result["too_young"] == []
