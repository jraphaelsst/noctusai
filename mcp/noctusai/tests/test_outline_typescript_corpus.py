"""Corpus accuracy guard for `outline_typescript` against every TS / TSX
file under `products/*/frontend/src/`.

The TS regex backend claims ~95% accuracy on prettier/eslint-formatted
sources (`outline_typescript.py` module docstring). This corpus test pins
that claim:

1. **No `parse_error`** on any file in the corpus. A regex misfire that
   would set `parse_error` would itself signal a worse-than-95% problem.
2. **At least one symbol per non-trivial file** (>20 lines, not a pure
   re-export barrel). Empty results indicate the regex regressed against
   a syntax it used to handle.
3. **A baseline snapshot** — the per-file symbol count is captured to
   `tests/fixtures/outline_corpus_baseline.json`. Future runs must stay
   within ±5% per file (tolerance for legitimate symbol additions /
   removals during normal feature work).

Marked `@pytest.mark.slow` so the default suite stays fast.

References:
- `projects/mcp-ast-tools-hardening/PROJECT.md § Phase 2 — C.5`
- `projects/methodology-extraction/PROJECT.md § Phase 4` (the regex
  deviation from the §7 default Compiler API)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import outline_typescript as ot


REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS_GLOB_BASES = [
    REPO_ROOT / "products",
]
TS_EXTENSIONS = {".ts", ".tsx"}
SKIP_DIRS = {"node_modules", ".venv", "dist", "build", "playwright-report",
             "test-results", "__pycache__", "coverage", "e2e", ".backup"}
BASELINE_FILE = Path(__file__).resolve().parent / "fixtures" / "outline_corpus_baseline.json"
TOLERANCE = 0.05  # ±5% per file


def _walk_corpus() -> list[Path]:
    files: list[Path] = []
    for base in CORPUS_GLOB_BASES:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix not in TS_EXTENSIONS:
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            # Only frontend SOURCE trees (production code). Excludes e2e
            # specs, playwright-report, etc. — those don't follow the
            # production patterns the outliner is calibrated for.
            rel = str(p.relative_to(base))
            if "/frontend/src/" not in str(p) + "/":
                continue
            # Co-located UNIT tests (`*.test.ts(x)` / `*.spec.ts(x)`) are not
            # production code: their top-level body is mostly `describe`/`it`
            # callbacks + `vi.fn()` mocks, so the outliner legitimately finds
            # near-zero declarations — that trips `test_nontrivial_files_have_
            # symbols` and pollutes the baseline. The corpus measures PRODUCT
            # symbol coverage; exclude tests (same rationale as the e2e exclusion).
            if p.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
                continue
            files.append(p)
    return sorted(files)


@pytest.fixture(scope="module")
def corpus_files() -> list[Path]:
    files = _walk_corpus()
    if not files:
        pytest.skip("no TS / TSX files found in products/*/frontend/")
    return files


@pytest.fixture(scope="module")
def corpus_results(corpus_files: list[Path]) -> dict[str, dict]:
    results = {}
    for f in corpus_files:
        rel = str(f.relative_to(REPO_ROOT))
        outline = ot.outline_typescript(f)
        results[rel] = {
            "parse_error": outline.parse_error,
            "total_lines": outline.total_lines,
            "symbol_count": outline.symbol_count,
            "imports": len(outline.imports),
        }
    return results


@pytest.mark.slow
class TestCorpusNoParseErrors:
    """Every file in the corpus must outline cleanly (no regex misfire)."""

    def test_no_parse_errors(self, corpus_results: dict[str, dict]):
        bad = {p: r for p, r in corpus_results.items() if r["parse_error"]}
        assert not bad, (
            f"{len(bad)} file(s) in the TS corpus parsed with errors: "
            f"{list(bad)[:5]}"
        )


@pytest.mark.slow
class TestCorpusSymbolCoverage:
    """Non-trivial files (>20 lines, not pure re-export) must expose ≥1
    symbol. Empty results signal a regex regression."""

    def test_nontrivial_files_have_symbols(self, corpus_results: dict[str, dict]):
        empty: list[str] = []
        for path, r in corpus_results.items():
            if r["total_lines"] <= 20:
                continue
            # Pure re-export barrels are legitimately symbol-empty if they
            # only contain `export * from "…";` lines — those still register
            # under `imports`. Skip when total_lines is small AND imports > 0
            # AND symbol_count is 0.
            if r["symbol_count"] == 0 and r["imports"] > 0 and r["total_lines"] < 50:
                continue
            if r["symbol_count"] == 0:
                empty.append(path)
        assert not empty, (
            f"{len(empty)} non-trivial file(s) outlined to zero symbols: "
            f"{empty[:5]}"
        )


@pytest.mark.slow
class TestCorpusBaselineSnapshot:
    """Per-file symbol count must stay within ±5% of the recorded baseline.
    First run captures the baseline if absent."""

    def test_within_tolerance_of_baseline(self, corpus_results: dict[str, dict]):
        if not BASELINE_FILE.exists():
            BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
            snapshot = {
                p: r["symbol_count"]
                for p, r in corpus_results.items()
            }
            BASELINE_FILE.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
            pytest.skip(
                f"baseline captured at {BASELINE_FILE}; re-run to enforce."
            )

        baseline: dict[str, int] = json.loads(BASELINE_FILE.read_text())
        regressions: list[str] = []
        for path, r in corpus_results.items():
            if path not in baseline:
                continue  # new file — not a regression
            base = baseline[path]
            now = r["symbol_count"]
            if base == 0:
                continue
            delta = abs(now - base) / base
            if delta > TOLERANCE:
                regressions.append(
                    f"{path}: baseline={base} now={now} delta={delta:.1%}"
                )
        assert not regressions, (
            f"{len(regressions)} file(s) drifted >{TOLERANCE:.0%} from "
            f"baseline:\n  " + "\n  ".join(regressions[:10])
        )
