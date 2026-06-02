"""Colocated regression tests for ``check_branch_tree_mirror``.

Scenarios:
  pass — valid pointer: exists, commit resolves, ts fresh, mirror intact, status valid.
  block/pointer-missing — no pointer in ledger for the pushed branch.
  block/ledger-missing — ledger file absent altogether.
  block/commit-not-resolves — recorded commit does not exist in the temp repo.
  block/stale-ts — pointer ts is >72 h behind branch tip.
  block/missing-claude-fields — role/agent/parent blank.
  block/invalid-status — status not in valid enum.
  block/shipped-but-ahead — status=shipped but branch has commits beyond recorded sha.
  block/orchestrator-wrong-base — orchestrator base != origin/dev.
  pass/engineer-valid-base — engineer with base equal to parent tip (coherent).
  pass/terminal-branches-skipped — shipped/canceled rows excluded from audit scan.

Each test uses a real temp git repo (subprocess git) + fixture ndjson so the
keeper's git calls work end-to-end without monkeypatching our own code.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_branch_tree_mirror  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ts_hours_ago(hours: float) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(root)] + list(args),
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def _init_repo(tmp_path: Path) -> tuple[Path, str]:
    """Create a minimal git repo with one commit; return (root, sha)."""
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    readme = tmp_path / "README.md"
    readme.write_text("hello\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "init")
    sha = _git(tmp_path, "rev-parse", "HEAD")
    # Also create a local 'origin/dev' ref that the keeper looks for.
    _git(tmp_path, "update-ref", "refs/remotes/origin/dev", sha)
    return tmp_path, sha


def _add_commit(root: Path, *, message: str = "extra commit") -> str:
    """Append a new commit; return its sha."""
    f = root / f"file_{message[:8].replace(' ', '_')}.txt"
    f.write_text(message + "\n")
    _git(root, "add", str(f))
    _git(root, "commit", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _write_ledger(root: Path, rows: list[dict]) -> Path:
    ledger = root / "project-history" / "branch-tree.ndjson"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return ledger


def _base_row(branch: str, commit: str, **overrides) -> dict:
    """Return a minimally valid branch-pointer row for ``branch``."""
    base = {
        "ts": _now_iso(),
        "branch": branch,
        "base": "origin/dev",
        "commit": commit,
        "worktree": None,
        "role": "engineer",
        "agent": branch,
        "parent": "tech-lead",
        "session": "test-session",
        "paths": ["README.md"],
        "status": "on_going",
        "brief": "test brief",
        "notes": "",
    }
    base.update(overrides)
    return base


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestBranchTreeMirrorPass:
    """Valid pointers must NOT produce any issues."""

    def test_valid_pointer_passes(self, tmp_path):
        root, sha = _init_repo(tmp_path)
        _write_ledger(root, [_base_row("feat/my-feature", sha)])
        issues = check_branch_tree_mirror(branch="feat/my-feature", repo_root=root)
        assert issues == [], f"Expected no issues, got: {issues}"

    def test_orchestrator_valid_pointer_passes(self, tmp_path):
        root, sha = _init_repo(tmp_path)
        row = _base_row("feat/orch", sha, role="orchestrator", parent="origin/dev", base="origin/dev")
        _write_ledger(root, [row])
        issues = check_branch_tree_mirror(branch="feat/orch", repo_root=root)
        assert issues == [], f"Expected no issues, got: {issues}"

    def test_latest_row_wins_when_multiple(self, tmp_path):
        """Latest-by-ts row is used; stale earlier row is ignored."""
        root, sha = _init_repo(tmp_path)
        old_row = _base_row("feat/x", sha, ts=_ts_hours_ago(200), status="blocked")
        new_row = _base_row("feat/x", sha, ts=_now_iso(), status="on_going")
        _write_ledger(root, [old_row, new_row])
        issues = check_branch_tree_mirror(branch="feat/x", repo_root=root)
        assert issues == [], f"Expected no issues (new row should win), got: {issues}"

    def test_terminal_branches_skipped_in_audit_mode(self, tmp_path):
        """In audit mode (no branch arg), shipped/canceled/stale/deferred rows are not checked."""
        root, sha = _init_repo(tmp_path)
        rows = [
            _base_row("feat/shipped", sha, status="shipped"),
            _base_row("feat/canceled", sha, status="canceled"),
            _base_row("feat/stale", sha, status="stale"),
            _base_row("feat/deferred", sha, status="deferred"),
        ]
        _write_ledger(root, rows)
        # In audit mode these terminal rows are excluded → no issues.
        issues = check_branch_tree_mirror(branch=None, repo_root=root)
        assert issues == [], f"Expected no issues for terminal branches, got: {issues}"

    def test_engineer_base_on_parent_branch(self, tmp_path):
        """Engineer whose base is the parent's branch tip — coherent, should pass."""
        root, sha = _init_repo(tmp_path)
        # Create a feat/parent branch at sha.
        _git(root, "update-ref", "refs/heads/feat/parent", sha)
        row = _base_row(
            "feat/child", sha,
            role="engineer",
            parent="feat/parent",
            base="feat/parent",  # base resolves to the same sha as parent
        )
        _write_ledger(root, [row])
        issues = check_branch_tree_mirror(branch="feat/child", repo_root=root)
        # base and parent both resolve to the same sha → no contradiction.
        assert issues == [], f"Expected no issues, got: {issues}"


class TestBranchTreeMirrorMissingPointer:
    def test_missing_ledger_with_branch_arg(self, tmp_path):
        root, _ = _init_repo(tmp_path)
        # Ledger not created.
        issues = check_branch_tree_mirror(branch="feat/no-ledger", repo_root=root)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert "missing" in issues[0]["issue"].lower() or "ledger" in issues[0]["issue"].lower()

    def test_missing_ledger_no_branch_arg(self, tmp_path):
        root, _ = _init_repo(tmp_path)
        # No ledger + no branch → nothing to check → no issues.
        issues = check_branch_tree_mirror(branch=None, repo_root=root)
        assert issues == []

    def test_no_pointer_for_branch(self, tmp_path):
        root, sha = _init_repo(tmp_path)
        _write_ledger(root, [_base_row("feat/other", sha)])
        issues = check_branch_tree_mirror(branch="feat/missing", repo_root=root)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert "feat/missing" in issues[0]["issue"]
        # Block message should reference branch_pointer.
        assert "branch_pointer" in issues[0]["issue"]


class TestBranchTreeMirrorCommitNotResolved:
    def test_commit_does_not_exist(self, tmp_path):
        root, _ = _init_repo(tmp_path)
        fake_sha = "deadbeef1234567890abcdef12345678deadbeef"
        _write_ledger(root, [_base_row("feat/x", fake_sha)])
        issues = check_branch_tree_mirror(branch="feat/x", repo_root=root)
        high = [i for i in issues if i["severity"] == "high"]
        assert high, "Expected at least one high-severity issue for non-resolving commit"
        combined = " ".join(i["issue"] for i in high)
        assert "resolve" in combined.lower() or "does not" in combined.lower()

    def test_empty_commit_flagged(self, tmp_path):
        root, sha = _init_repo(tmp_path)
        row = _base_row("feat/x", sha)
        row["commit"] = ""
        _write_ledger(root, [row])
        issues = check_branch_tree_mirror(branch="feat/x", repo_root=root)
        high = [i for i in issues if i["severity"] == "high"]
        assert high


class TestBranchTreeMirrorStaleTs:
    def test_stale_ts_blocked(self, tmp_path):
        root, sha = _init_repo(tmp_path)
        # Add a newer commit so the branch tip has a fresh date.
        new_sha = _add_commit(root, message="progress commit")
        # Write a pointer with a very old ts and the new sha.
        old_ts = _ts_hours_ago(100)  # 100 h ago — well past 72 h threshold.
        row = _base_row("feat/stale-ts", new_sha, ts=old_ts)
        _write_ledger(root, [row])
        # We need the branch ref to exist so the tip lookup works.
        _git(root, "update-ref", f"refs/heads/feat/stale-ts", new_sha)
        issues = check_branch_tree_mirror(branch="feat/stale-ts", repo_root=root)
        high = [i for i in issues if i["severity"] == "high"]
        assert high, f"Expected stale-ts to be flagged. Got: {issues}"
        combined = " ".join(i["issue"] for i in high)
        assert "stale" in combined.lower()


class TestBranchTreeMirrorClaudeFields:
    @pytest.mark.parametrize("missing_field", ["role", "agent", "parent"])
    def test_missing_claude_field_blocked(self, tmp_path, missing_field):
        root, sha = _init_repo(tmp_path)
        row = _base_row("feat/x", sha)
        row[missing_field] = ""  # blank it out
        _write_ledger(root, [row])
        issues = check_branch_tree_mirror(branch="feat/x", repo_root=root)
        high = [i for i in issues if i["severity"] == "high"]
        assert high, f"Expected missing '{missing_field}' to be flagged"
        combined = " ".join(i["issue"] for i in high)
        assert missing_field in combined


class TestBranchTreeMirrorInvalidStatus:
    def test_invalid_status_blocked(self, tmp_path):
        root, sha = _init_repo(tmp_path)
        row = _base_row("feat/x", sha, status="in_progress")  # not in enum
        _write_ledger(root, [row])
        issues = check_branch_tree_mirror(branch="feat/x", repo_root=root)
        high = [i for i in issues if i["severity"] == "high"]
        assert high
        combined = " ".join(i["issue"] for i in high)
        assert "status" in combined.lower()
        assert "in_progress" in combined

    @pytest.mark.parametrize("status", ["on_going", "shipped", "blocked", "canceled", "stale", "deferred"])
    def test_all_valid_statuses_pass(self, tmp_path, status):
        root, sha = _init_repo(tmp_path)
        row = _base_row("feat/x", sha, status=status)
        _write_ledger(root, [row])
        issues = check_branch_tree_mirror(branch="feat/x", repo_root=root)
        # Filter to only status-related issues (other issues like base checks are separate).
        status_issues = [i for i in issues if "status" in i["issue"].lower() and "invalid" in i["issue"].lower()]
        assert status_issues == [], f"Valid status '{status}' should not be flagged. Got: {status_issues}"


class TestBranchTreeMirrorShippedContradiction:
    def test_shipped_but_ahead_blocked(self, tmp_path):
        root, sha = _init_repo(tmp_path)
        # Record the pointer at sha, then add a new commit.
        row = _base_row("feat/x", sha, status="shipped")
        _write_ledger(root, [row])
        # Create the local branch at the older sha.
        _git(root, "update-ref", "refs/heads/feat/x", sha)
        # Add a new commit to the branch.
        _add_commit(root, message="post-ship commit")
        new_sha = _git(root, "rev-parse", "HEAD")
        _git(root, "update-ref", "refs/heads/feat/x", new_sha)
        issues = check_branch_tree_mirror(branch="feat/x", repo_root=root)
        high = [i for i in issues if i["severity"] == "high"]
        assert high, f"Expected shipped-but-ahead to be flagged. Got: {issues}"
        combined = " ".join(i["issue"] for i in high)
        assert "shipped" in combined.lower() or "ahead" in combined.lower()

    def test_shipped_at_exact_commit_passes(self, tmp_path):
        root, sha = _init_repo(tmp_path)
        _git(root, "update-ref", "refs/heads/feat/x", sha)
        row = _base_row("feat/x", sha, status="shipped")
        _write_ledger(root, [row])
        issues = check_branch_tree_mirror(branch="feat/x", repo_root=root)
        # Should only have issues unrelated to the contradiction check (e.g., base/parent).
        contradiction_issues = [
            i for i in issues
            if "shipped" in i["issue"].lower() and "ahead" in i["issue"].lower()
        ]
        assert contradiction_issues == []


class TestBranchTreeMirrorOrchestratorBase:
    def test_orchestrator_wrong_base_blocked(self, tmp_path):
        root, sha = _init_repo(tmp_path)
        # Create a feat/parent branch so it resolves.
        _git(root, "update-ref", "refs/heads/feat/parent", sha)
        row = _base_row(
            "feat/orch", sha,
            role="orchestrator",
            parent="origin/dev",
            base="feat/parent",  # orchestrator MUST fork from origin/dev
        )
        _write_ledger(root, [row])
        issues = check_branch_tree_mirror(branch="feat/orch", repo_root=root)
        high = [i for i in issues if i["severity"] == "high" and "orchestrator" in i["issue"].lower()]
        assert high, f"Expected orchestrator-wrong-base to be flagged. Got: {issues}"
        combined = " ".join(i["issue"] for i in high)
        assert "origin/dev" in combined

    def test_orchestrator_correct_base_passes(self, tmp_path):
        root, sha = _init_repo(tmp_path)
        row = _base_row("feat/orch", sha, role="orchestrator", parent="origin/dev", base="origin/dev")
        _write_ledger(root, [row])
        issues = check_branch_tree_mirror(branch="feat/orch", repo_root=root)
        orchestrator_issues = [
            i for i in issues
            if "orchestrator" in i["issue"].lower() and "origin/dev" in i["issue"]
        ]
        assert orchestrator_issues == []


class TestBranchTreeMirrorFindingShape:
    """Every blocking finding must carry the required keys."""

    def test_finding_shape(self, tmp_path):
        root, _ = _init_repo(tmp_path)
        issues = check_branch_tree_mirror(branch="feat/no-pointer", repo_root=root)
        assert issues
        for i in issues:
            assert "product" in i, f"Missing 'product' in {i}"
            assert "file" in i, f"Missing 'file' in {i}"
            assert "issue" in i, f"Missing 'issue' in {i}"
            assert "severity" in i, f"Missing 'severity' in {i}"
            assert i["severity"] == "high", f"Expected high severity, got: {i['severity']}"
