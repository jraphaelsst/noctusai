"""`sync_ci_matrix_coverage` — the generator half of the CI test-matrix
coverage gate (`noctus.dev.refresh_ci_matrix_coverage`).

WHY (2026-08-13, found while building `dependabot_sync.py` per this doc's
"generalise if the evidence supports it" rule). `.github/workflows/test.yml`'s
`product-backend-tests` matrix covered 9/12 products — missing `igig` (17
test files), `orbity` (31), `seed` (6), every one with REAL, currently-
uncollected backend tests. `product-frontend-tests` covered 8/12, missing
`orbity` (real vitest specs); `knowledge-extractor`/`igig`/`products/seed`
are legitimately absent — none has a single `*.test.ts(x)` file, and
`vitest run` hard-fails on "no test files found" (the job's own comment
states the rule) — so the required-set predicate must be "has a spec file",
never "exists on disk".

→ KB § PATTERNS/devops/product-lockfile-and-slug-drift.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.ci_matrix_sync import sync_ci_matrix_coverage  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

_WORKFLOW = """\
name: Tests & Build

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main, dev]

concurrency:
  group: tests-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  product-backend-tests:
    # A load-bearing rationale comment that MUST survive every repair.
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
          - core

    steps:
      - uses: actions/checkout@v7
      - run: npm test

  trivy-fs-scan:
    name: Trivy filesystem scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
"""


def _write_workflow(root: Path, body: str = _WORKFLOW) -> Path:
    p = root / ".github" / "workflows" / "test.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _write_backend_tests(root: Path, slug: str, n: int = 1) -> None:
    tests_dir = root / "products" / slug / "backend" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (tests_dir / f"test_{i}.py").write_text("def test_x(): assert True\n")


def _write_frontend_spec(root: Path, slug: str) -> None:
    src_dir = root / "products" / slug / "frontend" / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "foo.test.ts").write_text("test('x', () => {});\n")


class TestMissingEntries:
    def test_adds_a_qualifying_backend_product(self, tmp_path):
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        _write_backend_tests(tmp_path, "igig")  # not in the matrix yet

        r = sync_ci_matrix_coverage(root=tmp_path)
        assert r["ok"] and r["status"] == "written"
        assert r["added"] == {"product-backend-tests": ["igig"]}

        text = (tmp_path / ".github" / "workflows" / "test.yml").read_text()
        assert "          - igig" in text

    def test_backend_only_product_does_not_join_frontend_matrix(self, tmp_path):
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        _write_backend_tests(tmp_path, "headless")  # no frontend spec files
        r = sync_ci_matrix_coverage(root=tmp_path)
        assert "product-frontend-tests" not in r["added"]

    def test_a_product_with_only_frontend_specs_joins_only_that_matrix(self, tmp_path):
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        _write_frontend_spec(tmp_path, "orbity")  # no backend tests dir
        r = sync_ci_matrix_coverage(root=tmp_path)
        assert r["added"] == {"product-frontend-tests": ["orbity"]}

    def test_vitest_config_alone_without_a_spec_file_does_not_qualify(self, tmp_path):
        # knowledge-extractor/igig/products-seed shape: vitest.config.ts
        # exists but zero *.test.ts(x) — must NOT be added (vitest run would
        # hard-fail on "no test files found").
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        src_dir = tmp_path / "products" / "ke" / "frontend" / "src"
        src_dir.mkdir(parents=True)
        (tmp_path / "products" / "ke" / "frontend" / "vitest.config.ts").write_text("export default {}")
        r = sync_ci_matrix_coverage(root=tmp_path)
        assert "product-frontend-tests" not in r["added"]

    def test_existing_comments_and_other_jobs_survive(self, tmp_path):
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        _write_backend_tests(tmp_path, "igig")
        sync_ci_matrix_coverage(root=tmp_path)
        text = (tmp_path / ".github" / "workflows" / "test.yml").read_text()
        assert "A load-bearing rationale comment that MUST survive" in text
        assert "trivy-fs-scan" in text


class TestStaleEntries:
    def test_stale_entry_reported_never_removed(self, tmp_path):
        # `erp-imobiliario` is in the matrix but has no backend tests dir.
        body = _WORKFLOW.replace("          - erp-imobiliario\n", "          - ghost\n")
        _write_workflow(tmp_path, body)
        _write_backend_tests(tmp_path, "core")
        r = sync_ci_matrix_coverage(root=tmp_path)
        assert r["stale"].get("product-backend-tests") == ["ghost"]
        text = (tmp_path / ".github" / "workflows" / "test.yml").read_text()
        assert "- ghost" in text  # never auto-removed


class TestIdempotent:
    def test_second_run_is_a_true_no_op(self, tmp_path):
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        _write_backend_tests(tmp_path, "igig")

        first = sync_ci_matrix_coverage(root=tmp_path)
        assert first["status"] == "written"
        after_first = (tmp_path / ".github" / "workflows" / "test.yml").read_text()

        second = sync_ci_matrix_coverage(root=tmp_path)
        assert second["status"] == "in-sync"
        assert (tmp_path / ".github" / "workflows" / "test.yml").read_text() == after_first

    def test_all_clean_from_the_start_is_in_sync(self, tmp_path):
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        r = sync_ci_matrix_coverage(root=tmp_path)
        assert r["ok"] and r["status"] == "in-sync" and r["changed"] is False


class TestDryRun:
    def test_dry_run_writes_nothing(self, tmp_path):
        _write_workflow(tmp_path)
        _write_backend_tests(tmp_path, "core")
        _write_backend_tests(tmp_path, "erp-imobiliario")
        _write_backend_tests(tmp_path, "igig")
        before = (tmp_path / ".github" / "workflows" / "test.yml").read_text()

        r = sync_ci_matrix_coverage(root=tmp_path, write=False)
        assert r["status"] == "would-write"
        assert r["added"] == {"product-backend-tests": ["igig"]}
        assert (tmp_path / ".github" / "workflows" / "test.yml").read_text() == before


class TestMissingFileIsAnHonestError:
    def test_no_workflow_file_is_error_not_crash(self, tmp_path):
        (tmp_path / "products").mkdir()
        r = sync_ci_matrix_coverage(root=tmp_path)
        assert r["ok"] is False and r["status"] == "error"


class TestRealRepoIsGreen:
    def test_real_repo_needs_no_write(self):
        """The live repo (this session's own fix) is fully covered — a second
        run must report in-sync, proving the generator is idempotent against
        the real file."""
        r = sync_ci_matrix_coverage(root=REPO, write=False)
        assert r["ok"], r
        assert r["added"] == {}, r["added"]
