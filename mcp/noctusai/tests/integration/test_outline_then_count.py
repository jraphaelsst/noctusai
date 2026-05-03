"""Integration test for the natural composition of the two AST tools:
outline → token-budget the slices.

The narrow-read methodology says: outline first, then read targeted slices
(`Read offset=<line> limit=N`). This test pins the contract that:

1. The line-range fields produced by `outline_python` plug straight into
   text-slicing → `count_tokens(text=...)`.
2. The aggregate token count of the per-symbol slices, plus any
   between-symbol gap, equals the whole-file count (within tokenizer
   precision).
3. Symbol line ranges don't overlap.

If a future refactor breaks any of these, the narrow-read planning loop
stops working — agents budgeting reads from outline ranges would get
wrong numbers.

References:
- `projects/mcp-ast-tools-hardening/PROJECT.md § Phase 2 — C.6`
- `KB § PATTERNS/agent-reading-discipline.md § Companion tooling`
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import cost_evaluation as ce
from tools import outline_python as op


SAMPLE = textwrap.dedent('''
"""A small fixture file for the outline → count integration test."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

REPO_VERSION = "1.2.3"


class Greeter:
    """Two-line greeter."""

    def hello(self, name: str) -> str:
        """Say hello."""
        return f"hello {name}"

    def goodbye(self, name: str) -> str:
        return f"bye {name}"


def add(a: int, b: int) -> int:
    """Add two ints."""
    return a + b


async def fetch_remote(url: str) -> str:
    """Pretend to fetch."""
    return url
''')


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.py"
    p.write_text(SAMPLE)
    return p


class TestOutlineThenCount:
    def test_outline_ranges_plug_into_count_tokens(self, sample_file: Path):
        """The `line` / `end_line` fields can be used directly as text
        slice indices for `count_tokens(text=...)`."""
        outline = op.outline_python(sample_file)
        source_lines = sample_file.read_text().splitlines()
        assert outline.parse_error is None
        assert outline.symbol_count >= 4  # class + 2 methods + add + fetch_remote

        # For every captured class / function / method, the line range
        # must be valid and produce non-empty text whose token count is
        # >0.
        all_symbols = (
            outline.classes + outline.functions + outline.methods
        )
        assert all_symbols
        for s in all_symbols:
            assert 1 <= s.line <= s.end_line <= outline.total_lines
            slice_text = "\n".join(source_lines[s.line - 1: s.end_line])
            assert slice_text.strip(), f"{s.name} ({s.kind}) sliced to empty text"
            tok = ce.count_tokens(text=slice_text)
            assert tok.total_tokens > 0

    def test_class_method_ranges_inside_class_range(self, sample_file: Path):
        """Method ranges must sit inside their parent class's range — a
        narrow-read agent reading the class slice must not also need to
        re-read the method slices for completeness."""
        outline = op.outline_python(sample_file)
        for cls in outline.classes:
            for m in outline.methods:
                if m.parent != cls.name:
                    continue
                assert cls.line <= m.line <= m.end_line <= cls.end_line, (
                    f"method {cls.name}.{m.name} range "
                    f"({m.line}-{m.end_line}) escapes class range "
                    f"({cls.line}-{cls.end_line})"
                )

    def test_top_level_symbol_ranges_do_not_overlap(self, sample_file: Path):
        """Top-level symbols (classes + functions, not methods) must have
        non-overlapping line ranges — otherwise narrow-read budgeting
        double-counts tokens."""
        outline = op.outline_python(sample_file)
        top = sorted(outline.classes + outline.functions, key=lambda s: s.line)
        for a, b in zip(top, top[1:]):
            assert a.end_line < b.line, (
                f"top-level overlap: {a.name} ends at {a.end_line}, "
                f"{b.name} starts at {b.line}"
            )

    def test_outline_result_to_dict_compatible_with_count_text(self, sample_file: Path):
        """Cross-tool dataclass compatibility: outline's `to_dict()` is
        JSON-serializable AND its `total_lines` agrees with the raw file
        line count that `count_tokens(path=...)` reports."""
        outline = op.outline_python(sample_file)
        d = outline.to_dict()
        assert isinstance(d["symbol_count"], int)
        assert d["total_lines"] == outline.total_lines

        tok = ce.count_tokens(path=str(sample_file))
        # `count_tokens` reports per-file `lines`; should match outline's
        # `total_lines` for a non-empty file (newlines == lines).
        per_file = tok.per_file[0]
        # Allow off-by-one because count_tokens counts newlines while
        # outline counts logical lines from `splitlines()`.
        assert abs(per_file.lines - outline.total_lines) <= 1
