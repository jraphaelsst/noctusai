"""Corpus accuracy guard for `outline_typescript`.

Two INDEPENDENT guards, split by what each one actually needs to say
something meaningful:

1. **Frozen-corpus baseline** (`TestFrozenCorpus*`) — measures the outliner
   ONLY against `tests/fixtures/outline_corpus/`, a small (~12-file)
   VENDORED snapshot of real `.ts`/`.tsx` shapes (functional components,
   hooks, a default-export entrypoint, arrow-fn components, class
   components, a re-export barrel — see that directory's README.md).
   This corpus is FROZEN: it changes only when someone deliberately updates
   it (new outliner shape to cover, or a fixture for a real outliner
   regression), never as a side effect of ordinary product-frontend work.
   Because the corpus never moves on its own, a baseline drift here is
   ALWAYS an outliner-regression signal, never legitimate feature growth —
   no re-ratification path is needed because the input itself doesn't
   change.

2. **Live-tree parse-success** (`TestLiveTreeParses`) — every `.ts`/`.tsx`
   file under `products/*/frontend/src/` must still outline WITHOUT a
   `parse_error`. This is a real safety net (a regex misfire in the
   outliner) and needs NO baseline / no symbol-count — it's a pure
   pass/fail per file, so it never drifts just because a product added a
   route or a hook. This is the one live-tree property worth keeping after
   freezing the corpus above.

Decided 2026-09-23: the baseline used to be measured against the LIVE
product tree, so any legitimate top-level-symbol change (a new lazy route,
a hook gaining a return value, a page split into sub-components) tripped
the ±5%/±1-symbol guard — 9 baseline-bump-only commits since 2026-08
(`225c1892f` "core main.tsx outline baseline 29→33", `47d34f189`,
`78bba2e03`, `32fb55fee`, `8cfd4e07a`, `06df43af5`, `b0e1fe32e`, ...) with
no sanctioned per-entry re-ratification path — the only documented refresh
was "delete the whole fixture and let it regenerate", which silently
absorbs every unrelated regression present at that moment (exactly the
corpus-wide regex drift the fixture exists to catch). See
`project-history/auto-improvement.ndjson` (2026-09-01 entry). Gates are
safety nets behind a mechanism, not walls agents collide with during
normal work — freezing the corpus removes the coupling to live product
code at the root instead of adding a re-ratification workaround on top of
it.

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
from tools.noctus.dev.product_scope import is_active


REPO_ROOT = Path(__file__).resolve().parents[3]
TS_EXTENSIONS = {".ts", ".tsx"}

# --- Frozen corpus (baseline-measuring guard) -------------------------------
CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "outline_corpus"
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

# --- Live tree (no-baseline parse-success safety net) ------------------------
LIVE_TREE_BASES = [REPO_ROOT / "products"]
SKIP_DIRS = {"node_modules", ".venv", "dist", "build", "playwright-report",
             "test-results", "__pycache__", "coverage", "e2e", ".backup"}


def _walk_frozen_corpus() -> list[Path]:
    if not CORPUS_DIR.exists():
        return []
    return sorted(
        p for p in CORPUS_DIR.rglob("*")
        if p.is_file() and p.suffix in TS_EXTENSIONS
    )


def _walk_live_tree() -> list[Path]:
    files: list[Path] = []
    for base in LIVE_TREE_BASES:
        if not base.exists():
            continue
        for p in base.rglob("*"):  # product-scope: active (filtered below)
            if not p.is_file():
                continue
            if p.suffix not in TS_EXTENSIONS:
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            # Only frontend SOURCE trees (production code). Excludes e2e
            # specs, playwright-report, etc. — those don't follow the
            # production patterns the outliner is calibrated for.
            if "/frontend/src/" not in str(p) + "/":
                continue
            # Co-located UNIT tests (`*.test.ts(x)` / `*.spec.ts(x)`) are not
            # production code: their top-level body is mostly `describe`/`it`
            # callbacks + `vi.fn()` mocks, so the outliner legitimately finds
            # near-zero declarations. The live-tree guard measures
            # PARSE-ability of product code; exclude tests (same rationale
            # as the e2e exclusion).
            if p.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
                continue
            # Test-runner setup (`src/test/setup.ts` etc.) is test infra, not
            # product code — polyfills and `vi.mock`s with no declarations
            # (same rationale).
            if "/frontend/src/test/" in str(p):
                continue
            # Asleep products (absent from deploy/fleet/active-scope.txt) are
            # out of every gate — their TS is not outlined until they wake.
            parts = p.relative_to(REPO_ROOT).parts
            if parts[0] == "products" and not is_active(parts[1], REPO_ROOT):
                continue
            files.append(p)
    return sorted(files)


@pytest.fixture(scope="module")
def frozen_corpus_files() -> list[Path]:
    files = _walk_frozen_corpus()
    if not files:
        pytest.skip(
            f"no TS / TSX files found in {CORPUS_DIR} — the frozen corpus "
            "fixture is missing or empty."
        )
    return files


@pytest.fixture(scope="module")
def frozen_corpus_results(frozen_corpus_files: list[Path]) -> dict[str, dict]:
    results = {}
    for f in frozen_corpus_files:
        rel = str(f.relative_to(CORPUS_DIR))
        outline = ot.outline_typescript(f)
        results[rel] = {
            "parse_error": outline.parse_error,
            "total_lines": outline.total_lines,
            "symbol_count": outline.symbol_count,
            "imports": len(outline.imports),
        }
    return results


@pytest.fixture(scope="module")
def live_tree_files() -> list[Path]:
    files = _walk_live_tree()
    if not files:
        pytest.skip("no TS / TSX files found in products/*/frontend/")
    return files


@pytest.mark.slow
class TestFrozenCorpusNoParseErrors:
    """Every file in the FROZEN corpus must outline cleanly (no regex
    misfire). Sanity check on the fixture itself — a broken fixture file
    would silently zero out the baseline test below."""

    def test_no_parse_errors(self, frozen_corpus_results: dict[str, dict]):
        bad = {p: r for p, r in frozen_corpus_results.items() if r["parse_error"]}
        assert not bad, (
            f"{len(bad)} file(s) in the frozen TS corpus parsed with errors: "
            f"{list(bad)[:5]}"
        )


@pytest.mark.slow
class TestFrozenCorpusSymbolCoverage:
    """Non-trivial frozen-corpus files (>20 lines, not a pure re-export)
    must expose ≥1 symbol. Empty results signal a regex regression."""

    def test_nontrivial_files_have_symbols(self, frozen_corpus_results: dict[str, dict]):
        empty: list[str] = []
        for path, r in frozen_corpus_results.items():
            if r["total_lines"] <= 20:
                continue
            # Pure re-export barrels are legitimately symbol-empty if they
            # only contain `export * from "…";` / `export { X } from "…";`
            # lines — those still register under `imports`. `imports > 0
            # and symbol_count == 0` is sufficient evidence on its own: the
            # outliner found nothing BUT import/re-export statements, so
            # there is nothing else the file could be. No line-count cap —
            # a barrel re-exporting many organs (e.g.
            # `seed/lib/frontend/src/components/index.ts`) is still a pure
            # barrel at 130 lines; an arbitrary size ceiling here produced a
            # false fire on exactly that legitimate shape (found 2026-09-23
            # while building the frozen outline corpus).
            if r["symbol_count"] == 0 and r["imports"] > 0:
                continue
            if r["symbol_count"] == 0:
                empty.append(path)
        assert not empty, (
            f"{len(empty)} non-trivial frozen-corpus file(s) outlined to zero "
            f"symbols: {empty[:5]}"
        )


@pytest.mark.slow
class TestFrozenCorpusBaselineSnapshot:
    """Per-file symbol count (of the FROZEN corpus only) must stay within
    ±5% **or** ±1 symbol (`ABS_SYMBOL_FLOOR`) of the recorded baseline,
    whichever is more permissive. First run captures the baseline if
    absent.

    Because the corpus is frozen (`tests/fixtures/outline_corpus/`, a
    vendored copy — never `products/**` live), any drift here comes ONLY
    from a change to the outliner itself. Bump the baseline in the same
    commit as a deliberate outliner change; it should never move on its
    own from unrelated product-frontend work.

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

    def test_within_tolerance_of_baseline(self, frozen_corpus_results: dict[str, dict]):
        if not BASELINE_FILE.exists():
            BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
            snapshot = {
                p: r["symbol_count"]
                for p, r in frozen_corpus_results.items()
            }
            BASELINE_FILE.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
            pytest.skip(
                f"baseline captured at {BASELINE_FILE}; re-run to enforce."
            )

        baseline: dict[str, int] = json.loads(BASELINE_FILE.read_text())
        regressions: list[str] = []
        for path, r in frozen_corpus_results.items():
            if path not in baseline:
                continue  # new fixture file — not a regression
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
            f"{len(regressions)} frozen-corpus file(s) drifted >{TOLERANCE:.0%} "
            f"AND >{ABS_SYMBOL_FLOOR} symbol(s) from baseline — this means the "
            "OUTLINER changed (the corpus itself is frozen), review + "
            "re-snapshot deliberately:\n  " + "\n  ".join(regressions[:10])
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


@pytest.mark.slow
class TestLiveTreeParses:
    """No-baseline safety net: every LIVE `products/*/frontend/src/`
    `.ts`/`.tsx` file must still outline without a `parse_error`. Pure
    pass/fail, no symbol-count comparison — so unlike the frozen-corpus
    baseline above, this one legitimately DOES scan the live, ever-changing
    product tree without ever drifting on ordinary feature work; it only
    fires on a genuine outliner regex misfire."""

    def test_no_parse_errors(self, live_tree_files: list[Path]):
        bad: dict[str, str] = {}
        for f in live_tree_files:
            outline = ot.outline_typescript(f)
            if outline.parse_error:
                bad[str(f.relative_to(REPO_ROOT))] = outline.parse_error
        assert not bad, (
            f"{len(bad)} live product file(s) parsed with errors: "
            f"{list(bad)[:5]}"
        )
