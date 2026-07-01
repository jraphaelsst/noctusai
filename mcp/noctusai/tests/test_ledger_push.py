"""Tests for the shared ledger FF-push helper (noctus.dev._ledger_push).

`commit_and_ff_push_ledger` is the N=3 DRY lift of the "commit a
project-history/*.ndjson ledger row on the primary dev checkout, then fetch →
divergence-guard → rebase-onto-origin/dev → FF-push (best-effort, one retry on
the concurrent-push race)" idiom shared by branch_pointer + task_branch.

Covered:
  - path-scoped commit + push (already_committed=False): status/add/commit are
    issued path-scoped to rel_paths, then the push leg runs.
  - already_committed=True: NO status/add/commit — straight to fetch→guard→
    rebase→push of the existing HEAD.
  - stale-primary rebase: local dev behind origin/dev → first push non-FF, a
    `git rebase origin/dev` is issued, the retry push succeeds.
  - non-ledger-commit guard: an ahead-commit touching a non-ledger file → REFUSE
    (no push, committed_locally=True, error names the offending sha).
  - rebase conflict: `git rebase --abort` issued, committed_locally=True, and NO
    force/`-X` token EVER appears in any issued command.
  - concurrent-push single-retry: exactly two push calls.
  - already_clean idempotency + add/commit failure + missing-file guard.
  - command shape: root=None → `git …`; root=<r> → `git -C <r> …`; push targets
    HEAD:<dev>.

Zero real git — an injected fake runner scripts all git IO.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.noctus.dev._ledger_push as LP  # noqa: E402


# ── Fake runner ────────────────────────────────────────────────────────────────
def _sub(cmd: list[str]) -> str:
    """The git subcommand, tolerant of an optional `-C <root>` prefix."""
    i = 3 if len(cmd) > 2 and cmd[1] == "-C" else 1
    return cmd[i] if len(cmd) > i else ""


class FakeRunner:
    """Scriptable git runner recording every command.

    status_dirty : ledger appears modified in `git status --porcelain`.
    push_rcs     : per-attempt push return codes (default all-0).
    ahead        : shas returned by `git rev-list origin/dev..HEAD`.
    diff_tree    : changed files returned by `git diff-tree` (per ahead-commit).
    rebase_rc    : return code for `git rebase <ref>` (0 clean, 1 conflict).
    """

    def __init__(
        self,
        *,
        status_dirty: bool = True,
        status_rc: int = 0,
        add_rc: int = 0,
        commit_rc: int = 0,
        push_rcs: list[int] | None = None,
        ahead: list[str] | None = None,
        diff_tree: str = "project-history/branch-tree.ndjson\n",
        rebase_rc: int = 0,
        ledger_rel: str = "project-history/branch-tree.ndjson",
    ):
        self.status_dirty = status_dirty
        self.status_rc = status_rc
        self.add_rc = add_rc
        self.commit_rc = commit_rc
        self.push_rcs = list(push_rcs) if push_rcs is not None else [0]
        self.ahead = ahead if ahead is not None else ["deadbeef"]
        self.diff_tree = diff_tree
        self.rebase_rc = rebase_rc
        self.ledger_rel = ledger_rel
        self.calls: list[list[str]] = []
        self._push_i = 0

    def __call__(self, cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
        self.calls.append(list(cmd))
        sub = _sub(cmd)
        if sub == "status":
            if self.status_rc != 0:
                return self.status_rc, "", "status failed"
            return 0, (f" M {self.ledger_rel}\n" if self.status_dirty else ""), ""
        if sub == "add":
            return self.add_rc, "", "" if self.add_rc == 0 else "add failed"
        if sub == "commit":
            return self.commit_rc, "", "" if self.commit_rc == 0 else "commit failed"
        if sub == "fetch":
            return 0, "", ""
        if sub == "rev-list":
            return 0, "\n".join(self.ahead) + ("\n" if self.ahead else ""), ""
        if sub == "diff-tree":
            return 0, self.diff_tree, ""
        if sub == "rebase":
            if "--abort" in cmd:
                return 0, "", ""
            return self.rebase_rc, "", ("" if self.rebase_rc == 0 else "CONFLICT (content)")
        if sub == "push":
            rc = self.push_rcs[min(self._push_i, len(self.push_rcs) - 1)]
            self._push_i += 1
            return rc, "", ("" if rc == 0 else "non-fast-forward")
        return 0, "", ""

    # ── assertion helpers ──
    def subs(self) -> list[str]:
        return [_sub(c) for c in self.calls]

    def pushes(self) -> list[list[str]]:
        return [c for c in self.calls if _sub(c) == "push"]


# ── path-scoped commit + push (already_committed=False) ────────────────────────
class TestPathScopedCommit:
    def test_happy_path_commits_then_pushes(self):
        r = FakeRunner(status_dirty=True, push_rcs=[0])
        res = LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"],
            commit_msg="chore: x", already_committed=False,
        )
        assert res == {"ok": True, "status": "pushed", "pushed": True}
        # status → add → commit → fetch → rev-list → diff-tree → rebase → push
        subs = r.subs()
        assert subs[:3] == ["status", "add", "commit"]
        assert "push" in subs and "rebase" in subs

    def test_already_clean_short_circuits(self):
        r = FakeRunner(status_dirty=False)
        res = LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"],
            commit_msg="chore: x",
        )
        assert res == {"ok": True, "status": "already_clean", "pushed": False}
        assert "commit" not in r.subs() and "push" not in r.subs()

    def test_add_failure_surfaced_no_push(self):
        r = FakeRunner(status_dirty=True, add_rc=1)
        res = LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"], commit_msg="m",
        )
        assert res["ok"] is False and "add failed" in res["error"]
        assert not r.pushes()

    def test_commit_failure_surfaced_no_push(self):
        r = FakeRunner(status_dirty=True, commit_rc=1)
        res = LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"], commit_msg="m",
        )
        assert res["ok"] is False and "commit failed" in res["error"]
        assert not r.pushes()

    def test_missing_file_guard(self, tmp_path):
        missing = tmp_path / "project-history" / "nope.ndjson"
        r = FakeRunner()
        res = LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/nope.ndjson"], commit_msg="m",
            check_exists=missing,
        )
        assert res["ok"] is False and "does not exist" in res["error"]
        assert r.calls == []  # short-circuits before any git IO

    def test_commit_msg_required_when_not_already_committed(self):
        r = FakeRunner(status_dirty=True)
        res = LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"], commit_msg=None,
        )
        assert res["ok"] is False and "commit_msg is required" in res["error"]

    def test_add_is_path_scoped_to_rel_paths(self):
        r = FakeRunner(status_dirty=True, ledger_rel="project-history/worktree-salvage.ndjson")
        LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/worktree-salvage.ndjson"],
            commit_msg="m", root="/repo",
        )
        # both the add and the commit name ONLY the ledger path (never a bare `git add -A`)
        add = next(c for c in r.calls if _sub(c) == "add")
        assert add[-1] == "project-history/worktree-salvage.ndjson"
        commit = next(c for c in r.calls if _sub(c) == "commit")
        assert commit[-1] == "project-history/worktree-salvage.ndjson"


# ── already_committed=True (push an existing HEAD) ─────────────────────────────
class TestAlreadyCommitted:
    def test_skips_commit_leg(self):
        r = FakeRunner(push_rcs=[0])
        res = LP.commit_and_ff_push_ledger(
            runner=r,
            rel_paths=[
                "project-history/branch-tree.ndjson",
                "project-history/branch-tree.mirror.ndjson",
            ],
            already_committed=True,
        )
        assert res == {"ok": True, "status": "pushed", "pushed": True}
        subs = r.subs()
        assert "status" not in subs and "add" not in subs and "commit" not in subs
        assert subs[0] == "fetch"  # straight to the push leg


# ── stale-primary rebase path ──────────────────────────────────────────────────
class TestStalePrimaryRebase:
    def test_rebase_issued_then_retry_push_succeeds(self):
        # local dev behind origin/dev → first push non-FF, retry succeeds.
        r = FakeRunner(status_dirty=True, push_rcs=[1, 0], ahead=["deadbeef"])
        res = LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"], commit_msg="m",
        )
        assert res == {"ok": True, "status": "pushed", "pushed": True}
        rebases = [c for c in r.calls if _sub(c) == "rebase" and "--abort" not in c]
        assert rebases, "a `git rebase origin/dev` must be issued before the push"
        assert len(r.pushes()) == 2


# ── non-ledger-commit guard ─────────────────────────────────────────────────────
class TestDivergenceGuard:
    def test_non_ledger_ahead_refuses_no_push(self):
        r = FakeRunner(
            status_dirty=True, ahead=["feedface"],
            diff_tree="mcp/noctusai/tools/noctus/dev/other.py\n",
        )
        res = LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"], commit_msg="m",
        )
        assert res["ok"] is False
        assert res["committed_locally"] is True
        assert res["retryable"] is False
        assert "non-ledger" in res["error"]
        assert "feedface" in res["error"]  # names the offending sha
        assert not r.pushes(), "must NOT push when an ahead-commit is non-ledger"

    def test_ledger_and_mirror_ahead_is_allowed(self):
        # An ahead commit touching BOTH ledger + mirror passes the guard.
        r = FakeRunner(
            status_dirty=True, ahead=["cafe1234"], push_rcs=[0],
            diff_tree=(
                "project-history/branch-tree.ndjson\n"
                "project-history/branch-tree.mirror.ndjson\n"
            ),
        )
        res = LP.commit_and_ff_push_ledger(
            runner=r,
            rel_paths=[
                "project-history/branch-tree.ndjson",
                "project-history/branch-tree.mirror.ndjson",
            ],
            commit_msg="m",
        )
        assert res["ok"] is True and res["pushed"] is True


# ── rebase conflict → abort, no force ──────────────────────────────────────────
class TestRebaseConflict:
    def test_conflict_aborts_never_forces(self):
        r = FakeRunner(status_dirty=True, ahead=["abc12345"], rebase_rc=1)
        res = LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"], commit_msg="m",
        )
        assert res["ok"] is False
        assert res["committed_locally"] is True
        assert "conflict" in res["error"].lower()
        aborts = [c for c in r.calls if _sub(c) == "rebase" and "--abort" in c]
        assert aborts, "`git rebase --abort` must be issued on a conflict"
        assert not r.pushes(), "must NOT push when the rebase conflicts"
        # NEVER force / auto-resolve — no banned token in ANY issued command.
        for c in r.calls:
            assert "-X" not in c, f"no -X (auto-resolve) allowed: {c}"
            assert "-f" not in c, f"no -f (force) allowed: {c}"
            assert not any("--force" in tok for tok in c), f"no --force allowed: {c}"


# ── concurrent-push single-retry ────────────────────────────────────────────────
class TestConcurrentPushRetry:
    def test_retries_exactly_once(self):
        r = FakeRunner(status_dirty=True, push_rcs=[1, 0], ahead=["cafe1234"])
        res = LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"], commit_msg="m",
        )
        assert res["ok"] is True
        assert len(r.pushes()) == 2, "should retry exactly once on a concurrent-push race"

    def test_persistent_push_failure_after_retry(self):
        r = FakeRunner(status_dirty=True, push_rcs=[1, 1], ahead=["cafe1234"])
        res = LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"], commit_msg="m",
        )
        assert res["ok"] is False
        assert res["committed_locally"] is True
        assert "FF-push" in res["error"] or "failed" in res["error"]
        assert len(r.pushes()) == 2, "at most two pushes (one retry)"


# ── command shape ───────────────────────────────────────────────────────────────
class TestCommandShape:
    def test_root_none_has_no_dash_c(self):
        r = FakeRunner(status_dirty=True, push_rcs=[0])
        LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"],
            commit_msg="m", root=None,
        )
        assert all("-C" not in c for c in r.calls), "root=None must not emit `-C`"

    def test_root_set_targets_primary_checkout(self):
        r = FakeRunner(status_dirty=True, push_rcs=[0],
                       ledger_rel="project-history/worktree-salvage.ndjson")
        LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/worktree-salvage.ndjson"],
            commit_msg="m", root="/repo",
        )
        for c in r.calls:
            assert c[:3] == ["git", "-C", "/repo"], f"every call must target /repo: {c}"

    def test_push_targets_head_colon_dev(self):
        r = FakeRunner(status_dirty=True, push_rcs=[0])
        LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"],
            commit_msg="m", dev_branch="dev", remote="origin",
        )
        push = r.pushes()[0]
        assert push[-2] == "origin" and push[-1] == "HEAD:dev"

    def test_fetch_can_be_disabled(self):
        r = FakeRunner(status_dirty=True, push_rcs=[0])
        LP.commit_and_ff_push_ledger(
            runner=r, rel_paths=["project-history/branch-tree.ndjson"],
            commit_msg="m", _fetch=False,
        )
        assert "fetch" not in r.subs(), "_fetch=False must skip the git fetch"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
