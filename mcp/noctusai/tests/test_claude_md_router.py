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
        big = "# CLAUDE.md\n\n" + ("filler " * 2600) + "\n## 1 · Universal rules\n\n## 2 · Map\n"
        self._write(tmp_path, big)
        issues = check_claude_md_router(repo_root=tmp_path)
        assert any("cap 2500" in i["issue"] for i in issues)

    def test_missing_file_no_crash(self, tmp_path):
        assert check_claude_md_router(repo_root=tmp_path) == []
