"""Tests for session_end_sweep's branch-tree pointer auto-heal.

The backstop for the "flip on_going→shipped BEFORE merging" discipline: any
`on_going` branch-tree pointer whose branch is already integrated into origin/dev
is flipped to `shipped` at session close, so the global branch map never keeps
showing phantom in-flight work that mis-routes a peer's collision decision.

The real `_worktree_staleness.is_merged` / `is_ancestor` predicates run against
an INJECTED fake git runner (so the merge/ancestry logic is genuinely exercised);
`branch_pointer.query` / `update` are monkeypatched (they have their own coverage)
so no ledger is written. Zero real git, zero disk.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools.noctus.dev import session_end_sweep as SES  # noqa: E402
from tools.noctus.dev import _worktree_staleness as WTS  # noqa: E402
from tools.noctus.dev import branch_pointer as BP  # noqa: E402


class FakeRunner:
    """Scripts (rc, out, err) per git subcommand for calls shaped
    ``["git", <sub>, ...]`` (the shape `_worktree_staleness` + the auto-heal use)."""

    def __init__(self, scripts):
        self.scripts = scripts
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        sub = cmd[1] if len(cmd) > 1 else ""
        return self.scripts.get(sub, (0, "", ""))


def _wire(monkeypatch, *, runner, candidates, update_result=None):
    """Patch the auto-heal's dependencies: a fixed fake runner, a fixed
    origin/dev base, a fixed candidate set, and a recording `update`."""
    monkeypatch.setattr(WTS, "make_subprocess_runner", lambda root, **kw: runner)
    monkeypatch.setattr(WTS, "resolve_merged_base", lambda run: "origin/dev")
    monkeypatch.setattr(BP, "query", lambda **kw: list(candidates))
    updates = []

    def fake_update(**kw):
        updates.append(kw)
        return update_result if update_result is not None else {"ok": True, "row": kw}

    monkeypatch.setattr(BP, "update", fake_update)
    return updates


def test_flips_merged_existing_branch(monkeypatch):
    # branch exists (rev-parse rc0) AND is an ancestor of origin/dev (merge-base rc0).
    runner = FakeRunner({"rev-parse": (0, "sha\n", ""), "merge-base": (0, "", "")})
    updates = _wire(
        monkeypatch, runner=runner,
        candidates=[{"branch": "feat/landed", "commit": "abc123"}],
    )
    res = SES._autoheal_branch_pointers(Path("/repo"))
    assert [h["branch"] for h in res["healed"]] == ["feat/landed"]
    assert res["errors"] == []
    # flip issued as shipped, push_dev=False (delivery batches the push).
    assert len(updates) == 1
    assert updates[0]["branch"] == "feat/landed"
    assert updates[0]["status"] == "shipped"
    assert updates[0]["push_dev"] is False


def test_flips_cleaned_up_branch_with_landed_commit(monkeypatch):
    # branch gone (rev-parse rc1) BUT its recorded commit is an ancestor (merge-base rc0).
    runner = FakeRunner({"rev-parse": (1, "", "not found"), "merge-base": (0, "", "")})
    updates = _wire(
        monkeypatch, runner=runner,
        candidates=[{"branch": "feat/gone-but-landed", "commit": "deadbeef"}],
    )
    res = SES._autoheal_branch_pointers(Path("/repo"))
    assert [h["branch"] for h in res["healed"]] == ["feat/gone-but-landed"]
    assert "cleaned up" in res["healed"][0]["reason"]
    assert len(updates) == 1 and updates[0]["status"] == "shipped"


def test_skips_unmerged_existing_branch(monkeypatch):
    # branch exists, NOT an ancestor, and cherry shows a genuinely-unmerged commit.
    runner = FakeRunner({
        "rev-parse": (0, "sha\n", ""),
        "merge-base": (1, "", ""),          # not a SHA-ancestor
        "cherry": (0, "+ abc123\n", ""),    # one unmerged commit (+)
        "log": (0, "abc123 subject\n", ""),
    })
    updates = _wire(
        monkeypatch, runner=runner,
        candidates=[{"branch": "feat/in-flight", "commit": "abc123"}],
    )
    res = SES._autoheal_branch_pointers(Path("/repo"))
    assert res["healed"] == []
    assert updates == []  # genuinely in-flight → left on_going


def test_skips_gone_branch_with_unproven_commit(monkeypatch):
    # branch gone AND its commit is not reachable from origin/dev → cannot prove landed.
    runner = FakeRunner({"rev-parse": (1, "", ""), "merge-base": (1, "", "")})
    updates = _wire(
        monkeypatch, runner=runner,
        candidates=[{"branch": "feat/lost", "commit": "cafef00d"}],
    )
    res = SES._autoheal_branch_pointers(Path("/repo"))
    assert res["healed"] == []
    assert res["skipped_unproven"] == ["feat/lost"]
    assert updates == []


def test_reports_update_error_without_raising(monkeypatch):
    runner = FakeRunner({"rev-parse": (0, "sha\n", ""), "merge-base": (0, "", "")})
    _wire(
        monkeypatch, runner=runner,
        candidates=[{"branch": "feat/landed", "commit": "abc"}],
        update_result={"ok": False, "error": "push conflict"},
    )
    res = SES._autoheal_branch_pointers(Path("/repo"))
    assert res["healed"] == []
    assert any("push conflict" in e for e in res["errors"])


def test_empty_candidate_set_is_clean(monkeypatch):
    _wire(monkeypatch, runner=FakeRunner({}), candidates=[])
    res = SES._autoheal_branch_pointers(Path("/repo"))
    assert res == {"healed": [], "skipped_unproven": [], "errors": []}


# ═══════════ 2026-09-17 incident — Leg 1: ledger CLAIM vs filesystem EVIDENCE
# session_end_sweep's auto-heal used to flip an integrated branch straight to
# `shipped` without ever checking whether its `.claude/worktrees/<slug>`
# directory still existed — waving a still-checked-out worktree through as
# terminal. These tests pin the fix: the worktree directory's presence is
# looked up via `_worktree_branches` (monkeypatched here exactly like
# `test_sweep_respects_heal_pointers_false` already does), and a LIVE
# directory routes to the distinct non-terminal `integrated-worktree-live`
# status instead of `shipped`.
class TestWorktreeLivenessBeforeTerminalFlip:
    def test_flips_to_integrated_worktree_live_when_directory_still_exists(
        self, monkeypatch, tmp_path,
    ):
        live_dir = tmp_path / "ef-w8-models-worker"
        live_dir.mkdir()
        runner = FakeRunner({"rev-parse": (0, "sha\n", ""), "merge-base": (0, "", "")})
        monkeypatch.setattr(
            SES, "_worktree_branches",
            lambda root: [("ef-w8-models-worker", "feat/landed", live_dir)],
        )
        updates = _wire(
            monkeypatch, runner=runner,
            candidates=[{"branch": "feat/landed", "commit": "abc123"}],
        )
        res = SES._autoheal_branch_pointers(Path("/repo"))
        assert [h["branch"] for h in res["healed"]] == ["feat/landed"]
        assert res["errors"] == []
        assert len(updates) == 1
        assert updates[0]["branch"] == "feat/landed"
        assert updates[0]["status"] == "integrated-worktree-live"
        assert updates[0]["push_dev"] is False
        assert "still exists" in res["healed"][0]["reason"]

    def test_new_status_is_a_real_branch_pointer_status_and_non_terminal(self):
        assert "integrated-worktree-live" in BP.STATUSES
        assert "integrated-worktree-live" not in BP.TERMINAL_STATUSES

    def test_new_status_still_blocks_removal_via_pointer_blocks_removal(self):
        runner_row = (
            '{"branch": "feat/x", "status": "integrated-worktree-live", '
            '"ts": "2026-09-17T00:00:00Z"}'
        )

        def _run(cmd):
            if cmd[:2] == ["git", "show"]:
                return 0, runner_row + "\n", ""
            return 0, "", ""

        blocks, status = WTS.pointer_blocks_removal("feat/x", _run)
        assert blocks is True
        assert status == "integrated-worktree-live"

    def test_still_flips_shipped_when_directory_absent(self, monkeypatch):
        # No `_worktree_branches` monkeypatch — the real function resolves
        # `/repo/.claude/worktrees` as non-existent (fake root), returning
        # `[]`, exactly the existing (pre-fix) behaviour: preserved.
        runner = FakeRunner({"rev-parse": (0, "sha\n", ""), "merge-base": (0, "", "")})
        updates = _wire(
            monkeypatch, runner=runner,
            candidates=[{"branch": "feat/landed", "commit": "abc123"}],
        )
        res = SES._autoheal_branch_pointers(Path("/repo"))
        assert len(updates) == 1
        assert updates[0]["status"] == "shipped"

    def test_directory_present_but_for_a_different_branch_still_ships(
        self, monkeypatch, tmp_path,
    ):
        other_dir = tmp_path / "some-other-worktree"
        other_dir.mkdir()
        runner = FakeRunner({"rev-parse": (0, "sha\n", ""), "merge-base": (0, "", "")})
        monkeypatch.setattr(
            SES, "_worktree_branches",
            lambda root: [("some-other-worktree", "feat/unrelated", other_dir)],
        )
        updates = _wire(
            monkeypatch, runner=runner,
            candidates=[{"branch": "feat/landed", "commit": "abc123"}],
        )
        res = SES._autoheal_branch_pointers(Path("/repo"))
        assert updates[0]["status"] == "shipped"


def test_sweep_respects_heal_pointers_false(monkeypatch, tmp_path):
    # heal_pointers=False must skip the heal entirely (no query/update touched).
    called = {"n": 0}
    monkeypatch.setattr(SES, "_autoheal_branch_pointers",
                        lambda root: called.__setitem__("n", called["n"] + 1) or {})
    # Neuter the git-touching + delivery legs so sweep() runs offline.
    monkeypatch.setattr(SES, "_run_git", lambda *a, **k: (0, "", ""))
    monkeypatch.setattr(SES, "_worktree_branches", lambda root: [])
    monkeypatch.setattr(SES, "deliver_trailing_ledgers", lambda root, **k: {"status": "clean"})
    res = SES.sweep(repo_root=tmp_path, deliver_ledgers=False, heal_pointers=False)
    assert called["n"] == 0
    assert res["pointer_heal"]["healed"] == []


def test_already_correct_status_writes_no_row(monkeypatch, tmp_path):
    # An integrated-worktree-live pointer whose worktree is still live is
    # already correct; rewriting it every sweep is pure ledger churn.
    runner = FakeRunner({"rev-parse": (0, "sha\n", ""), "merge-base": (0, "", "")})
    wt = tmp_path / "wt"
    wt.mkdir()
    monkeypatch.setattr(SES, "_worktree_branches", lambda root: [("x", "feat/live", wt)])
    updates = _wire(
        monkeypatch, runner=runner,
        candidates=[{"branch": "feat/live", "commit": "abc", "status": "integrated-worktree-live"}],
    )
    res = SES._autoheal_branch_pointers(Path("/repo"))
    assert updates == [] and res["healed"] == [] and res["errors"] == []
