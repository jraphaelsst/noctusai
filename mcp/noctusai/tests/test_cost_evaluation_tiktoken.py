"""Pin the tiktoken-active branch of `count_tokens`.

`tools/cost_evaluation.py` falls back to a chars/4 approximation when
`tiktoken` isn't importable. The audit (2026-05-02, mcp-ast-tools-hardening
Phase 0) found that the tiktoken branch was never actively exercised in
CI — `requirements.txt` didn't pin `tiktoken`, so the tokenizer label
test (`test_per_file_tokenizer_label_matches_aggregate`) ran against
the chars/4 fallback in every dev shell.

Phase 2 fix:
1. Pinned `tiktoken>=0.7.0` in requirements.txt + pyproject.toml.
2. This test: assert that when tiktoken IS importable (always, post-fix),
   the active tokenizer label is in the tiktoken family AND counts a
   known string to the tiktoken value (NOT chars/4).

Skips when tiktoken genuinely isn't installable (extreme edge case;
keeps the test honest if a future env can't install the lib).

References:
- `projects/mcp-ast-tools-hardening/PROJECT.md § Phase 2 — C.3`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import cost_evaluation as ce


tiktoken = pytest.importorskip("tiktoken")


class TestTiktokenBranchActive:
    def test_aggregate_label_starts_with_tiktoken(self, tmp_path: Path):
        """When tiktoken is installed, the cost_evaluation tool must
        report a tiktoken-family label, NOT 'approximate-chars-per-4'."""
        f = tmp_path / "a.md"
        f.write_text("hello world\n")
        result = ce.count_tokens(str(f))
        assert "approximate" not in result.tokenizer_used.lower(), (
            f"tiktoken installed but tool fell back to: "
            f"{result.tokenizer_used!r}"
        )
        # The label varies (e.g. 'tiktoken-cl100k_base') but must mention
        # tiktoken as the family.
        assert "tiktoken" in result.tokenizer_used.lower(), (
            f"unexpected tokenizer label: {result.tokenizer_used!r}"
        )

    def test_count_matches_tiktoken_directly(self, tmp_path: Path):
        """A known fixed string counted via the tool must match the
        same count produced by calling tiktoken directly. This locks
        that the tool isn't accidentally double-counting or stripping
        chars before tokenization."""
        sample = "The quick brown fox jumps over the lazy dog."
        f = tmp_path / "fox.txt"
        f.write_text(sample)
        # Tool count
        tool_result = ce.count_tokens(str(f))
        # Direct tiktoken count (cl100k_base = the default GPT-4-family
        # encoding; what the tool uses by default per cost_evaluation.py).
        enc = tiktoken.get_encoding("cl100k_base")
        direct = len(enc.encode(sample))
        assert tool_result.total_tokens == direct, (
            f"tool reported {tool_result.total_tokens} tokens; "
            f"direct tiktoken reported {direct} for same input."
        )

    def test_per_file_label_matches_aggregate(self, tmp_path: Path):
        """The aggregate label must match every per-file label when
        tiktoken is the active tokenizer."""
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        a.write_text("alpha\n")
        b.write_text("beta beta\n")
        result = ce.count_tokens(path=str(tmp_path), extensions=[".md"])
        assert result.file_count == 2
        for pf in result.per_file:
            assert pf.tokenizer == result.tokenizer_used, (
                f"per-file label {pf.tokenizer!r} != "
                f"aggregate {result.tokenizer_used!r}"
            )
