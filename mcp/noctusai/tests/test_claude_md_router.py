"""Regression tests for `check_claude_md_router`.

Per `KB § PATTERNS/compliance/testing.md § Regression-test-the-detector` — the colocated
suite the meta-detector `check_detector_has_regression_test` requires.
Enforces the v4.0 CLAUDE.md router pattern (KB § PATTERNS/common/claude-md-router-discipline.md):
§1 rules are one-line (rule + `→` pointer, no inlined bodies); whole file under budget.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_claude_md_router  # noqa: E402


class TestClaudeMdRouter:
    @staticmethod
    def _write(tmp_path: Path, body: str) -> Path:
        (tmp_path / "CLAUDE.md").write_text(body, encoding="utf-8")
        return tmp_path

    def test_clean_router_passes(self, tmp_path):
        self._write(
            tmp_path,
            "# CLAUDE.md\n\n## 1 · Universal rules\n\n"
            "- **Seed first.** Inherit via the factories. → `KB § 03-SEED-ARCHITECTURE.md`\n"
            "- **No silent errors.** Surface, never swallow. → `KB § 01-PHILOSOPHY.md`\n\n"
            "## 2 · Map\n\nstuff\n",
        )
        assert check_claude_md_router(repo_root=tmp_path) == []

    def test_rule_without_pointer_flagged(self, tmp_path):
        self._write(
            tmp_path,
            "## 1 · Universal rules\n\n"
            "- **Seed first.** Inherit via the factories everywhere.\n\n"
            "## 2 · Map\n",
        )
        issues = check_claude_md_router(repo_root=tmp_path)
        assert any("pointer" in i["issue"] for i in issues)
        assert all(i["severity"] == "high" for i in issues)

    def test_inlined_prose_body_flagged(self, tmp_path):
        self._write(
            tmp_path,
            "## 1 · Universal rules\n\n"
            "- **Seed first.** Inherit via the factories. → `KB § x.md`\n"
            "This is an inlined prose body line that re-bloats the contract.\n\n"
            "## 2 · Map\n",
        )
        issues = check_claude_md_router(repo_root=tmp_path)
        assert any("prose body" in i["issue"] for i in issues)

    def test_overlong_rule_flagged(self, tmp_path):
        long_rule = "- **Bloat.** " + ("word " * 70) + "→ `KB § x.md`\n"
        self._write(tmp_path, "## 1 · Universal rules\n\n" + long_rule + "\n## 2 · Map\n")
        issues = check_claude_md_router(repo_root=tmp_path)
        assert any("words (cap" in i["issue"] for i in issues)

    def test_total_budget_flagged(self, tmp_path):
        # Derive the fixture size + expected cap from the live constant so this
        # test survives a cap change (raised 2500→3500 2026-07-22) instead of
        # pinning a stale literal — the exact drift this session codified against.
        from tools.noctus.dev.compliance import _CLAUDE_MD_MAX_WORDS
        big = "# CLAUDE.md\n\n" + ("filler " * (_CLAUDE_MD_MAX_WORDS + 100)) + "\n## 1 · Universal rules\n\n## 2 · Map\n"
        self._write(tmp_path, big)
        issues = check_claude_md_router(repo_root=tmp_path)
        assert any(f"cap {_CLAUDE_MD_MAX_WORDS}" in i["issue"] for i in issues)

    def test_missing_file_no_crash(self, tmp_path):
        assert check_claude_md_router(repo_root=tmp_path) == []

    # ── §1 rule-COUNT ceiling (2026-08-03 harness-audit re-author) ──────────
    #
    # The regression these guard is subtle: §1 grew 72 → 79 always-on rules
    # while this very keeper stayed green, because invariants 1-3 gate the
    # SHAPE of each rule and nothing gated their NUMBER. The fixtures below
    # are therefore built from rules that are individually PERFECT — one line,
    # a `→` pointer, well under the word cap — so the only thing that can fire
    # is the count ceiling itself.

    @staticmethod
    def _rules(n: int) -> str:
        return "\n".join(
            f"- **Rule {i}.** A short well-formed reason. → `KB § 01-PHILOSOPHY.md`"
            for i in range(n)
        )

    def test_rule_count_at_cap_passes(self, tmp_path):
        from tools.noctus.dev.compliance import _CLAUDE_MD_MAX_S1_RULES
        self._write(
            tmp_path,
            "# CLAUDE.md\n\n## 1 · Universal rules\n\n"
            + self._rules(_CLAUDE_MD_MAX_S1_RULES)
            + "\n\n## 2 · Map\n",
        )
        issues = check_claude_md_router(repo_root=tmp_path)
        assert not any("always-on rules" in i["issue"] for i in issues)

    def test_rule_count_over_cap_flagged(self, tmp_path):
        from tools.noctus.dev.compliance import _CLAUDE_MD_MAX_S1_RULES
        over = _CLAUDE_MD_MAX_S1_RULES + 1
        self._write(
            tmp_path,
            "# CLAUDE.md\n\n## 1 · Universal rules\n\n"
            + self._rules(over)
            + "\n\n## 2 · Map\n",
        )
        issues = check_claude_md_router(repo_root=tmp_path)
        count_issues = [i for i in issues if "always-on rules" in i["issue"]]
        assert len(count_issues) == 1
        # Every rule is individually legal — nothing else may fire, or the
        # fixture is testing the shape gates by accident.
        assert issues == count_issues
        assert f"{over} always-on rules" in count_issues[0]["issue"]
        # The remedy must be named, not just the violation: an over-cap §1 is
        # a consolidation trigger, NOT a cue to trim words or raise the cap.
        assert "family" in count_issues[0]["issue"].lower()

    def test_rule_count_ignores_prose_and_quotes(self, tmp_path):
        """Blockquotes / `---` / blanks are not rules and must not be counted."""
        from tools.noctus.dev.compliance import _CLAUDE_MD_MAX_S1_RULES
        body = (
            "# CLAUDE.md\n\n## 1 · Universal rules\n\n"
            "> a framing blockquote\n\n---\n\n"
            + self._rules(_CLAUDE_MD_MAX_S1_RULES)
            + "\n\n## 2 · Map\n"
        )
        self._write(tmp_path, body)
        issues = check_claude_md_router(repo_root=tmp_path)
        assert not any("always-on rules" in i["issue"] for i in issues)
