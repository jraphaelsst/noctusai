"""Colocated tests for `check_dangling_remote_branches`.

Coverage:
  positive — unique branch older than threshold emits a warning finding
  negative — integrated branches / young unique branches / protected branches
             do NOT emit findings
  error-resilience — classification failure → warning finding, not crash
  finding shape — finding dict has required keys + correct severity
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_dangling_remote_branches  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_branch_entry(
    branch: str,
    verdict: str,
    age_days: float | None,
    subject: str = "some subject",
    unique_commits: int | None = 1,
) -> dict:
    return {
        "branch": branch,
        "verdict": verdict,
        "age_days": age_days,
        "subject": subject,
        "unique_commits": unique_commits,
    }


_PATCH_TARGET = "tools.noctus.dev.remote_branch_hygiene.classify_remote_branches"


def _patch_classify(branches: list[dict]):
    """Context manager that patches classify_remote_branches to return `branches`.

    The function is imported inside check_dangling_remote_branches via:
      `from tools.noctus.dev.remote_branch_hygiene import classify_remote_branches`
    Patching the function on the source module (remote_branch_hygiene) is correct.
    """
    return patch(_PATCH_TARGET, return_value=branches)


# ── Positive: should emit findings ────────────────────────────────────────────

class TestDanglingRemoteBranchesPositive:
    """Cases that MUST produce warning findings."""

    def test_unique_old_branch_emits_warning(self):
        """unique branch with age_days > threshold → 1 warning finding."""
        branches = [
            _make_branch_entry("feat/old-unique", "unique", age_days=30.0),
        ]
        with _patch_classify(branches):
            issues = check_dangling_remote_branches(threshold_days=7.0)

        assert len(issues) == 1, f"Expected 1 issue, got: {issues}"
        assert issues[0]["severity"] == "warning"
        assert "feat/old-unique" in issues[0]["file"]
        assert "unique" in issues[0]["issue"].lower() or "commit" in issues[0]["issue"].lower()

    def test_multiple_unique_old_branches(self):
        """Multiple unique-old branches → one finding each."""
        branches = [
            _make_branch_entry("feat/a", "unique", age_days=10.0),
            _make_branch_entry("feat/b", "unique", age_days=20.0),
        ]
        with _patch_classify(branches):
            issues = check_dangling_remote_branches(threshold_days=7.0)

        assert len(issues) == 2
        assert all(i["severity"] == "warning" for i in issues)

    def test_threshold_boundary(self):
        """Branch aged exactly threshold + 1 day → flagged; exactly threshold → not flagged."""
        threshold = 7.0
        branches_over = [_make_branch_entry("feat/over", "unique", age_days=threshold + 1)]
        branches_at = [_make_branch_entry("feat/at", "unique", age_days=threshold)]

        with _patch_classify(branches_over):
            issues_over = check_dangling_remote_branches(threshold_days=threshold)
        with _patch_classify(branches_at):
            issues_at = check_dangling_remote_branches(threshold_days=threshold)

        assert len(issues_over) == 1
        assert len(issues_at) == 0  # strictly greater-than check


# ── Negative: should NOT emit findings ────────────────────────────────────────

class TestDanglingRemoteBranchesNegative:
    """Cases that must NOT produce findings."""

    def test_integrated_branch_not_flagged(self):
        branches = [_make_branch_entry("feat/integrated", "integrated", age_days=30.0)]
        with _patch_classify(branches):
            issues = check_dangling_remote_branches()
        assert len(issues) == 0

    def test_protected_branch_not_flagged(self):
        branches = [
            _make_branch_entry("dev", "protected", age_days=None, unique_commits=None),
            _make_branch_entry("main", "protected", age_days=None, unique_commits=None),
        ]
        with _patch_classify(branches):
            issues = check_dangling_remote_branches()
        assert len(issues) == 0

    def test_young_unique_branch_not_flagged(self):
        """unique branch aged 2 days with 7-day threshold → no finding."""
        branches = [_make_branch_entry("feat/young", "unique", age_days=2.0)]
        with _patch_classify(branches):
            issues = check_dangling_remote_branches(threshold_days=7.0)
        assert len(issues) == 0

    def test_unique_with_null_age_not_flagged(self):
        """unique branch with age_days=None (can't determine age) → not flagged."""
        branches = [_make_branch_entry("feat/no-age", "unique", age_days=None)]
        with _patch_classify(branches):
            issues = check_dangling_remote_branches()
        assert len(issues) == 0

    def test_empty_remote_list_returns_clean(self):
        with _patch_classify([]):
            issues = check_dangling_remote_branches()
        assert len(issues) == 0


# ── Error resilience ──────────────────────────────────────────────────────────

class TestDanglingRemoteBranchesErrorResilience:
    """Never silent on git errors — emits a warning finding instead of crashing."""

    def test_classification_failure_emits_warning_not_crash(self):
        """If classify_remote_branches raises → warning finding, no exception."""
        with patch(_PATCH_TARGET, side_effect=RuntimeError("git not available")):
            issues = check_dangling_remote_branches()

        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "classification failed" in issues[0]["issue"].lower()


# ── Finding shape ─────────────────────────────────────────────────────────────

class TestDanglingRemoteBranchesFindingShape:
    def test_finding_has_required_keys(self):
        branches = [_make_branch_entry("feat/shape-check", "unique", age_days=14.0)]
        with _patch_classify(branches):
            issues = check_dangling_remote_branches(threshold_days=7.0)

        assert len(issues) == 1
        issue = issues[0]
        assert "product" in issue
        assert "file" in issue
        assert "issue" in issue
        assert "severity" in issue
        assert issue["severity"] in ("warning", "high", "critical")
