"""Regression tests for engineer_output_linter."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import engineer_output_linter as eol  # noqa: E402


class TestLintReturn:
    def test_empty_input_fails(self):
        r = eol.lint_return("")
        assert r["ok"] is False
        assert set(r["missing"]) == {"drift-found", "scoped-improvement"}

    def test_both_legs_present_with_bullets(self):
        text = (
            "drift-found:\n"
            "  - the registration line got staged twice\n"
            "\n"
            "scoped-improvement:\n"
            "  - extracted the helper to a constant\n"
        )
        r = eol.lint_return(text)
        assert r["ok"] is True
        assert r["missing"] == []
        assert r["empty"] == []

    def test_both_legs_present_with_sentinel(self):
        text = (
            "drift-found:\n  none\n\n"
            "scoped-improvement:\n  N/A\n"
        )
        r = eol.lint_return(text)
        assert r["ok"] is True
        assert r["empty"] == []

    def test_missing_drift_found(self):
        text = (
            "scoped-improvement:\n  - the change cleaned up a redundant import\n"
        )
        r = eol.lint_return(text)
        assert r["ok"] is False
        assert "drift-found" in r["missing"]
        assert "scoped-improvement" not in r["missing"]

    def test_missing_scoped_improvement(self):
        text = (
            "drift-found:\n  - leftover token in another file\n"
        )
        r = eol.lint_return(text)
        assert r["ok"] is False
        assert "scoped-improvement" in r["missing"]

    def test_empty_section_flagged(self):
        text = (
            "drift-found:\n\n\n"
            "scoped-improvement:\n  - fixed inline\n"
        )
        r = eol.lint_return(text)
        # drift-found has no content + no sentinel → empty.
        assert "drift-found" in r["empty"] or r["ok"] is False

    def test_case_insensitive_headers(self):
        text = (
            "Drift-Found:\n  - X\n\n"
            "Scoped-Improvement:\n  - Y\n"
        )
        r = eol.lint_return(text)
        assert r["ok"] is True

    def test_bold_wrapping_tolerated(self):
        text = (
            "**drift-found:**\n  - x\n\n"
            "**scoped-improvement:**\n  - y\n"
        )
        r = eol.lint_return(text)
        assert r["ok"] is True

    def test_commit_msg_format_drift_warned(self):
        text = (
            "feat(foo): bar\n\nCo-Authored-By: somebody\n"
        )
        r = eol.lint_return(text)
        assert r["ok"] is False
        assert any("Co-Authored-By" in w for w in r["warnings"])


class TestSentinelDetection:
    @pytest.mark.parametrize("sentinel", ["none", "n/a", "(none)", "no drift", "nothing"])
    def test_sentinels_are_acceptable_empty(self, sentinel):
        text = (
            f"drift-found:\n  {sentinel}\n\n"
            f"scoped-improvement:\n  {sentinel}\n"
        )
        r = eol.lint_return(text)
        assert r["ok"] is True


class TestExtractSection:
    def test_extract_to_next_header(self):
        text = (
            "drift-found:\n  - first\n  - second\n\n"
            "scoped-improvement:\n  - third\n"
        )
        df_body = eol._extract_section(text, "drift-found")
        si_body = eol._extract_section(text, "scoped-improvement")
        assert "first" in df_body and "second" in df_body
        assert "third" not in df_body
        assert "third" in si_body

    def test_missing_section_returns_none(self):
        assert eol._extract_section("nothing here", "drift-found") is None
