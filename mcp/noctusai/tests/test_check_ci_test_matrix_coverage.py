"""`check_ci_test_matrix_coverage` — the keeper (backstop) half of the CI
test-matrix coverage gate.

WHY (2026-08-13, found while building the dependabot gate). `igig` (17
backend test files), `orbity` (31), and `seed` (6) were never in
`product-backend-tests`'s matrix; `orbity`'s real vitest specs were never in
`product-frontend-tests`'s. Every one of those products' tests silently never
ran in CI. Companion generator: `noctus.dev.refresh_ci_matrix_coverage`
(`ci_matrix_sync.py`, `test_ci_matrix_sync.py`).

→ KB § PATTERNS/devops/product-lockfile-and-slug-drift.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_ci_test_matrix_coverage  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

_WORKFLOW = """\
name: Tests & Build

on:
  push:
    branches: [main, dev]

jobs:
  product-backend-tests:
    name: Product Backend Tests (pytest)
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        product:
          - core
          - erp-imobiliario

    steps:
      - uses: actions/checkout@v7
      - run: pytest --tb=short -q

  product-frontend-tests:
    name: Product Frontend Tests (vitest)
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        product:

    steps:
      - uses: actions/checkout@v7
      - run: npm test
"""


def _write_workflow(root: Path, body: str = _WORKFLOW) -> Path:
    p = root / ".github" / "workflows" / "test.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _write_backend_tests(root: Path, slug: str) -> None:
    tests_dir = root / "products" / slug / "backend" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_x.py").write_text("def test_x(): assert True\n")


def _write_frontend_spec(root: Path, slug: str) -> None:
    src_dir = root / "products" / slug / "frontend" / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "foo.test.ts").write_text("test('x', () => {});\n")


class TestMissingQualifyingProduct:
    def test_flags_a_backend_product_with_real_tests_not_in_the_matrix(self, tmp_path):
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        _write_backend_tests(tmp_path, "igig")

        issues = check_ci_test_matrix_coverage(tmp_path)
        hits = [i for i in issues if i["product"] == "igig"]
        assert len(hits) == 1, issues
        assert hits[0]["severity"] == "high"
        assert "product-backend-tests" in hits[0]["issue"]

    def test_flags_a_frontend_product_with_real_specs_not_in_the_matrix(self, tmp_path):
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        _write_frontend_spec(tmp_path, "orbity")

        issues = check_ci_test_matrix_coverage(tmp_path)
        hits = [i for i in issues if i["product"] == "orbity"]
        assert len(hits) == 1, issues
        assert "product-frontend-tests" in hits[0]["issue"]

    def test_product_with_vitest_config_but_no_spec_file_is_not_flagged(self, tmp_path):
        # knowledge-extractor/igig/products-seed shape — vitest.config.ts
        # exists, zero *.test.ts(x). Legitimately absent from the matrix.
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        fe = tmp_path / "products" / "ke" / "frontend"
        (fe / "src").mkdir(parents=True)
        (fe / "vitest.config.ts").write_text("export default {}")
        issues = check_ci_test_matrix_coverage(tmp_path)
        assert issues == [], issues


class TestStaleEntry:
    def test_flags_a_matrix_entry_with_no_qualifying_tests(self, tmp_path):
        body = _WORKFLOW.replace("          - erp-imobiliario\n", "          - ghost\n")
        _write_workflow(tmp_path, body)
        _write_backend_tests(tmp_path, "core")
        issues = check_ci_test_matrix_coverage(tmp_path)
        hits = [i for i in issues if i["product"] == "ghost"]
        assert len(hits) == 1, issues
        assert "stale" in hits[0]["issue"] or "no longer" in hits[0]["issue"]


class TestCheckCiTestMatrixCoverage:
    """Named for `check_detector_has_regression_test`'s `Test<CamelCase>`
    heuristic — a real true-positive/false-positive pair, not a rubber stamp
    (the finer-grained classes above are the detailed pins)."""

    def test_true_positive_qualifying_product_missing_from_matrix(self, tmp_path):
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        _write_backend_tests(tmp_path, "orbity")
        issues = check_ci_test_matrix_coverage(tmp_path)
        assert any(i["product"] == "orbity" for i in issues)

    def test_false_positive_fully_covered_is_clean(self, tmp_path):
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        assert check_ci_test_matrix_coverage(tmp_path) == []


class TestAllClean:
    def test_all_clean_case_zero_issues(self, tmp_path):
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        assert check_ci_test_matrix_coverage(tmp_path) == []

    def test_no_workflow_file_no_crash_no_flag(self, tmp_path):
        _write_backend_tests(tmp_path, "core")
        assert check_ci_test_matrix_coverage(tmp_path) == []

    def test_no_products_dir_no_crash(self, tmp_path):
        # No `products/` dir at all — every existing matrix entry is
        # legitimately stale (nothing on disk can qualify), which is a
        # correct finding, not a crash. Assert only that it doesn't raise.
        _write_workflow(tmp_path)
        issues = check_ci_test_matrix_coverage(tmp_path)
        assert isinstance(issues, list)


class TestRealRepoIsGreen:
    def test_real_repo_has_zero_ci_matrix_coverage_drift(self):
        issues = check_ci_test_matrix_coverage(REPO)
        assert issues == [], issues


class TestCatchesTheHistoricalBug:
    """Reconstructs the pre-fix test.yml state (missing igig/orbity/seed
    backend + orbity frontend) against synthetic products with REAL test
    files, and proves the detector fires on it."""

    def test_pre_fix_state_is_flagged_post_fix_state_is_not(self, tmp_path):
        backend_covered = ("core", "erp-imobiliario")
        backend_missing = ("igig", "orbity", "seed")

        _write_workflow(tmp_path)
        for s in backend_covered + backend_missing:
            _write_backend_tests(tmp_path, s)
        _write_frontend_spec(tmp_path, "orbity")

        pre_fix = check_ci_test_matrix_coverage(tmp_path)
        pre_fix_products = {i["product"] for i in pre_fix}
        assert pre_fix_products == {"igig", "orbity", "seed"}, pre_fix

        fixed_body = _WORKFLOW.replace(
            "          - erp-imobiliario\n",
            "          - erp-imobiliario\n          - igig\n          - orbity\n          - seed\n",
        ).replace(
            "        product:\n\n    steps:\n      - uses: actions/checkout@v7\n      - run: npm test\n",
            "        product:\n          - orbity\n\n    steps:\n      - uses: actions/checkout@v7\n      - run: npm test\n",
        )
        _write_workflow(tmp_path, fixed_body)
        assert check_ci_test_matrix_coverage(tmp_path) == []
