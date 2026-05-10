"""Tests for the ``noctus.hound.*`` tool umbrella.

The hound orchestrates the absorption + fusion + optimization trio.
Each upstream scanner has its own deep test suite (in test_seed.py);
these tests verify the hound's composition + dispatch logic without
re-testing the underlying detectors.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.hound.scan import _next_action, scan


class TestHoundScan:
    """Composition + dispatch logic. Upstream scanners are stubbed so
    the test isn't beholden to live-tree state."""

    def test_runs_all_three_scopes_by_default(self):
        with (
            mock.patch("tools.noctus.seed.report.report",
                       return_value={"summary": {"P0_count": 0, "P1_count": 0, "total_items": 0}, "items": []}),
            mock.patch("tools.noctus.seed.scan_fusions.scan_fusions",
                       return_value={"summary": {"pairs_above_threshold": 0}, "pairs": []}),
            mock.patch("tools.noctus.seed.scan_optimizations.scan_optimizations",
                       return_value={"summary": {"total_findings": 0, "by_severity": {}}, "findings": []}),
        ):
            r = scan(max_per_scope=5)
        assert set(r["scopes_run"]) == {"absorption", "fusion", "optimization"}
        assert r["errors"] == []
        assert "absorption" in r["unified"]
        assert "fusion" in r["unified"]
        assert "optimization" in r["unified"]
        assert "total_candidates" in r["unified"]

    def test_scopes_filter_runs_only_requested(self):
        with (
            mock.patch("tools.noctus.seed.report.report",
                       return_value={"summary": {"total_items": 0}, "items": []}),
            mock.patch("tools.noctus.seed.scan_fusions.scan_fusions",
                       return_value={"summary": {"pairs_above_threshold": 0}, "pairs": []}),
        ):
            r = scan(scopes=["absorption", "fusion"])
        assert set(r["scopes_run"]) == {"absorption", "fusion"}
        assert "optimization" not in r["unified"]

    def test_unknown_scope_returns_error(self):
        r = scan(scopes=["bogus"])
        assert r["scopes_run"] == []
        assert any("unknown scope" in e for e in r["errors"])

    def test_soft_fail_per_scope_keeps_others_running(self):
        """When one scope's scanner raises, errors[] gets the message but
        the other two scopes still complete."""
        with (
            mock.patch("tools.noctus.seed.report.report",
                       side_effect=RuntimeError("boom")),
            mock.patch("tools.noctus.seed.scan_fusions.scan_fusions",
                       return_value={"summary": {"pairs_above_threshold": 2}, "pairs": []}),
            mock.patch("tools.noctus.seed.scan_optimizations.scan_optimizations",
                       return_value={"summary": {"total_findings": 0, "by_severity": {}}, "findings": []}),
        ):
            r = scan()
        assert "absorption" not in r["scopes_run"]
        assert "fusion" in r["scopes_run"]
        assert "optimization" in r["scopes_run"]
        assert any("absorption" in e and "boom" in e for e in r["errors"])

    def test_unified_aggregates_match_per_scope(self):
        with (
            mock.patch("tools.noctus.seed.report.report",
                       return_value={"summary": {"P0_count": 0, "P1_count": 3, "total_items": 5}, "items": []}),
            mock.patch("tools.noctus.seed.scan_fusions.scan_fusions",
                       return_value={"summary": {
                           "pairs_above_threshold": 7,
                           "estimated_savings_loc_total": 50,
                           "subsume_candidates_count": 3,
                           "compose_candidates_count": 4,
                       }, "pairs": []}),
            mock.patch("tools.noctus.seed.scan_optimizations.scan_optimizations",
                       return_value={"summary": {
                           "total_findings": 4,
                           "by_severity": {"warning": 4},
                           "estimated_savings_loc_total": 12,
                           "by_detector": {},
                       }, "findings": []}),
        ):
            r = scan()
        u = r["unified"]
        assert u["absorption"]["candidates"] == 5
        assert u["fusion"]["candidates"] == 7
        assert u["optimization"]["candidates"] == 4
        assert u["total_candidates"] == 16
        assert u["total_loc_savings_estimate"] == 62  # 0 (absorption) + 50 + 12
        assert u["files_absorbable_estimate"] == 3  # P0+P1


class TestHoundNextAction:
    """`next_action` dispatches by leverage: absorption-P0 first, then
    optimization-high, then absorption-P1, then fusion-subsume, then
    optimization-warning, then ad-hoc."""

    def test_absorption_p0_takes_precedence(self):
        unified = {
            "absorption": {"P0_count": 2, "P1_count": 5},
            "fusion": {"subsume_count": 8},
            "optimization": {"high_count": 1, "warning_count": 30},
        }
        action = _next_action(unified)
        assert action.startswith("absorption:")
        assert "P0" in action

    def test_optimization_high_beats_p1(self):
        unified = {
            "absorption": {"P0_count": 0, "P1_count": 5},
            "fusion": {"subsume_count": 0},
            "optimization": {"high_count": 3, "warning_count": 0},
        }
        action = _next_action(unified)
        assert action.startswith("optimization:")
        assert "dead code" in action

    def test_absorption_p1_beats_fusion_subsume(self):
        unified = {
            "absorption": {"P0_count": 0, "P1_count": 4},
            "fusion": {"subsume_count": 10},
            "optimization": {"high_count": 0, "warning_count": 0},
        }
        action = _next_action(unified)
        assert action.startswith("absorption:")
        assert "P1" in action

    def test_fusion_subsume_beats_optimization_warning(self):
        unified = {
            "absorption": {"P0_count": 0, "P1_count": 0},
            "fusion": {"subsume_count": 5},
            "optimization": {"high_count": 0, "warning_count": 20},
        }
        action = _next_action(unified)
        assert action.startswith("fusion:")

    def test_optimization_warning_when_nothing_else(self):
        unified = {
            "absorption": {"P0_count": 0, "P1_count": 0},
            "fusion": {"subsume_count": 0},
            "optimization": {"high_count": 0, "warning_count": 12},
        }
        action = _next_action(unified)
        assert action.startswith("optimization:")
        assert "warning" in action

    def test_clean_codebase_returns_no_dominant_scope(self):
        unified = {
            "absorption": {"P0_count": 0, "P1_count": 0},
            "fusion": {"subsume_count": 0},
            "optimization": {"high_count": 0, "warning_count": 0},
        }
        action = _next_action(unified)
        assert "clean" in action.lower() or "ad-hoc" in action


class TestHoundLiveTree:
    """Smoke test against the live mcp/noctusai/tools/noctus tree."""

    def test_live_tree_runs_without_error(self):
        r = scan(max_per_scope=5)
        # All three scopes should complete on the live tree.
        assert "absorption" in r["scopes_run"]
        assert "fusion" in r["scopes_run"]
        assert "optimization" in r["scopes_run"]
        assert r["errors"] == []
        assert r["next_action"]  # non-empty string
        assert r["unified"]["total_candidates"] >= 0
