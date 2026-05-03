"""Performance pin for `outline_python` on a 2,000-line synthetic source.

The narrow-read methodology only works if outline calls are CHEAP — agents
treat them as "free" relative to whole-file Reads. This test asserts that
outlining a 2,000-line Python source file completes in ≤500ms median over
5 runs. Stdlib `ast.parse` typically does this in <100ms; 500ms is the
slack for CI noise + parse-tree walking.

A regression here means the implementation accidentally went superlinear.
The expectation is to stay well under the cap; if this test starts failing,
investigate (don't ratchet the cap up without finding the cause).

Marked `@pytest.mark.slow` so the default suite stays fast.

References:
- `projects/mcp-ast-tools-hardening/PROJECT.md § Phase 2 — C.8`
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import outline_python as op


def _build_synthetic_source(num_classes: int, methods_per_class: int) -> str:
    """Roughly num_classes * (methods_per_class + 5) lines."""
    parts = [
        '"""Synthetic source for benchmark."""',
        "from __future__ import annotations",
        "",
        "import logging",
        "from dataclasses import dataclass",
        "from typing import Optional",
        "",
        "REPO_VERSION = '0.0.0'",
        "logger = logging.getLogger(__name__)",
        "",
    ]
    for c in range(num_classes):
        parts.append(f"class GeneratedClass{c}:")
        parts.append(f'    """Doc for class {c}."""')
        parts.append("    field_a: int = 0")
        parts.append("    field_b: str = ''")
        parts.append("")
        for m in range(methods_per_class):
            parts.append(f"    def method_{m}(self, x: int) -> int:")
            parts.append(f'        """Method {m}."""')
            parts.append("        return x + 1")
            parts.append("")
        parts.append("")
    parts.append("")
    parts.append("def top_level_helper(value: int) -> int:")
    parts.append('    """Top-level."""')
    parts.append("    return value * 2")
    return "\n".join(parts)


@pytest.mark.slow
class TestOutlinePythonBenchmark:
    def test_outline_2000_line_source_under_500ms_median(self, tmp_path: Path):
        # Generate ~2,000 lines: 100 classes * 18 lines each ≈ 1,800 + header
        source = _build_synthetic_source(num_classes=100, methods_per_class=4)
        target = tmp_path / "synthetic_large.py"
        target.write_text(source)
        line_count = source.count("\n") + 1
        assert line_count >= 1500, f"synthetic file too small: {line_count} lines"

        # Warm-up + 5 timed runs
        op.outline_python(target)
        times: list[float] = []
        for _ in range(5):
            start = time.perf_counter()
            result = op.outline_python(target)
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            assert result.parse_error is None
            assert result.symbol_count >= 100  # 100 classes minimum
        median = statistics.median(times)
        assert median < 0.5, (
            f"outline_python median wall-clock for {line_count}-line file: "
            f"{median * 1000:.1f}ms (cap: 500ms). Investigate before "
            f"ratcheting the cap. Times: "
            f"{[f'{t * 1000:.0f}ms' for t in times]}"
        )
