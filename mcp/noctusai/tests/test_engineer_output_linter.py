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
            "  - the registration line got staged twice [fixed abc1234]\n"
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
            "drift-found:\n  - leftover token in another file [fixed abc1234]\n"
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
            "Drift-Found:\n  - X [fixed abc1234]\n\n"
            "Scoped-Improvement:\n  - Y\n"
        )
        r = eol.lint_return(text)
        assert r["ok"] is True

    def test_bold_wrapping_tolerated(self):
        text = (
            "**drift-found:**\n  - x [fixed abc1234]\n\n"
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
            "drift-found:\n  - first [fixed abc1234]\n  - second [fixed abc1234]\n\n"
            "scoped-improvement:\n  - third\n"
        )
        df_body = eol._extract_section(text, "drift-found")
        si_body = eol._extract_section(text, "scoped-improvement")
        assert "first" in df_body and "second" in df_body
        assert "third" not in df_body
        assert "third" in si_body

    def test_missing_section_returns_none(self):
        assert eol._extract_section("nothing here", "drift-found") is None


def _ft(bullets: str) -> str:
    return f"drift-found:\n{bullets}\n\nscoped-improvement:\n  - none\n"


class TestOutcomeTags:
    @pytest.mark.parametrize("tag", [
        "[fixed abc1234]",
        "[fixing \u2192 feat/fix-thing]",
        "[fixing -> feat/fix-thing]",
        "[deferred \u2192 NOC-REMEDIATE[tunnel-cli] because needs a CLI flag design]",
        "[deferred \u2192 project-history/roadmaps/x.md because multi-session work]",
        "[deferred \u2192 MEMORY-reminders because owner must approve spend]",
        "[deferred \u2192 owner-decision because pick a vendor first]",
    ])
    def test_valid_tag_forms(self, tag):
        r = eol.lint_return(_ft(f"  - something broke in a/b.py {tag}"))
        assert r["ok"] is True, r
        assert r["untagged"] == []

    @pytest.mark.parametrize("bullet", [
        "  - bare drift with no tag",
        "  - garbled [fixd abc1234]",
        "  - short sha [fixed ab]",
        "  - fixing no branch [fixing \u2192 somewhere]",
        "  - no destination [deferred because it is hard to do right now]",
        "  - unknown destination [deferred \u2192 later because it is hard to do]",
        "  - short reason [deferred \u2192 owner-decision because no]",
    ])
    def test_refused(self, bullet):
        r = eol.lint_return(_ft(bullet))
        assert r["ok"] is False
        assert len(r["untagged"]) == 1
        assert "expected_tag_shape" in r

    @pytest.mark.parametrize("bullet", [
        "  - [fixed a972dc780] docstring did not describe the lane",
        "  - [fixing \u2192 feat/x-y] the thing",
        "  - [deferred \u2192 NOC-REMEDIATE[mq-area-map-dedup] because it rides that follow-up] the docstring",
    ])
    def test_a_leading_tag_counts(self, bullet):
        assert eol.lint_return(_ft(bullet))["ok"] is True

    def test_the_refusal_says_where_the_tag_goes(self):
        assert "END" in eol.lint_return(_ft("  - bare"))["expected_tag_shape"]

    def test_none_allowed(self):
        assert eol.lint_return(_ft("  - none"))["ok"] is True

    def test_improvement_tag_optional(self):
        t = "drift-found:\n  - none\n\nscoped-improvement:\n  - did a thing\n"
        assert eol.lint_return(t)["ok"] is True

    def test_parse_outcome_tag_fields(self):
        t = eol.parse_outcome_tag("x [deferred \u2192 owner-decision because pick a vendor first]")
        assert t["outcome"] == "deferred" and t["reason"] == "pick a vendor first"
        assert eol.parse_outcome_tag("x [fixed abc1234]") == {"outcome": "fixed", "ref": "abc1234"}
