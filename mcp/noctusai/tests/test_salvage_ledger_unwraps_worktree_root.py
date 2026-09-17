"""`cleanup_stale_worktrees` and `run_mole` both scope worktree-sweep
operations to a `root` that may legitimately be a caller's OWN worktree
(explicit `worktree_path` — correct for enumerating/removing worktrees
nested under THAT tree). But the recovery-pointer salvage ledger
(`project-history/worktree-salvage.ndjson`) must never land in a worktree
that can be torn down — it needs to land at the worktree's PRIMARY.

`workspace.unwrap_worktree_root(root)` is the narrow fix: it corrects
`root` ONLY when `root` is itself worktree-shaped, and passes any other
explicit root through unchanged (so a test's synthetic repo, or an
already-correct primary, is unaffected — see
`test_worktree_salvage.py::TestSweepWritesLedger` for that
non-regression coverage).

This file constructs `root` AS a worktree-shaped path (nested:
`<primary>/.claude/worktrees/caller-wt`, itself carrying its OWN
`.claude/worktrees/target-wt`, since git worktree structure only depends
on directory SHAPE, not on `git worktree add` having created it) and
proves the salvage ledger lands at `<primary>`, never at `caller-wt`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.cleanup_worktrees import cleanup_stale_worktrees  # noqa: E402
from tools.noctus.dev.mole import run_mole  # noqa: E402

LEDGER_REL = "project-history/worktree-salvage.ndjson"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True,
        capture_output=True, text=True,
    ).stdout


def _caller_wt_with_merged_target(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build `<primary>/.claude/worktrees/caller-wt` as a REAL git repo
    (dev branch, origin/dev ref, empty tracked branch-tree.ndjson so
    pointer lookups resolve locally) that ALSO carries its own
    `.claude/worktrees/target-wt` — a merged, clean, stale worktree of
    THAT repo. `caller-wt` is structurally a worktree of `primary`
    (matches `.../.claude/worktrees/<slug>` — the ONLY thing
    `unwrap_worktree_root` checks), even though nothing under `primary`
    itself was created via `git worktree add`.

    Returns (primary, caller_wt, target_wt).
    """
    primary = tmp_path / "primary"
    caller_wt = primary / ".claude" / "worktrees" / "caller-wt"
    caller_wt.mkdir(parents=True)
    # `noctus.dev.mole`'s `worktree_path` arg is validated by
    # `resolve_caller_root` (requires a `.git` entry AND this marker).
    (caller_wt / ".noctusai-workspace").write_text(
        "workspace_kind=primary\nworkspace_name=caller-wt\n", encoding="utf-8"
    )

    _git(caller_wt, "init", "-q", "-b", "dev")
    _git(caller_wt, "config", "user.email", "t@t.t")
    _git(caller_wt, "config", "user.name", "t")
    (caller_wt / "f").write_text("base\n")
    (caller_wt / "project-history").mkdir(parents=True)
    (caller_wt / "project-history" / "branch-tree.ndjson").write_text("")
    _git(caller_wt, "add", "f", "project-history/branch-tree.ndjson")
    _git(caller_wt, "commit", "-qm", "base")
    _git(caller_wt, "update-ref", "refs/remotes/origin/dev", "HEAD")

    # Publish a terminal `shipped` pointer for the soon-to-exist target
    # branch so the 2026-09-17 fail-closed-on-unresolvable-pointer guard
    # doesn't block the sweep.
    row = json.dumps({
        "branch": "wt-target", "status": "shipped",
        "ts": "2026-09-17T00:00:00+00:00",
    })
    with (caller_wt / "project-history" / "branch-tree.ndjson").open("a") as fh:
        fh.write(row + "\n")
    _git(caller_wt, "add", "project-history/branch-tree.ndjson")
    _git(caller_wt, "commit", "-qm", "pointer: wt-target shipped")
    _git(caller_wt, "update-ref", "refs/remotes/origin/dev", "HEAD")

    (caller_wt / ".claude" / "worktrees").mkdir(parents=True)
    target_wt = caller_wt / ".claude" / "worktrees" / "target-wt"
    _git(caller_wt, "worktree", "add", "-q", "-b", "wt-target", str(target_wt))

    return primary, caller_wt, target_wt


class TestCleanupStaleWorktreesUnwrapsCallerWorktree:
    def test_salvage_ledger_lands_at_primary_not_caller_worktree(self, tmp_path):
        primary, caller_wt, target_wt = _caller_wt_with_merged_target(tmp_path)

        result = cleanup_stale_worktrees(
            repo_root=caller_wt, force=True, recent_mtime_minutes=0,
        )
        assert result["status"] == "removed"
        assert not target_wt.exists()
        assert result["salvaged"] >= 1

        primary_ledger = primary / LEDGER_REL
        caller_wt_ledger = caller_wt / LEDGER_REL
        assert primary_ledger.exists(), (
            "the salvage ledger must land at the worktree's PRIMARY, "
            "never inside the worktree itself"
        )
        assert not caller_wt_ledger.exists()
        assert result["salvage_ledger"] == str(primary_ledger)


class TestMoleUnwrapsCallerWorktree:
    def test_salvage_ledger_lands_at_primary_not_caller_worktree(self, tmp_path):
        primary, caller_wt, target_wt = _caller_wt_with_merged_target(tmp_path)

        result = run_mole(
            mode="sweep", scope="worktrees", force=True,
            worktree_path=str(caller_wt), recent_mtime_minutes=0,
        )
        assert result.get("ok") is True, result
        assert not target_wt.exists()

        primary_ledger = primary / LEDGER_REL
        caller_wt_ledger = caller_wt / LEDGER_REL
        assert primary_ledger.exists(), (
            "the salvage ledger must land at the worktree's PRIMARY, "
            "never inside the worktree itself"
        )
        assert not caller_wt_ledger.exists()
