"""`check_seed_test_root_ci_coverage` — the gate that makes the seed's own
test suites impossible to leave uncollected.

WHY (2026-09-09). `seed/lib/backend` (3637 tests), `seed/framework/backend`
(203) and `seed/lib/frontend` (375) had NO CI job. Those three packages are
imported by every product backend and rendered by every product frontend, so
they were simultaneously the highest-blast-radius suites in the repo and the
only ones with no gate. All three passed on their first run — they were never
red, they were never asked.

The sibling `check_ci_test_matrix_coverage` exists for exactly this class and
could not see it: its required set comes from `_on_disk_products()`, i.e.
`products/*`, and `seed/lib` is not a product. A gate whose DOMAIN excludes
the gap is indistinguishable from no gate.

🔴 The test that carries the real weight is
`TestVisitingIsNotRunning::test_a_typecheck_only_step_does_not_count_as_coverage`.
`seed-typecheck.yml` had two steps whose `working-directory` was
`seed/lib/frontend` — running `npm run check` (tsc --noEmit). A coverage
predicate keyed on "does a workflow visit this directory" would have called
that root gated and stayed green over 375 uncollected tests. Coverage means a
step that RUNS the suite; if that assertion ever gets relaxed, the keeper
silently reverts to the shape that missed the original bug.

→ KB § PATTERNS/devops/product-lockfile-and-slug-drift.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_seed_test_root_ci_coverage  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

_COVERED_WORKFLOW = """\
name: Tests & Build

on:
  push:
    branches: [main, dev]

jobs:
  seed-backend-tests:
    name: Seed Backend Tests (pytest)
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        root:
          - seed/lib/backend
          - seed/framework/backend
    steps:
      - uses: actions/checkout@v7
      - name: Run tests
        working-directory: ${{ matrix.root }}
        run: pytest --tb=short -q

  seed-frontend-tests:
    name: Seed Frontend Tests (vitest)
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        root:
          - seed/lib/frontend
    steps:
      - uses: actions/checkout@v7
      - name: Run FE tests (vitest)
        working-directory: ${{ matrix.root }}
        run: npm test
"""

_TYPECHECK_ONLY_WORKFLOW = """\
name: Seed Typecheck

on:
  push:
    branches: [main, dev]

jobs:
  seed-lib-typecheck:
    name: Seed lib typecheck
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Install dependencies
        working-directory: seed/lib/frontend
        run: npm ci
      - name: Type-check (tsc --noEmit, strict)
        working-directory: seed/lib/frontend
        run: npm run check
"""


def _write_workflow(root: Path, body: str, name: str = "test.yml") -> Path:
    p = root / ".github" / "workflows" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _write_seed_backend_tests(root: Path, layer: str) -> None:
    d = root / "seed" / layer / "backend" / "tests"
    d.mkdir(parents=True, exist_ok=True)
    (d / "test_x.py").write_text("def test_x(): assert True\n")


def _write_seed_frontend_spec(root: Path, layer: str) -> None:
    d = root / "seed" / layer / "frontend" / "src"
    d.mkdir(parents=True, exist_ok=True)
    (d / "foo.test.ts").write_text("test('x', () => {});\n")


class TestCheckSeedTestRootCiCoverage:
    """The canonical `Test<detector>` name — `check_detector_has_regression_test`
    matches detectors to tests by class name, so this is the class that makes
    the keeper discoverable. It carries the true-positive shapes; the classes
    below pin the specific traps."""

    def test_flags_a_backend_root_with_tests_and_no_job(self, tmp_path):
        _write_workflow(tmp_path, _COVERED_WORKFLOW.replace("          - seed/lib/backend\n", ""))
        _write_seed_backend_tests(tmp_path, "lib")

        issues = check_seed_test_root_ci_coverage(tmp_path)
        hits = [i for i in issues if i["file"] == "seed/lib/backend"]
        assert len(hits) == 1, issues
        assert hits[0]["severity"] == "high"
        assert "pytest" in hits[0]["issue"]

    def test_flags_a_frontend_root_with_specs_and_no_job(self, tmp_path):
        _write_workflow(tmp_path, _TYPECHECK_ONLY_WORKFLOW)
        _write_seed_frontend_spec(tmp_path, "lib")

        issues = check_seed_test_root_ci_coverage(tmp_path)
        hits = [i for i in issues if i["file"] == "seed/lib/frontend"]
        assert len(hits) == 1, issues
        assert "vitest" in hits[0]["issue"]

    def test_the_original_three_gap_state_yields_three_findings(self, tmp_path):
        """The exact 2026-09-09 state: real suites, zero jobs."""
        _write_workflow(tmp_path, _TYPECHECK_ONLY_WORKFLOW)
        _write_seed_backend_tests(tmp_path, "lib")
        _write_seed_backend_tests(tmp_path, "framework")
        _write_seed_frontend_spec(tmp_path, "lib")

        issues = check_seed_test_root_ci_coverage(tmp_path)
        assert {i["file"] for i in issues} == {
            "seed/lib/backend",
            "seed/framework/backend",
            "seed/lib/frontend",
        }, issues


class TestVisitingIsNotRunning:
    def test_a_typecheck_only_step_does_not_count_as_coverage(self, tmp_path):
        """🔴 The assertion that encodes the actual bug. `seed-typecheck.yml`
        set `working-directory: seed/lib/frontend` on two steps and ran only
        `npm run check`. If this ever passes, the keeper has regressed to the
        predicate that missed 375 tests."""
        _write_workflow(tmp_path, _TYPECHECK_ONLY_WORKFLOW)
        _write_seed_frontend_spec(tmp_path, "lib")

        issues = check_seed_test_root_ci_coverage(tmp_path)
        assert [i["file"] for i in issues] == ["seed/lib/frontend"], (
            "a directory CI merely visits must never read as covered"
        )

    def test_a_pytest_step_does_not_cover_a_frontend_root(self, tmp_path):
        """Kind-specific: running pytest somewhere cannot satisfy a vitest root."""
        _write_workflow(tmp_path, """\
name: T
on: {push: {branches: [dev]}}
jobs:
  x:
    runs-on: ubuntu-latest
    steps:
      - name: Run tests
        working-directory: seed/lib/frontend
        run: pytest -q
""")
        _write_seed_frontend_spec(tmp_path, "lib")

        issues = check_seed_test_root_ci_coverage(tmp_path)
        assert [i["file"] for i in issues] == ["seed/lib/frontend"], issues


class TestCoveredIsClean:
    def test_matrix_expanded_roots_satisfy_the_gate(self, tmp_path):
        """`working-directory: ${{ matrix.root }}` is how the seed jobs address
        their roots, so the keeper has to expand it — an unexpanded template
        would make every seed job invisible and the gate permanently red."""
        _write_workflow(tmp_path, _COVERED_WORKFLOW)
        _write_seed_backend_tests(tmp_path, "lib")
        _write_seed_backend_tests(tmp_path, "framework")
        _write_seed_frontend_spec(tmp_path, "lib")

        assert check_seed_test_root_ci_coverage(tmp_path) == []

    def test_a_root_with_no_test_files_is_not_required(self, tmp_path):
        """`seed/framework/frontend` has zero specs today and is correctly
        absent from the matrix — `vitest run` hard-fails on "no test files
        found", so a root joins the gate the commit it gets its first spec.
        The predicate is "has >=1 test file", never "exists on disk"."""
        _write_workflow(tmp_path, _COVERED_WORKFLOW)
        _write_seed_backend_tests(tmp_path, "lib")
        _write_seed_backend_tests(tmp_path, "framework")
        _write_seed_frontend_spec(tmp_path, "lib")
        (tmp_path / "seed" / "framework" / "frontend" / "src").mkdir(parents=True)
        (tmp_path / "seed" / "framework" / "frontend" / "src" / "index.ts").write_text("export {};\n")

        assert check_seed_test_root_ci_coverage(tmp_path) == []

    def test_no_seed_dir_at_all_is_not_a_finding(self, tmp_path):
        _write_workflow(tmp_path, _COVERED_WORKFLOW)
        assert check_seed_test_root_ci_coverage(tmp_path) == []


class TestStaleEntry:
    def test_flags_a_job_running_a_seed_root_with_no_tests(self, tmp_path):
        _write_workflow(tmp_path, _COVERED_WORKFLOW)
        _write_seed_backend_tests(tmp_path, "lib")
        _write_seed_frontend_spec(tmp_path, "lib")
        # seed/framework/backend is in the matrix but has no tests on disk

        issues = check_seed_test_root_ci_coverage(tmp_path)
        hits = [i for i in issues if i["file"] == "seed/framework/backend"]
        assert len(hits) == 1, issues
        assert "stale" in hits[0]["issue"]


class TestLiveRepo:
    def test_the_real_repo_is_clean(self):
        """The gate must hold on the tree that ships it — otherwise the commit
        that adds the keeper also adds a standing failure."""
        assert check_seed_test_root_ci_coverage(REPO) == []
