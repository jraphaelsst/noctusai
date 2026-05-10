"""Tests for analyzer tools."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.analyzers import (
    find_duplicated_functions, find_inline_hooks,
    audit_python_deps, analyze_test_coverage, get_code_metrics,
    run_all_analyzers,
)


class TestPatternFinder:
    def test_finds_duplicated_functions(self):
        dups = find_duplicated_functions()
        # There should be some duplicated function names across products
        assert isinstance(dups, list)
        for d in dups:
            assert "function" in d
            assert "products" in d
            assert len(d["products"]) >= 2

    def test_no_inline_hooks(self):
        """All inline hooks should have been extracted."""
        hooks = find_inline_hooks()
        assert len(hooks) == 0, f"Found inline hooks: {hooks}"


class TestDependencyAudit:
    def test_no_python_mismatches(self):
        mismatches = audit_python_deps()
        assert len(mismatches) == 0, f"Dep mismatches: {mismatches}"


class TestTestCoverage:
    def test_all_products_have_tests(self):
        result = analyze_test_coverage()
        critical = [i for i in result["issues"] if i["severity"] == "critical"]
        assert len(critical) == 0, f"Products without tests: {critical}"

    def test_matrix_has_all_products(self):
        result = analyze_test_coverage()
        products = [m["product"] for m in result["matrix"]]
        assert "seed" in products
        assert "mailing" in products

    def test_all_have_e2e(self):
        result = analyze_test_coverage()
        for m in result["matrix"]:
            assert m["e2e"] is True, f"{m['product']} missing E2E tests"


class TestCodeMetrics:
    def test_returns_all_products(self):
        metrics = get_code_metrics()
        assert len(metrics) >= 6

    def test_seed_is_minimal(self):
        """Seed ships ≤2 demo routers (example_router + webhook_router, see
        commit 22750fd) — no domain routers. Products inherit from the
        framework, never copy from seed. Backend stays slim; the bound
        accommodates the demo routers but catches drift toward "seed as
        a real product."""
        metrics = get_code_metrics()
        seed = next(m for m in metrics if m["product"] == "seed")
        assert seed["routers"] <= 2, (
            f"seed routers should stay ≤2 (demos only); got {seed['routers']}"
        )
        assert seed["backend_lines"] < 500, (
            f"seed backend should stay under 500 lines; got {seed['backend_lines']}"
        )


class TestRunAll:
    def test_run_all_returns_all_sections(self):
        results = run_all_analyzers()
        assert "duplicated_functions" in results
        assert "inline_hooks" in results
        assert "python_dep_mismatches" in results
        assert "test_coverage" in results
        assert "code_metrics" in results
