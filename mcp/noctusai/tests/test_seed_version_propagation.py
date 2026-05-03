"""Tests for `check_seed_version_propagation` — drift detection for the
install-time seed version stamp.

Shipped by `seed-inheritance-hardening` Phase 3 via `seed-core-consolidation` §7.1
(user decision: git-tag/SHA-derived at install time).

The detector pulls two signals at runtime:
  * Current `git rev-parse --short HEAD` via subprocess.
  * Installed `noctusai_seed.__seed_version__` / `noctusai_lib.__lib_version__`
    from `sys.modules`.

Tests inject fakes into `sys.modules` (not `builtins.__import__`, which
would clobber the detector's own internal imports like `subprocess`).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_seed_version_propagation  # noqa: E402


# --- Helpers ---------------------------------------------------------------


def _fake_git_result(sha: str, returncode: int = 0):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = f"{sha}\n" if sha else ""
    return result


class _ModuleInjector:
    """Context manager that swaps `noctusai_seed` + `noctusai_lib` in
    `sys.modules` with fakes carrying the supplied version strings."""

    def __init__(
        self,
        seed_version: str | None = "abc1234",
        lib_version: str | None = "abc1234",
        *,
        seed_missing: bool = False,
        lib_missing: bool = False,
    ):
        self._seed_version = seed_version
        self._lib_version = lib_version
        self._seed_missing = seed_missing
        self._lib_missing = lib_missing
        self._original_seed = None
        self._original_lib = None
        self._seed_was_present = False
        self._lib_was_present = False

    def __enter__(self):
        self._seed_was_present = "noctusai_seed" in sys.modules
        self._lib_was_present = "noctusai_lib" in sys.modules
        if self._seed_was_present:
            self._original_seed = sys.modules["noctusai_seed"]
        if self._lib_was_present:
            self._original_lib = sys.modules["noctusai_lib"]

        if self._seed_missing:
            sys.modules.pop("noctusai_seed", None)
        else:
            mod = types.ModuleType("noctusai_seed")
            if self._seed_version is not None:
                mod.__seed_version__ = self._seed_version
            sys.modules["noctusai_seed"] = mod

        if self._lib_missing:
            sys.modules.pop("noctusai_lib", None)
        else:
            mod = types.ModuleType("noctusai_lib")
            if self._lib_version is not None:
                mod.__lib_version__ = self._lib_version
            sys.modules["noctusai_lib"] = mod
        return self

    def __exit__(self, *exc):
        if self._seed_was_present:
            sys.modules["noctusai_seed"] = self._original_seed
        else:
            sys.modules.pop("noctusai_seed", None)
        if self._lib_was_present:
            sys.modules["noctusai_lib"] = self._original_lib
        else:
            sys.modules.pop("noctusai_lib", None)


# --- Detector behavior ----------------------------------------------------


def test_returns_no_issues_when_versions_match_git_head(tmp_path):
    """Both packages report the current HEAD SHA → clean."""
    with (
        patch("subprocess.run", return_value=_fake_git_result("abc1234")),
        _ModuleInjector("abc1234", "abc1234"),
    ):
        issues = check_seed_version_propagation(repo_root=tmp_path)
    assert issues == []


def test_flags_drift_when_seed_static_is_stale(tmp_path):
    """Installed `noctusai_seed.__seed_version__` != git HEAD → high severity."""
    with (
        patch("subprocess.run", return_value=_fake_git_result("abc1234")),
        _ModuleInjector("stale99", "abc1234"),
    ):
        issues = check_seed_version_propagation(repo_root=tmp_path)

    assert len(issues) == 1
    issue = issues[0]
    assert issue["severity"] == "high"
    assert issue["product"] == "<platform>"
    assert "stale99" in issue["issue"]
    assert "abc1234" in issue["issue"]
    assert "stamp-seed-version" in issue["issue"]


def test_flags_drift_when_lib_static_is_stale(tmp_path):
    """Same flag behavior for noctusai_lib side."""
    with (
        patch("subprocess.run", return_value=_fake_git_result("abc1234")),
        _ModuleInjector("abc1234", "oldlibs"),
    ):
        issues = check_seed_version_propagation(repo_root=tmp_path)

    assert len(issues) == 1
    assert issues[0]["severity"] == "high"
    assert "oldlibs" in issues[0]["issue"]


def test_flags_both_when_both_drift(tmp_path):
    """Both stale → two separate flags (one per package)."""
    with (
        patch("subprocess.run", return_value=_fake_git_result("abc1234")),
        _ModuleInjector("old1", "old2"),
    ):
        issues = check_seed_version_propagation(repo_root=tmp_path)

    assert len(issues) == 2
    severities = [i["severity"] for i in issues]
    assert severities == ["high", "high"]


def test_warning_when_version_is_runtime_fallback_matching_head(tmp_path):
    """`runtime:<sha>` matching HEAD → warning (fallback path, no stamp yet)."""
    with (
        patch("subprocess.run", return_value=_fake_git_result("abc1234")),
        _ModuleInjector("runtime:abc1234", "runtime:abc1234"),
    ):
        issues = check_seed_version_propagation(repo_root=tmp_path)

    assert len(issues) == 2
    for issue in issues:
        assert issue["severity"] == "warning"
        assert "falls back to live git" in issue["issue"]
        assert "stamp-seed-version" in issue["issue"]


def test_critical_when_version_is_unknown(tmp_path):
    """`__seed_version__ == "unknown"` → critical (detector is blind)."""
    with (
        patch("subprocess.run", return_value=_fake_git_result("abc1234")),
        _ModuleInjector("unknown", "abc1234"),
    ):
        issues = check_seed_version_propagation(repo_root=tmp_path)

    assert len(issues) == 1
    assert issues[0]["severity"] == "critical"
    assert "unknown" in issues[0]["issue"]


def test_critical_when_version_attr_missing(tmp_path):
    """Module present but `__seed_version__` attribute missing → critical."""
    with (
        patch("subprocess.run", return_value=_fake_git_result("abc1234")),
        _ModuleInjector(seed_version=None, lib_version="abc1234"),
    ):
        issues = check_seed_version_propagation(repo_root=tmp_path)

    assert len(issues) == 1
    assert issues[0]["severity"] == "critical"


def test_skips_check_when_git_unavailable(tmp_path):
    """Detector returns no issues when git isn't callable — fails open."""
    with (
        patch("subprocess.run", side_effect=FileNotFoundError("git")),
        _ModuleInjector("abc1234", "abc1234"),
    ):
        issues = check_seed_version_propagation(repo_root=tmp_path)

    assert issues == []


def test_skips_check_when_git_returns_empty(tmp_path):
    """Detector returns no issues when `git rev-parse` fails quietly."""
    with (
        patch("subprocess.run", return_value=_fake_git_result("", returncode=128)),
        _ModuleInjector("abc1234", "abc1234"),
    ):
        issues = check_seed_version_propagation(repo_root=tmp_path)

    assert issues == []
