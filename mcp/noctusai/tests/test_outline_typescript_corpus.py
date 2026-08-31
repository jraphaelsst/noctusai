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
   within ±5% **OR** ±1 symbol per file, whichever is more permissive
   (tolerance for legitimate symbol additions / removals during normal
   feature work).

   Decided 2026-08-31, after repeated false fires on small files: a
   RELATIVE-ONLY tolerance is wrong at small symbol counts — one
   legitimate export added to a 4-symbol file is a 25% move, well past
   ±5%, so the guard fired hardest on exactly the files it has the
   least statistical basis to say anything about. The intent of this
   test is to catch a CORPUS-WIDE regex regression (the regex backend
   silently stops recognizing a syntax shape across many files), not to
   gate a single-symbol edit on one small file — an absolute ±1-symbol
   floor lets that legitimate case through while the relative ±5% rule
   still catches genuine multi-symbol regressions on files of any size
   (see `test_within_tolerance_of_baseline`'s docstring for the
   two-sided proof: a 1-symbol move on a small file passes, a
   multi-symbol regression on that same small file still fails).

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
# Absolute floor, decided 2026-08-31: a delta passes if it is within
# TOLERANCE *or* within ABS_SYMBOL_FLOOR symbols, whichever is more
# permissive. Relative-only tolerance is wrong for small files — one
# legitimate export on a 4-symbol file is a 25% move, well past ±5%, so a
# relative-only guard fires hardest on the files it has least basis to
# judge. The absolute floor targets what this test actually cares about
# (a corpus-wide regex regression), not a single legitimate symbol edit.
# Large files keep the ±5% behaviour unchanged since a 1-symbol floor is
# already looser there than 5% of a large count.
ABS_SYMBOL_FLOOR = 1


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
    """Per-file symbol count must stay within ±5% **or** ±1 symbol
    (`ABS_SYMBOL_FLOOR`) of the recorded baseline, whichever is more
    permissive. First run captures the baseline if absent.

    Relative-OR-absolute, not relative-only (decided 2026-08-31): a
    1-symbol move on a small file (e.g. 4 -> 5 symbols, a 25% relative
    delta) now PASSES via the absolute floor, while a genuine
    multi-symbol regression on that same small file (e.g. 4 -> 2, also
    within the floor's raw magnitude but a real corpus-signal drop)
    still FAILS because ±1 alone doesn't cover it AND the relative ±5%
    doesn't either. See `test_absolute_floor_passes_single_symbol_move`
    and `test_multi_symbol_regression_still_fails` below for both halves
    proven directly against this same comparison logic.
    """

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
            if _within_tolerance(base, now):
                continue
            delta = abs(now - base) / base
            regressions.append(
                f"{path}: baseline={base} now={now} delta={delta:.1%}"
            )
        assert not regressions, (
            f"{len(regressions)} file(s) drifted >{TOLERANCE:.0%} AND "
            f">{ABS_SYMBOL_FLOOR} symbol(s) from baseline:\n  "
            + "\n  ".join(regressions[:10])
        )


def _within_tolerance(base: int, now: int) -> bool:
    """A baseline->now move passes if it's within the RELATIVE tolerance
    OR the ABSOLUTE symbol floor — whichever is more permissive. Shared
    by the corpus test and its two direct unit tests below so the unit
    tests exercise the EXACT comparison the corpus test uses, not a
    hand-copied re-implementation that could drift from it.
    """
    if base == 0:
        return True  # pre-existing guard: nothing to compare against
    delta = abs(now - base) / base
    abs_delta = abs(now - base)
    return delta <= TOLERANCE or abs_delta <= ABS_SYMBOL_FLOOR


class TestAbsoluteFloorDecision:
    """Direct, non-corpus proof of the 2026-08-31 relative-OR-absolute
    decision — both halves matter, the second more than the first (a
    tolerance that never fires is not a guard)."""

    def test_absolute_floor_passes_single_symbol_move(self):
        """A 1-symbol move on a small file (4 -> 5, a 25% relative delta —
        well past ±5%) passes because it's within the ±1 absolute floor.
        This is the exact false-fire shape that cost a ratification
        commit (32fb55fe) before this fix."""
        assert _within_tolerance(base=4, now=5) is True
        assert _within_tolerance(base=4, now=3) is True

    def test_multi_symbol_regression_still_fails(self):
        """A genuine multi-symbol regression on that SAME small file (4 -> 2,
        a 50% relative delta AND a 2-symbol absolute move) still fails —
        the absolute floor does not swallow a real corpus-signal drop just
        because the file is small."""
        assert _within_tolerance(base=4, now=2) is False
        # And the relative ±5% rule is unchanged for large files.
        assert _within_tolerance(base=200, now=250) is False  # +25%, no floor rescue at this scale
        assert _within_tolerance(base=200, now=208) is True   # +4%, within ±5%
