"""Tests for the learn/extract-before-delete worktree-salvage ledger leg.

`_worktree_salvage` is the mechanical "recovery record → tracked ledger" leg
(KB § PATTERNS/common/storage-hygiene.md § 2.3): every swept worktree is recorded to
`project-history/worktree-salvage.ndjson` so the recovery pointer survives the
transient out-of-repo salvage dir. Verifies the pure helpers + the real-git
integration through `cleanup_stale_worktrees(force=True)`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import _worktree_salvage as wsv
from tools.noctus.dev.cleanup_worktrees import cleanup_stale_worktrees

LEDGER_REL = "project-history/worktree-salvage.ndjson"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True,
        capture_output=True, text=True,
    ).stdout


class TestBuildRecords:
    def test_shape_and_defaults(self):
        recs = wsv.build_records([
            {"path": "/wt/a", "branch": "wt-a", "sha": "abc123"},
            {"path": "/wt/b", "branch": None, "sha": None, "reason": "orphan"},
        ])
        assert len(recs) == 2
        assert recs[0]["event"] == "worktree-sweep"
        assert recs[0]["path"] == "/wt/a"
        assert recs[0]["branch"] == "wt-a"
        assert recs[0]["sha"] == "abc123"
        assert recs[0]["reason"] == "merged-to-dev"  # default
        assert recs[1]["reason"] == "orphan"          # explicit kept
        assert recs[0]["ts"]  # date stamped

    def test_empty(self):
        assert wsv.build_records([]) == []


class TestAppendLedger:
    def test_writes_tracked_ndjson_and_appends(self, tmp_path):
        root = tmp_path
        first = wsv.append_ledger(root, [{"ts": "2026-05-25", "event": "worktree-sweep",
                                          "path": "/wt/a", "branch": "wt-a",
                                          "sha": "s1", "reason": "merged-to-dev"}])
        assert first == root / LEDGER_REL
        assert first.exists()
        # Second call APPENDS (does not overwrite).
        wsv.append_ledger(root, [{"ts": "2026-05-25", "event": "worktree-sweep",
                                  "path": "/wt/b", "branch": "wt-b",
                                  "sha": "s2", "reason": "merged-to-dev"}])
        lines = (root / LEDGER_REL).read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["path"] == "/wt/a"
        assert json.loads(lines[1])["sha"] == "s2"

    def test_empty_records_is_noop_returns_none(self, tmp_path):
        assert wsv.append_ledger(tmp_path, []) is None
        assert not (tmp_path / LEDGER_REL).exists()

    def test_branch_sha_resolves_real_ref(self, tmp_path):
        r = tmp_path / "g"
        r.mkdir()
        _git(r, "init", "-q", "-b", "main")
        _git(r, "config", "user.email", "t@t.t")
        _git(r, "config", "user.name", "t")
        (r / "f").write_text("x\n")
        _git(r, "add", "f")
        _git(r, "commit", "-qm", "c")
        head = _git(r, "rev-parse", "HEAD").strip()
        assert wsv.branch_sha(r, "main") == head
        assert wsv.branch_sha(r, None) is None
        assert wsv.branch_sha(r, "no-such-branch") is None


class TestAppendLedgerIdempotency:
    """The N=3 cross-tree hazard fix (2026-05-28): repeated cleanup calls used to
    re-append the same record, leaving the worktree dirty and looping forever."""

    def _rec(self, path, branch, sha):
        return {"ts": "2026-05-28", "event": "worktree-sweep", "path": path,
                "branch": branch, "sha": sha, "reason": "merged-to-dev"}

    def test_skip_duplicate_same_key(self, tmp_path):
        rec = self._rec("/wt/x", "wt-x", "sX")
        wsv.append_ledger(tmp_path, [rec])
        wsv.append_ledger(tmp_path, [rec])
        wsv.append_ledger(tmp_path, [rec])
        lines = (tmp_path / LEDGER_REL).read_text().strip().splitlines()
        assert len(lines) == 1  # idempotent — first write wins

    def test_returns_path_even_when_all_duplicates(self, tmp_path):
        rec = self._rec("/wt/y", "wt-y", "sY")
        first = wsv.append_ledger(tmp_path, [rec])
        # Second call: all records are duplicates → no write, but path is canonical.
        second = wsv.append_ledger(tmp_path, [rec])
        assert second == first  # caller still gets the path (for staging probes)

    def test_new_keys_after_existing_still_appended(self, tmp_path):
        wsv.append_ledger(tmp_path, [self._rec("/wt/a", "wt-a", "s1")])
        # Mixed batch: one duplicate + one new — only the new one is written.
        wsv.append_ledger(tmp_path, [
            self._rec("/wt/a", "wt-a", "s1"),     # duplicate
            self._rec("/wt/a", "wt-a", "s2"),     # new (same branch, different sha)
        ])
        lines = (tmp_path / LEDGER_REL).read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[1])["sha"] == "s2"

    def test_branch_distinguishes_key(self, tmp_path):
        # Same path+sha but different branch ⇒ NOT a duplicate (the recovery
        # pointer is branch-anchored — different branch = different recovery).
        wsv.append_ledger(tmp_path, [self._rec("/wt/p", "branch-A", "sZ")])
        wsv.append_ledger(tmp_path, [self._rec("/wt/p", "branch-B", "sZ")])
        lines = (tmp_path / LEDGER_REL).read_text().strip().splitlines()
        assert len(lines) == 2

    def test_malformed_line_in_existing_ledger_does_not_block(self, tmp_path):
        ledger = tmp_path / LEDGER_REL
        ledger.parent.mkdir(parents=True)
        ledger.write_text("not json\n" +
                          json.dumps(self._rec("/wt/q", "wt-q", "sQ")) + "\n")
        # The malformed line is silently skipped (no spurious duplicate from
        # garbage); the valid one still acts as a duplicate key.
        wsv.append_ledger(tmp_path, [self._rec("/wt/q", "wt-q", "sQ")])
        lines = ledger.read_text().splitlines()
        assert len(lines) == 2  # malformed + 1 real, no new line


class TestSweepWritesLedger:
    """Integration: a real force sweep records recovery pointers to the ledger."""

    def _repo_with_merged_worktree(self, tmp_path: Path) -> tuple[Path, Path]:
        r = tmp_path / "noc"
        r.mkdir()
        _git(r, "init", "-q", "-b", "dev")
        _git(r, "config", "user.email", "t@t.t")
        _git(r, "config", "user.name", "t")
        (r / "f").write_text("base\n")
        _git(r, "add", "f")
        _git(r, "commit", "-qm", "base")
        _git(r, "update-ref", "refs/remotes/origin/dev", "HEAD")
        (r / ".claude" / "worktrees").mkdir(parents=True)
        wt = r / ".claude" / "worktrees" / "agent-clean"
        _git(r, "worktree", "add", "-q", "-b", "wt-clean", str(wt))
        return r, wt

    def test_force_sweep_records_recovery_pointer(self, tmp_path):
        r, wt = self._repo_with_merged_worktree(tmp_path)
        result = cleanup_stale_worktrees(repo_root=r, force=True)
        assert result["status"] == "removed"
        assert not wt.exists()
        # The extract-before-delete ledger leg fired:
        assert result["salvaged"] >= 1
        assert result["salvage_ledger"] == str(r / LEDGER_REL)
        ledger = r / LEDGER_REL
        assert ledger.exists(), "force sweep must write the tracked salvage ledger"
        recs = [json.loads(ln) for ln in ledger.read_text().strip().splitlines()]
        clean = [x for x in recs if x.get("branch") == "wt-clean"]
        assert clean, "removed worktree's branch must be recorded for recovery"
        assert clean[0]["sha"], "recovery SHA must be captured (git branch <name> <sha>)"

    def test_dry_run_writes_nothing(self, tmp_path):
        r, wt = self._repo_with_merged_worktree(tmp_path)
        result = cleanup_stale_worktrees(repo_root=r)  # dry-run
        assert result["salvaged"] == 0
        assert result["salvage_ledger"] is None
        assert not (r / LEDGER_REL).exists(), "dry-run must not touch the ledger"
        assert wt.exists()
