"""Tests for the cost-evaluation (token counting) tool."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import cost_evaluation as ce


class TestCountTokensInText:
    def test_empty_string(self):
        tokens, used = ce.count_tokens_in_text("")
        assert tokens == 0
        assert used in {"approximate-chars-per-4"} or used.startswith("tiktoken-")

    def test_short_string(self):
        tokens, used = ce.count_tokens_in_text("hello world")
        assert tokens >= 1
        # Approximation gives 11/4 ≈ 2; tiktoken gives 2 for "hello world".
        assert tokens <= 5

    def test_tokenizer_label_set(self):
        _, used = ce.count_tokens_in_text("test")
        assert used in {"approximate-chars-per-4"} or used.startswith("tiktoken-")


class TestCountTokensFile:
    def test_single_file(self, tmp_path):
        f = tmp_path / "sample.md"
        f.write_text("# Hello\n\nThis is a sample.\n")
        result = ce.count_tokens(str(f))
        assert result.file_count == 1
        assert result.total_tokens > 0
        assert result.total_chars == len(f.read_text())
        assert len(result.per_file) == 1
        assert result.per_file[0].path == str(f)
        assert result.per_file[0].tokens == result.total_tokens

    def test_missing_file_returns_empty_result(self, tmp_path):
        result = ce.count_tokens(str(tmp_path / "does-not-exist.md"))
        assert result.file_count == 0
        assert result.total_tokens == 0
        assert result.per_file == []

    def test_inline_text_only(self):
        result = ce.count_tokens(text="hello world this is inline")
        assert result.file_count == 0
        assert result.inline_text_tokens > 0
        assert result.total_tokens == result.inline_text_tokens

    def test_path_and_text_combined(self, tmp_path):
        f = tmp_path / "a.md"
        f.write_text("file content")
        result = ce.count_tokens(str(f), text="inline text too")
        assert result.file_count == 1
        assert result.inline_text_tokens > 0
        # Total = file tokens + inline tokens
        assert result.total_tokens >= result.inline_text_tokens
        assert result.total_tokens >= result.per_file[0].tokens

    def test_neither_path_nor_text_raises(self):
        with pytest.raises(ValueError):
            ce.count_tokens()


class TestCountTokensDirectory:
    def test_walks_directory_md_only(self, tmp_path):
        (tmp_path / "a.md").write_text("# A\nalpha\n")
        (tmp_path / "b.md").write_text("# B\nbeta\n")
        (tmp_path / "ignore.py").write_text("print('skipped')\n")
        result = ce.count_tokens(str(tmp_path))
        assert result.file_count == 2  # a.md, b.md — not ignore.py
        paths = sorted(fc.path for fc in result.per_file)
        assert all(p.endswith(".md") for p in paths)

    def test_extensions_override(self, tmp_path):
        (tmp_path / "a.md").write_text("# A\n")
        (tmp_path / "b.py").write_text("print('hi')\n")
        result = ce.count_tokens(str(tmp_path), extensions=(".py",))
        assert result.file_count == 1
        assert result.per_file[0].path.endswith(".py")

    def test_extensions_wildcard_includes_everything(self, tmp_path):
        (tmp_path / "a.md").write_text("a\n")
        (tmp_path / "b.txt").write_text("b\n")
        (tmp_path / "c.json").write_text('{"x": 1}\n')
        result = ce.count_tokens(str(tmp_path), extensions=("*",))
        assert result.file_count == 3

    def test_skip_dirs_excluded(self, tmp_path):
        (tmp_path / "real.md").write_text("real\n")
        nm = tmp_path / "node_modules" / "nested.md"
        nm.parent.mkdir()
        nm.write_text("vendored\n")
        result = ce.count_tokens(str(tmp_path))
        assert result.file_count == 1
        assert result.per_file[0].path.endswith("real.md")


class TestCountTokensGlob:
    def test_glob_expands(self, tmp_path, monkeypatch):
        # Anchor relative-to-cwd glob
        monkeypatch.chdir(tmp_path)
        (tmp_path / "doc-a.md").write_text("a\n")
        (tmp_path / "doc-b.md").write_text("b\n")
        (tmp_path / "other.md").write_text("c\n")
        result = ce.count_tokens("doc-*.md")
        assert result.file_count == 2


class TestResultSerialization:
    def test_to_dict_round_trip(self, tmp_path):
        f = tmp_path / "x.md"
        f.write_text("hello\n")
        result = ce.count_tokens(str(f))
        d = result.to_dict()
        assert d["file_count"] == 1
        assert d["tokenizer_used"]
        assert isinstance(d["per_file"], list)
        assert d["per_file"][0]["path"] == str(f)


class TestPerFileTokenizer:
    def test_per_file_tokenizer_label_matches_aggregate(self, tmp_path):
        """When tiktoken is present, every per-file count uses it; same when not."""
        f = tmp_path / "x.md"
        f.write_text("# Sample\n")
        result = ce.count_tokens(str(f))
        # The aggregate label should describe the same family as per-file labels.
        family_aggregate = result.tokenizer_used.split("-")[0]
        family_per_file = result.per_file[0].tokenizer.split("-")[0]
        assert family_aggregate == family_per_file
