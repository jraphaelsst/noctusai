"""Unit tests for the shared `_worktree_staleness` predicate.

The helper holds the merged-base + is-merged core extracted from
`cleanup_worktrees.py` AND `mole.py` (the documented N=2 DRY dup). Every git
call routes through an injectable `run` callable returning `(rc, stdout, stderr)`
(mirroring `release.py`), so these tests drive every path with ZERO real git via
a scripted fake runner — no monkey-patching of our own code.

Real-git integration parity (ancestry / patch-id against a live repo) is still
covered by `test_cleanup_worktrees.py` + `test_mole_tool.py`, which build real
worktrees.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import _worktree_staleness as wts


class FakeRunner:
    """A scripted git runner. Maps a git-args tuple → (rc, stdout, stderr).

    `calls` records every invocation so tests can assert which base ref the
    helper actually probed (the dev-keying assertion)."""

    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str, str]]):
        self._responses = responses
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: list[str]) -> tuple[int, str, str]:
        key = tuple(args)
        self.calls.append(key)
        # Default: command "succeeds" with no output unless scripted otherwise.
        return self._responses.get(key, (0, "", ""))


# ───────────────────────── base resolution ─────────────────────────────
def test_base_resolves_to_origin_dev_when_present():
    runner = FakeRunner({
        ("git", "rev-parse", "--verify", "--quiet", "origin/dev"): (0, "abc\n", ""),
    })
    assert wts.resolve_merged_base(runner) == "origin/dev"
    # It probed origin/dev — NOT origin/main (the dev-keying guarantee).
    assert ("git", "rev-parse", "--verify", "--quiet", "origin/dev") in runner.calls
    assert wts.PREFERRED_BASE == "origin/dev"


def test_base_falls_back_to_dev_when_origin_dev_absent():
    runner = FakeRunner({
        ("git", "rev-parse", "--verify", "--quiet", "origin/dev"): (1, "", ""),
    })
    assert wts.resolve_merged_base(runner) == "dev"
    assert wts.FALLBACK_BASE == "dev"


# ───────────────────────── merged predicate ────────────────────────────
def test_is_merged_true_on_sha_ancestry():
    # merge-base --is-ancestor returns 0 → SHA-merged; cherry is never reached.
    runner = FakeRunner({
        ("git", "merge-base", "--is-ancestor", "br", "origin/dev"): (0, "", ""),
    })
    assert wts.is_merged(runner, "br", "origin/dev") is True
    # cherry must not have been consulted once ancestry short-circuits.
    assert not any(c[:2] == ("git", "cherry") for c in runner.calls)


def test_is_merged_true_on_patch_id_when_not_ancestor():
    # Not a SHA ancestor, but `git cherry` reports ZERO '+' lines and the
    # branch has ≥1 commit → patch-id merged (the cherry-pick case).
    runner = FakeRunner({
        ("git", "merge-base", "--is-ancestor", "br", "origin/dev"): (1, "", ""),
        ("git", "cherry", "origin/dev", "br"): (0, "- aaaa\n- bbbb\n", ""),
        ("git", "log", "--oneline", "origin/dev..br"): (0, "aaaa x\nbbbb y\n", ""),
    })
    assert wts.is_merged(runner, "br", "origin/dev") is True


def test_is_merged_false_on_genuinely_unmerged_branch():
    # Not an ancestor; cherry shows a '+' line → genuinely unmerged → KEPT.
    runner = FakeRunner({
        ("git", "merge-base", "--is-ancestor", "br", "origin/dev"): (1, "", ""),
        ("git", "cherry", "origin/dev", "br"): (0, "+ cccc\n- dddd\n", ""),
        ("git", "log", "--oneline", "origin/dev..br"): (0, "cccc z\ndddd w\n", ""),
    })
    assert wts.is_merged(runner, "br", "origin/dev") is False


def test_is_merged_false_when_branch_has_no_commits_and_cherry_empty():
    # No '+' lines BUT zero total commits → NOT merged (mirrors the
    # `total > 0` guard — an empty diff is not a "merged" signal here).
    runner = FakeRunner({
        ("git", "merge-base", "--is-ancestor", "br", "origin/dev"): (1, "", ""),
        ("git", "cherry", "origin/dev", "br"): (0, "", ""),
        ("git", "log", "--oneline", "origin/dev..br"): (0, "", ""),
    })
    assert wts.is_merged(runner, "br", "origin/dev") is False


def test_all_commits_cherry_picked_false_when_cherry_errors():
    # `git cherry` non-zero rc (e.g. unknown ref) → not merged, never raises.
    runner = FakeRunner({
        ("git", "cherry", "origin/dev", "br"): (128, "", "fatal: bad revision"),
    })
    assert wts.all_commits_cherry_picked(runner, "br", "origin/dev") is False


def test_is_ancestor_reflects_returncode():
    yes = FakeRunner({
        ("git", "merge-base", "--is-ancestor", "a", "b"): (0, "", ""),
    })
    no = FakeRunner({
        ("git", "merge-base", "--is-ancestor", "a", "b"): (1, "", ""),
    })
    assert wts.is_ancestor(yes, "a", "b") is True
    assert wts.is_ancestor(no, "a", "b") is False


# ═══════════ 2026-09-20 — merged-into-base fallback (ledger-less immortal
# branches, 6.4 GB incident) ════════════════════════════════════════════════
class TestMergedIntoBaseFallback:
    def test_confirms_dead_when_diverged_and_ancestor(self):
        runner = FakeRunner({
            ("git", "rev-parse", "br"): (0, "aaaa\n", ""),
            ("git", "rev-parse", "base"): (0, "bbbb\n", ""),
            ("git", "merge-base", "--is-ancestor", "br", "base"): (0, "", ""),
        })
        assert wts.merged_into_base_confirms_dead(runner, "br", "base") is True

    def test_does_not_confirm_when_not_an_ancestor(self):
        runner = FakeRunner({
            ("git", "rev-parse", "br"): (0, "aaaa\n", ""),
            ("git", "rev-parse", "base"): (0, "bbbb\n", ""),
            ("git", "merge-base", "--is-ancestor", "br", "base"): (1, "", ""),
        })
        assert wts.merged_into_base_confirms_dead(runner, "br", "base") is False

    def test_rejects_the_trivial_self_ancestor_case(self):
        # 🔴 2026-09-16 false positive: a freshly-forked worktree has the
        # SAME sha as base (zero commits ahead) — `is_ancestor` alone would
        # read that as trivially "merged". The fallback must NOT authorize
        # removal here even though `merge-base --is-ancestor` would return 0
        # for two identical shas — the divergence check short-circuits
        # before ever asking ancestry.
        runner = FakeRunner({
            ("git", "rev-parse", "br"): (0, "aaaa\n", ""),
            ("git", "rev-parse", "base"): (0, "aaaa\n", ""),
            ("git", "merge-base", "--is-ancestor", "br", "base"): (0, "", ""),
        })
        assert wts.merged_into_base_confirms_dead(runner, "br", "base") is False
        # And ancestry must never even have been consulted — the divergence
        # check short-circuits it.
        assert not any(c[:3] == ("git", "merge-base", "--is-ancestor") for c in runner.calls)

    def test_unresolvable_branch_sha_refuses(self):
        runner = FakeRunner({
            ("git", "rev-parse", "br"): (128, "", "fatal: bad revision"),
            ("git", "rev-parse", "base"): (0, "bbbb\n", ""),
        })
        assert wts.merged_into_base_confirms_dead(runner, "br", "base") is False

    def test_unresolvable_base_sha_refuses(self):
        runner = FakeRunner({
            ("git", "rev-parse", "br"): (0, "aaaa\n", ""),
            ("git", "rev-parse", "base"): (128, "", "fatal: bad revision"),
        })
        assert wts.merged_into_base_confirms_dead(runner, "br", "base") is False


# ───────────────────── default subprocess runner ───────────────────────
def _init_repo_on_dev(root: Path) -> None:
    import subprocess

    def g(*a: str) -> None:
        subprocess.run(["git", *a], cwd=str(root), check=True,
                       capture_output=True, text=True)

    g("init", "-q", "-b", "dev")
    g("config", "user.email", "t@t.t")
    g("config", "user.name", "t")
    (root / "f").write_text("x\n")
    g("add", "f")
    g("commit", "-qm", "init")


def test_make_subprocess_runner_executes_git(tmp_path):
    _init_repo_on_dev(tmp_path)
    runner = wts.make_subprocess_runner(tmp_path)
    rc, out, _err = runner(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    assert rc == 0
    assert out.strip() == "dev"


def test_make_subprocess_runner_forwards_timeout(tmp_path):
    _init_repo_on_dev(tmp_path)
    runner = wts.make_subprocess_runner(tmp_path, timeout=60)
    rc, out, _err = runner(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    assert rc == 0 and out.strip() == "dev"


# ─────────────────── helper is NOT an MCP tool ──────────────────────────
def test_helper_exposes_no_register_and_is_not_in_register_all():
    # The helper must NOT be a tool (no register) and must NOT be wired into
    # register_all → the registered tool count is unchanged (zero tools added).
    assert not hasattr(wts, "register")

    import tools.noctus.dev as dev_pkg
    import inspect

    src = inspect.getsource(dev_pkg.register_all)
    assert "_worktree_staleness" not in src, (
        "_worktree_staleness must NOT be registered in register_all"
    )


# ═══════════════ 2026-09-16 incident guards ═══════════════════════════════
# A freshly-forked worktree has 0 commits ahead of origin/dev, which
# `is_ancestor` reads as trivially merged (see the module docstring). These
# tests pin the two guards that stop that false positive from reaching an
# actual `git worktree remove`.

class TestMinAgeGuard:
    def test_default_min_age_is_in_the_documented_30_120_minute_range(self):
        assert 30.0 <= wts.DEFAULT_MIN_AGE_MINUTES <= 120.0

    def test_worktree_age_seconds_uses_the_youngest_of_dir_and_commit(self, tmp_path):
        # tmp_path's real ctime is ~"now" (pytest just created it). A commit
        # timestamp far in the past must NOT win — age is measured from the
        # YOUNGEST of the two signals, not the oldest.
        long_ago = time.time() - 10_000
        runner = FakeRunner({
            ("git", "log", "-1", "--format=%ct", "br"): (0, f"{long_ago:.0f}\n", ""),
        })
        age = wts.worktree_age_seconds(runner, tmp_path, "br")
        assert age is not None and age < 60.0, (
            "age must reflect the freshly-created dir, not the stale commit time"
        )

    def test_worktree_age_seconds_none_when_neither_source_resolves(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        runner = FakeRunner({
            ("git", "log", "-1", "--format=%ct", "br"): (128, "", "fatal: bad revision"),
        })
        assert wts.worktree_age_seconds(runner, missing, "br") is None

    def test_is_too_young_true_when_age_unresolvable_conservative_refusal(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        runner = FakeRunner({
            ("git", "log", "-1", "--format=%ct", "br"): (128, "", "fatal"),
        })
        too_young, age, min_age_seconds = wts.is_too_young(runner, missing, "br")
        assert too_young is True and age is None
        assert min_age_seconds == wts.DEFAULT_MIN_AGE_MINUTES * 60.0

    def test_is_too_young_false_when_age_exceeds_threshold(self, tmp_path):
        runner = FakeRunner({
            ("git", "log", "-1", "--format=%ct", "br"): (0, "0\n", ""),
        })
        real_ctime = tmp_path.stat().st_ctime
        now = real_ctime + 3600.0  # 1 hour after the dir was created
        too_young, age, min_age_seconds = wts.is_too_young(
            runner, tmp_path, "br", min_age_minutes=1.0, now=now,
        )
        assert too_young is False
        assert age is not None and abs(age - (now - real_ctime)) < 0.01, (
            "age must be measured from the dir's own ctime, not the ancient commit epoch"
        )

    def test_is_too_young_true_when_age_below_threshold(self, tmp_path):
        runner = FakeRunner({
            ("git", "log", "-1", "--format=%ct", "br"): (0, "0\n", ""),
        })
        real_ctime = tmp_path.stat().st_ctime
        now = real_ctime + 5.0  # 5s after creation
        too_young, age, min_age_seconds = wts.is_too_young(
            runner, tmp_path, "br", min_age_minutes=60.0, now=now,
        )
        assert too_young is True
        assert age is not None and age < min_age_seconds


class TestLivePointerGuard:
    def test_no_pointer_row_blocks_fail_closed(self):
        # 🔴 2026-09-17 fix: absence of a pointer is UNKNOWN liveness, not
        # permission to delete — the fail-open here is exactly what let
        # session_end_sweep's auto-heal (and, before that, a never-published
        # pointer) wave a removal through. Unknown now blocks, same as a
        # live claim.
        runner = FakeRunner({
            ("git", "show", "origin/dev:project-history/branch-tree.ndjson"): (
                0, "", "",
            ),
        })
        assert wts.pointer_status_for_branch("feat/x", runner) is None
        blocks, status = wts.pointer_blocks_removal("feat/x", runner)
        assert blocks is True and status is None

    def test_query_exception_blocks_fail_closed(self, monkeypatch):
        # A query failure (e.g. branch_pointer.query raising) must be treated
        # exactly like "unknown" — never silently proceed as if terminal.
        from tools.noctus.dev import branch_pointer as _bp

        def _boom(**kwargs):
            raise RuntimeError("ledger read exploded")

        monkeypatch.setattr(_bp, "query", _boom)
        blocks, status = wts.pointer_blocks_removal("feat/x", FakeRunner({}))
        assert blocks is True and status is None

    def test_pointer_block_reason_names_unknown_liveness(self):
        reason = wts.pointer_block_reason(None)
        assert "UNKNOWN" in reason or "unknown" in reason.lower()
        assert "force=True does NOT override" in reason

    def test_pointer_block_reason_names_the_status(self):
        reason = wts.pointer_block_reason("on_going")
        assert "on_going" in reason
        assert "force=True does NOT override" in reason

    def test_on_going_pointer_blocks(self):
        row = (
            '{"branch": "feat/x", "status": "on_going", "ts": "2026-09-16T19:05:00Z"}'
        )
        runner = FakeRunner({
            ("git", "show", "origin/dev:project-history/branch-tree.ndjson"): (
                0, row + "\n", "",
            ),
        })
        assert wts.pointer_status_for_branch("feat/x", runner) == "on_going"
        blocks, status = wts.pointer_blocks_removal("feat/x", runner)
        assert blocks is True and status == "on_going"

    def test_terminal_status_does_not_block(self):
        row = (
            '{"branch": "feat/x", "status": "shipped", "ts": "2026-09-16T19:05:00Z"}'
        )
        runner = FakeRunner({
            ("git", "show", "origin/dev:project-history/branch-tree.ndjson"): (
                0, row + "\n", "",
            ),
        })
        blocks, status = wts.pointer_blocks_removal("feat/x", runner)
        assert blocks is False and status == "shipped"

    def test_latest_row_wins_over_an_earlier_stale_row(self):
        rows = (
            '{"branch": "feat/x", "status": "on_going", "ts": "2026-09-16T19:00:00Z"}\n'
            '{"branch": "feat/x", "status": "shipped", "ts": "2026-09-16T19:10:00Z"}\n'
        )
        runner = FakeRunner({
            ("git", "show", "origin/dev:project-history/branch-tree.ndjson"): (
                0, rows, "",
            ),
        })
        blocks, status = wts.pointer_blocks_removal("feat/x", runner)
        assert blocks is False and status == "shipped", (
            "the LATEST row (by ts) must win, not the first one seen"
        )

    def test_a_different_branchs_pointer_never_leaks_its_status_onto_this_one(self):
        # feat/x still has NO pointer of its own — it must block (fail-closed,
        # 2026-09-17), but with status=None, never borrowing feat/other's
        # on_going status.
        row = (
            '{"branch": "feat/other", "status": "on_going", '
            '"ts": "2026-09-16T19:05:00Z"}'
        )
        runner = FakeRunner({
            ("git", "show", "origin/dev:project-history/branch-tree.ndjson"): (
                0, row + "\n", "",
            ),
        })
        blocks, status = wts.pointer_blocks_removal("feat/x", runner)
        assert blocks is True and status is None


# ═══════════ 2026-09-17 incident — Leg 2: filesystem-mtime liveness ═══════
# INDEPENDENT of the ledger entirely — no pointer, no git-log call, a raw
# directory walk. Closes the hole where a missing/wrong/never-published
# pointer left the ONLY signal being (trivially-true) merge ancestry.
class TestRecentMtimeGuard:
    def test_default_window_matches_the_age_guard_default(self):
        # Documented pairing: the two "grace period" defaults are equal so an
        # operator tuning one has an obvious analog for the other.
        assert wts.DEFAULT_RECENT_MTIME_MINUTES == wts.DEFAULT_MIN_AGE_MINUTES

    def test_latest_file_mtime_none_for_missing_dir(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        assert wts._latest_file_mtime(missing) is None

    def test_latest_file_mtime_finds_the_newest_file(self, tmp_path):
        old = tmp_path / "old.txt"
        old.write_text("x")
        new = tmp_path / "new.txt"
        new.write_text("y")
        old_time = time.time() - 10_000
        os_utime = __import__("os").utime
        os_utime(old, (old_time, old_time))
        latest = wts._latest_file_mtime(tmp_path)
        assert latest is not None
        assert abs(latest - new.stat().st_mtime) < 1.0

    def test_latest_file_mtime_ignores_noise_dirs(self, tmp_path):
        # A file only inside an ignored dir must NOT count as "recent
        # activity" — otherwise a stray __pycache__/node_modules write would
        # make every worktree look permanently live.
        for name in wts.IGNORED_DIR_NAMES:
            d = tmp_path / name
            d.mkdir()
            (d / "f").write_text("noise")
        assert wts._latest_file_mtime(tmp_path) is None

    def test_is_recently_active_true_within_window(self, tmp_path):
        (tmp_path / "f.txt").write_text("x")
        active, age, window = wts.is_recently_active(
            tmp_path, window_minutes=60.0,
        )
        assert active is True
        assert age is not None and age < window

    def test_is_recently_active_false_outside_window(self, tmp_path):
        f = tmp_path / "f.txt"
        f.write_text("x")
        old_time = time.time() - 10_000
        __import__("os").utime(f, (old_time, old_time))
        active, age, window = wts.is_recently_active(
            tmp_path, window_minutes=1.0,
        )
        assert active is False
        assert age is not None and age > window

    def test_is_recently_active_true_when_unresolvable_conservative_refusal(
        self, tmp_path,
    ):
        missing = tmp_path / "does-not-exist"
        active, age, _window = wts.is_recently_active(missing)
        assert active is True and age is None

    def test_is_recently_active_true_when_directory_empty(self, tmp_path):
        # An empty (but existing) worktree dir cannot prove staleness either
        # — conservative refusal, same contract as the missing-path case.
        empty = tmp_path / "empty-wt"
        empty.mkdir()
        active, age, _window = wts.is_recently_active(empty)
        assert active is True and age is None
