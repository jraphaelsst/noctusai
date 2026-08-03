"""Regression tests for `check_memory_md_index` (sibling of TestClaudeMdRouter).

Per KB § PATTERNS/compliance/testing.md § Regression-test-the-detector. The colocated suite
the meta-detector `check_detector_has_regression_test` requires. Enforces the
v4.0 MEMORY-trim pattern (sibling of `KB § PATTERNS/common/claude-md-router-discipline.md`):
entry lines stay tight; whole-file under budget.

The keeper's DI seam (`home` parameter) lets us isolate the test from the real
~/.claude store: tests inject `home=tmp_path` so reads/writes never touch the
live agent-memory dir.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_memory_md_index  # noqa: E402


class TestMemoryMdIndex:
    @staticmethod
    def _setup(tmp_path: Path, content: str) -> tuple[Path, Path]:
        """Build an isolated (repo_root, home) pair and seed MEMORY.md at the
        keeper-derived path. tmp_path subtrees keep the test off the real ~/.claude."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        home = tmp_path / "home"
        encoded = str(repo_root).replace("/", "-")
        memdir = home / ".claude" / "projects" / encoded / "memory"
        memdir.mkdir(parents=True)
        (memdir / "MEMORY.md").write_text(content, encoding="utf-8")
        return repo_root, home

    def test_no_memory_dir_silent_skip(self, tmp_path):
        # Per-project memory not configured for this developer/fork → silent skip.
        assert check_memory_md_index(repo_root=tmp_path, home=tmp_path / "nohome") == []

    def test_clean_index_passes(self, tmp_path):
        repo_root, home = self._setup(
            tmp_path,
            "# MEMORY\n\n## Section\n- [Title](file.md) — short hook + KB § X.md.\n",
        )
        assert check_memory_md_index(repo_root=repo_root, home=home) == []

    def test_bloated_entry_flagged(self, tmp_path):
        bloated = "- [Title](file.md) — " + ("word " * 130) + "\n"
        assert len(bloated.rstrip("\n")) > 500
        repo_root, home = self._setup(tmp_path, bloated)
        issues = check_memory_md_index(repo_root=repo_root, home=home)
        assert any("bloated" in i["issue"] and "file.md" in i["issue"] for i in issues)
        assert all(i["severity"] == "high" for i in issues)

    def test_malformed_entry_flagged(self, tmp_path):
        repo_root, home = self._setup(tmp_path, "- [Bad entry without link\n")
        issues = check_memory_md_index(repo_root=repo_root, home=home)
        assert any("malformed" in i["issue"] for i in issues)

    def test_total_budget_flagged(self, tmp_path):
        # Derive the fixture size + expected cap from the live constant rather
        # than pinning a literal — the cap moved 60 → 20 KB on 2026-08-03 and a
        # hard-coded "cap 60 KB" would have gone stale silently. (Same lesson
        # the router test records for its own word cap.)
        from tools.noctus.dev.compliance import _MEMORY_MD_MAX_KB
        rows = (_MEMORY_MD_MAX_KB * 1024 // 24) + 200
        big = "# M\n" + "\n".join(f"- [t{i}](f{i}.md) — short" for i in range(rows)) + "\n"
        assert len(big.encode("utf-8")) > _MEMORY_MD_MAX_KB * 1024
        repo_root, home = self._setup(tmp_path, big)
        issues = check_memory_md_index(repo_root=repo_root, home=home)
        assert any(f"cap {_MEMORY_MD_MAX_KB} KB" in i["issue"] for i in issues)

    def test_budget_cap_sits_below_the_silent_read_cliff(self, tmp_path):
        """The cap must be BELOW ~24.4 KB, where the harness read returns nothing.

        This is the one assertion that makes the keeper meaningful rather than
        merely present. A cap ABOVE the cliff is worse than no cap: MEMORY.md
        would sail past the point where recall silently returns NOTHING while
        the gate still reported green — which is exactly what the old 60 KB cap
        did. → `KB § PATTERNS/common/memory-index-topic-split.md`
        """
        from tools.noctus.dev.compliance import _MEMORY_MD_MAX_KB
        assert _MEMORY_MD_MAX_KB < 24.4, (
            f"cap {_MEMORY_MD_MAX_KB} KB is at or above the ~24.4 KB silent-read "
            f"cliff — the gate would stay green through the failure it exists to "
            f"prevent"
        )

    def test_non_entry_lines_ignored(self, tmp_path):
        # Section headers, blanks, blockquotes, narrative prose: not entry lines.
        repo_root, home = self._setup(
            tmp_path,
            "# Header\n\n## Section\nfree prose line\n> warning blockquote\n# userEmail\nemail@x.com\n",
        )
        assert check_memory_md_index(repo_root=repo_root, home=home) == []
