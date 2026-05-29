"""Tests for noctusai_lib.components.validation_signal.

Covers:
- derive_validation_status: all four outcome branches (table-driven)
- Threshold-edge cases: exactly 3 consumers, boundary dates
- compute_signal_inputs: integration with fixture component files
- _has_remediate_markers: marker detection
- _find_test_file: test file co-location patterns
- _count_recent_bugfix_commits: git log wrapper (mocked subprocess)
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from noctusai_lib.components.validation_signal import (
    BUGFIX_WINDOW_DAYS,
    CONSUMERS_THRESHOLD,
    _count_recent_bugfix_commits,
    _find_test_file,
    _has_remediate_markers,
    compute_signal_inputs,
    derive_validation_status,
)


# ── derive_validation_status — table-driven ───────────────────────────────────


class TestDeriveValidationStatus:
    """Table-driven tests covering all four status outcomes."""

    @pytest.mark.parametrize(
        "consumers,has_test,test_passes_ci,has_markers,bugfixes,expected",
        [
            # ── validated: all five gates pass ──
            (3, True, True, False, 0, "validated"),
            (5, True, True, False, 0, "validated"),
            (100, True, True, False, 0, "validated"),
            # ── shelfware: zero consumers ──
            (0, True, True, False, 0, "shelfware"),
            (0, False, None, True, 5, "shelfware"),
            # ── unknown: negative consumers (missing data signal) ──
            (-1, True, True, False, 0, "unknown"),
            # ── emerging: one or more gates fail ──
            # Not enough consumers (below threshold)
            (2, True, True, False, 0, "emerging"),
            (1, True, True, False, 0, "emerging"),
            # Has test but CI unknown
            (3, True, None, False, 0, "emerging"),
            # Has test but CI red
            (3, True, False, False, 0, "emerging"),
            # Has NOC-REMEDIATE markers
            (3, True, True, True, 0, "emerging"),
            # Recent bugfixes present
            (3, True, True, False, 1, "emerging"),
            (3, True, True, False, 3, "emerging"),
            # No test file
            (3, False, None, False, 0, "emerging"),
            # Multiple gates failing simultaneously
            (2, False, None, True, 2, "emerging"),
        ],
    )
    def test_derive_status(
        self,
        consumers: int,
        has_test: bool,
        test_passes_ci: bool | None,
        has_markers: bool,
        bugfixes: int,
        expected: str,
    ) -> None:
        result = derive_validation_status(
            component_name="TestComponent",
            consumers_count=consumers,
            has_test=has_test,
            test_passes_ci=test_passes_ci,
            has_noc_remediate_markers=has_markers,
            recent_bugfix_commits_14d=bugfixes,
        )
        assert result == expected

    def test_exactly_threshold_consumers_validated(self) -> None:
        """Exactly CONSUMERS_THRESHOLD consumers → validated (boundary test)."""
        result = derive_validation_status(
            component_name="BoundaryComponent",
            consumers_count=CONSUMERS_THRESHOLD,
            has_test=True,
            test_passes_ci=True,
            has_noc_remediate_markers=False,
            recent_bugfix_commits_14d=0,
        )
        assert result == "validated"

    def test_one_below_threshold_emerging(self) -> None:
        """One below CONSUMERS_THRESHOLD → emerging, not shelfware."""
        result = derive_validation_status(
            component_name="AlmostThereComponent",
            consumers_count=CONSUMERS_THRESHOLD - 1,
            has_test=True,
            test_passes_ci=True,
            has_noc_remediate_markers=False,
            recent_bugfix_commits_14d=0,
        )
        assert result == "emerging"


# ── threshold constants sanity ────────────────────────────────────────────────


class TestThresholdConstants:
    def test_consumers_threshold_positive(self) -> None:
        assert CONSUMERS_THRESHOLD > 0

    def test_bugfix_window_days_positive(self) -> None:
        assert BUGFIX_WINDOW_DAYS > 0

    def test_consumers_threshold_is_three(self) -> None:
        """DRY recurrence rule → 3 is the canonical threshold."""
        assert CONSUMERS_THRESHOLD == 3

    def test_bugfix_window_is_fourteen_days(self) -> None:
        """14 days = the canonical two-week settling window."""
        assert BUGFIX_WINDOW_DAYS == 14


# ── _has_remediate_markers ─────────────────────────────────────────────────────


class TestHasRemediateMarkers:
    def test_no_marker_returns_false(self, tmp_path: Path) -> None:
        f = tmp_path / "Component.tsx"
        f.write_text("export function Component() { return null; }\n")
        assert _has_remediate_markers(f) is False

    def test_with_marker_returns_true(self, tmp_path: Path) -> None:
        f = tmp_path / "Component.tsx"
        f.write_text(
            "// NOC-REMEDIATE[validation-pending]: needs type annotation — 2026-05-29\n"
            "export function Component() { return null; }\n"
        )
        assert _has_remediate_markers(f) is True

    def test_multiple_markers_still_true(self, tmp_path: Path) -> None:
        f = tmp_path / "Component.tsx"
        f.write_text(
            "// NOC-REMEDIATE[debt-a]: first — 2026-05-01\n"
            "// NOC-REMEDIATE[debt-b]: second — 2026-05-02\n"
            "export function x() {}\n"
        )
        assert _has_remediate_markers(f) is True

    def test_placeholder_bracket_ignored(self, tmp_path: Path) -> None:
        """NOC-REMEDIATE[<class>] placeholder (angle brackets) is NOT a real marker."""
        f = tmp_path / "Component.tsx"
        f.write_text("// NOC-REMEDIATE[<class>]: see the docs for format\n")
        assert _has_remediate_markers(f) is False

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.tsx"
        assert _has_remediate_markers(f) is False


# ── _find_test_file ────────────────────────────────────────────────────────────


class TestFindTestFile:
    def test_tsx_test_sibling(self, tmp_path: Path) -> None:
        src = tmp_path / "LoginForm.tsx"
        src.touch()
        (tmp_path / "LoginForm.test.tsx").touch()
        assert _find_test_file(src) is True

    def test_ts_test_sibling(self, tmp_path: Path) -> None:
        src = tmp_path / "LoginForm.tsx"
        src.touch()
        (tmp_path / "LoginForm.test.ts").touch()
        assert _find_test_file(src) is True

    def test_spec_sibling(self, tmp_path: Path) -> None:
        src = tmp_path / "LoginForm.tsx"
        src.touch()
        (tmp_path / "LoginForm.spec.tsx").touch()
        assert _find_test_file(src) is True

    def test_python_test_sibling(self, tmp_path: Path) -> None:
        src = tmp_path / "login_form.py"
        src.touch()
        (tmp_path / "test_login_form.py").touch()
        assert _find_test_file(src) is True

    def test_test_in_double_underscore_tests_subdir(self, tmp_path: Path) -> None:
        src = tmp_path / "Component.tsx"
        src.touch()
        tests_dir = tmp_path / "__tests__"
        tests_dir.mkdir()
        (tests_dir / "Component.test.tsx").touch()
        assert _find_test_file(src) is True

    def test_no_test_file_returns_false(self, tmp_path: Path) -> None:
        src = tmp_path / "Component.tsx"
        src.touch()
        assert _find_test_file(src) is False

    def test_unrelated_file_not_counted(self, tmp_path: Path) -> None:
        src = tmp_path / "LoginForm.tsx"
        src.touch()
        (tmp_path / "OtherComponent.test.tsx").touch()
        assert _find_test_file(src) is False


# ── _count_recent_bugfix_commits ──────────────────────────────────────────────


class TestCountRecentBugfixCommits:
    def _make_component(self, tmp_path: Path) -> Path:
        src = tmp_path / "Component.tsx"
        src.write_text("export function Component() { return null; }\n")
        return src

    def test_returns_zero_on_empty_log(self, tmp_path: Path) -> None:
        src = self._make_component(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            count = _count_recent_bugfix_commits(src, tmp_path)
        assert count == 0

    def test_counts_fix_commits(self, tmp_path: Path) -> None:
        src = self._make_component(tmp_path)
        git_output = "\n".join([
            "abc1234 fix: correct null-check in Component",
            "def5678 fix(auth): handle expired token",
        ])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=git_output, stderr="")
            count = _count_recent_bugfix_commits(src, tmp_path)
        assert count == 2

    def test_returns_zero_on_git_failure(self, tmp_path: Path) -> None:
        src = self._make_component(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="not a git repo")
            count = _count_recent_bugfix_commits(src, tmp_path)
        assert count == 0

    def test_returns_zero_on_timeout(self, tmp_path: Path) -> None:
        src = self._make_component(tmp_path)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            count = _count_recent_bugfix_commits(src, tmp_path)
        assert count == 0

    def test_returns_zero_for_path_outside_repo(self, tmp_path: Path) -> None:
        """A component outside repo_root returns 0 without calling git."""
        import tempfile
        with tempfile.TemporaryDirectory() as other_dir:
            outside_path = Path(other_dir) / "Component.tsx"
            outside_path.write_text("export function Component() {}\n")
            with patch("subprocess.run") as mock_run:
                count = _count_recent_bugfix_commits(outside_path, tmp_path)
            mock_run.assert_not_called()
            assert count == 0


# ── compute_signal_inputs — integration ──────────────────────────────────────


class TestComputeSignalInputs:
    def _make_component(self, tmp_path: Path, with_test: bool = False, with_marker: bool = False) -> Path:
        src = tmp_path / "LoginForm.tsx"
        content = "export function LoginForm() { return null; }\n"
        if with_marker:
            content = "// NOC-REMEDIATE[test-debt]: add test — 2026-05-01\n" + content
        src.write_text(content)
        if with_test:
            (tmp_path / "LoginForm.test.tsx").touch()
        return src

    def _make_neighbors(self, edge_kind: str = "consumes_component", count: int = 3) -> dict:
        """Synthetic graph neighbors result."""
        edges = []
        for i in range(count):
            edges.append({
                "kind": edge_kind,
                "source": f"product_{i}:SomeConsumer",
                "target": f"seed:LoginForm",
            })
        return {"edges": edges}

    def test_basic_signal_inputs_shape(self, tmp_path: Path) -> None:
        src = self._make_component(tmp_path, with_test=True)
        neighbors = self._make_neighbors("consumes_component", 3)
        with patch(
            "noctusai_lib.components.validation_signal._count_recent_bugfix_commits",
            return_value=0,
        ):
            result = compute_signal_inputs(src, neighbors, tmp_path)

        assert "consumers_count" in result
        assert "has_test" in result
        assert "test_passes_ci" in result
        assert "has_noc_remediate_markers" in result
        assert "recent_bugfix_commits_14d" in result

    def test_with_test_file_has_test_true(self, tmp_path: Path) -> None:
        src = self._make_component(tmp_path, with_test=True)
        with patch(
            "noctusai_lib.components.validation_signal._count_recent_bugfix_commits",
            return_value=0,
        ):
            result = compute_signal_inputs(src, {"edges": []}, tmp_path)
        assert result["has_test"] is True

    def test_without_test_file_has_test_false(self, tmp_path: Path) -> None:
        src = self._make_component(tmp_path, with_test=False)
        with patch(
            "noctusai_lib.components.validation_signal._count_recent_bugfix_commits",
            return_value=0,
        ):
            result = compute_signal_inputs(src, {"edges": []}, tmp_path)
        assert result["has_test"] is False

    def test_test_passes_ci_is_none(self, tmp_path: Path) -> None:
        """CI signal is always None at this layer (no live CI probe)."""
        src = self._make_component(tmp_path)
        with patch(
            "noctusai_lib.components.validation_signal._count_recent_bugfix_commits",
            return_value=0,
        ):
            result = compute_signal_inputs(src, {"edges": []}, tmp_path)
        assert result["test_passes_ci"] is None

    def test_marker_detected(self, tmp_path: Path) -> None:
        src = self._make_component(tmp_path, with_marker=True)
        with patch(
            "noctusai_lib.components.validation_signal._count_recent_bugfix_commits",
            return_value=0,
        ):
            result = compute_signal_inputs(src, {"edges": []}, tmp_path)
        assert result["has_noc_remediate_markers"] is True

    def test_consumers_from_consumes_component_edges(self, tmp_path: Path) -> None:
        src = self._make_component(tmp_path)
        neighbors = self._make_neighbors("consumes_component", 5)
        with patch(
            "noctusai_lib.components.validation_signal._count_recent_bugfix_commits",
            return_value=0,
        ):
            result = compute_signal_inputs(src, neighbors, tmp_path)
        assert result["consumers_count"] == 5

    def test_fallback_to_imports_edges(self, tmp_path: Path) -> None:
        """When no consumes_component edges exist, falls back to imports edges."""
        src = self._make_component(tmp_path)
        # imports edges pointing at LoginForm (same label as stem)
        neighbors = {
            "edges": [
                {"kind": "imports", "source": "productA:PageA", "target": "LoginForm"},
                {"kind": "imports", "source": "productB:PageB", "target": "LoginForm"},
            ]
        }
        with patch(
            "noctusai_lib.components.validation_signal._count_recent_bugfix_commits",
            return_value=0,
        ):
            result = compute_signal_inputs(src, neighbors, tmp_path)
        assert result["consumers_count"] == 2

    def test_zero_consumers_for_no_edges(self, tmp_path: Path) -> None:
        src = self._make_component(tmp_path)
        with patch(
            "noctusai_lib.components.validation_signal._count_recent_bugfix_commits",
            return_value=0,
        ):
            result = compute_signal_inputs(src, {"edges": []}, tmp_path)
        assert result["consumers_count"] == 0

    def test_end_to_end_validated_signal(self, tmp_path: Path) -> None:
        """Full-chain: compute inputs → derive status → validated."""
        src = self._make_component(tmp_path, with_test=True, with_marker=False)
        neighbors = self._make_neighbors("consumes_component", 3)
        with patch(
            "noctusai_lib.components.validation_signal._count_recent_bugfix_commits",
            return_value=0,
        ):
            inputs = compute_signal_inputs(src, neighbors, tmp_path)

        status = derive_validation_status(
            component_name="LoginForm",
            **inputs,
        )
        # CI is None → cannot be validated (one gate fails); should be emerging.
        # (test_passes_ci is None = not True = gate fails)
        assert status == "emerging"

    def test_end_to_end_shelfware(self, tmp_path: Path) -> None:
        """Zero consumers → shelfware regardless of other signals."""
        src = self._make_component(tmp_path, with_test=True)
        with patch(
            "noctusai_lib.components.validation_signal._count_recent_bugfix_commits",
            return_value=0,
        ):
            inputs = compute_signal_inputs(src, {"edges": []}, tmp_path)
        status = derive_validation_status(component_name="LoginForm", **inputs)
        assert status == "shelfware"
