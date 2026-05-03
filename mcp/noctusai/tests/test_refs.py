"""Tests for `tools/refs.py` — recursive reference finder."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.refs import find_refs


class TestFindRefs:
    def _mk_repo(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="refs_test_"))

    def test_finds_match_across_md_files(self):
        repo = self._mk_repo()
        (repo / "KNOWLEDGE-BASE" / "CONTEXT").mkdir(parents=True)
        (repo / "projects" / "foo").mkdir(parents=True)
        (repo / "KNOWLEDGE-BASE" / "CONTEXT" / "kb.md").write_text(
            "Some text mentioning my-pattern in a sentence.\nOther line.\n"
        )
        (repo / "projects" / "foo" / "PROJECT.md").write_text(
            "# Foo\n\nReferences my-pattern here.\n"
        )
        (repo / "unrelated.md").write_text("nothing here.\n")
        result = find_refs("my-pattern", repo_root=repo)
        assert result.total_matches == 2
        assert {m.file for m in result.matches} == {
            "KNOWLEDGE-BASE/CONTEXT/kb.md",
            "projects/foo/PROJECT.md",
        }

    def test_no_matches_returns_empty(self):
        repo = self._mk_repo()
        (repo / "a.md").write_text("nothing of interest")
        result = find_refs("xyz-not-there", repo_root=repo)
        assert result.total_matches == 0
        assert result.matches == []

    def test_empty_pattern_short_circuits(self):
        repo = self._mk_repo()
        (repo / "a.md").write_text("anything")
        result = find_refs("", repo_root=repo)
        assert result.total_matches == 0
        assert result.total_files == 0

    def test_skips_excluded_dirs(self):
        repo = self._mk_repo()
        (repo / "node_modules" / "lib").mkdir(parents=True)
        (repo / "node_modules" / "lib" / "a.js").write_text("contains target-pattern")
        (repo / "src").mkdir()
        (repo / "src" / "real.ts").write_text("contains target-pattern")
        result = find_refs("target-pattern", repo_root=repo)
        assert result.total_matches == 1
        assert result.matches[0].file == "src/real.ts"

    def test_skips_unscanned_extensions(self):
        repo = self._mk_repo()
        (repo / "a.png").write_text("ascii-target-pattern in a fake png")
        (repo / "b.md").write_text("real target-pattern hit")
        result = find_refs("target-pattern", repo_root=repo)
        assert result.total_matches == 1
        assert result.matches[0].file == "b.md"

    def test_to_dict_groups_by_file(self):
        repo = self._mk_repo()
        (repo / "x.md").write_text("hit-me\nother\nhit-me\n")
        result = find_refs("hit-me", repo_root=repo)
        d = result.to_dict()
        assert d["total_matches"] == 2
        assert "x.md" in d["matches_by_file"]
        assert len(d["matches_by_file"]["x.md"]) == 2
