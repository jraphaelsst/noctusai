"""Tests for analyzer tools."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.analyzers import (
    find_duplicated_functions, find_inline_hooks,
    audit_python_deps, analyze_test_coverage, get_code_metrics,
    run_all_analyzers, _parse_requirements,
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

    def test_parse_requirements_strips_inline_comments(self):
        """A `pkg>=1.0  # why` line must parse to the clean version, not swallow
        the comment (regression 2026-05-31: inline comments in the root superset
        false-mismatched the same clean version in a product requirements file)."""
        parsed = _parse_requirements(
            "anthropic>=0.40.0                # therapy-platform (LLM)\n"
            "python-docx>=1.1.0   # ke docx_export\n"
            "# a pure comment line is skipped\n"
            "requests\n"
        )
        assert parsed == {
            "anthropic": ">=0.40.0",
            "python-docx": ">=1.1.0",
            "requests": "any",
        }, parsed


class TestTestCoverage:
    def test_all_products_have_tests(self):
        result = analyze_test_coverage()
        critical = [i for i in result["issues"] if i["severity"] == "critical"]
        assert len(critical) == 0, f"Products without tests: {critical}"

    def test_matrix_has_all_products(self, domain_product):
        result = analyze_test_coverage()
        products = [m["product"] for m in result["matrix"]]
        assert "seed" in products
        # Registry-derived domain product, not a frozen `"mailing"` literal
        # (deleted in social-wiring-absorption Wave-4; see tests/conftest.py).
        assert domain_product in products

    def test_all_have_e2e(self):
        """Every SEED-ARCHITECTURE product ships the e2e flow suite.

        🔴 SCOPED 2026-09-04. `permutas` was absorbed as Django + DRF +
        create-react-app, building on neither half of the seed, and has no
        `backend/tests/integration/test_e2e_flows.py` — the seed-shaped file
        this looks for. CI already agrees: the e2e jobs cover `core` and `erp`
        only, never every product. Asserting it fleet-wide was stricter than
        anything CI enforces, and it reddened the matrix for a divergence that
        was deliberate.

        The scope is DERIVED from `is_seed_architecture_product`, never a slug
        list, so it flips on its own the day permutas adopts the seed — at
        which point this file becomes a real requirement for it again.
        """
        result = analyze_test_coverage()
        covered = [m for m in result["matrix"] if m.get("seed_architecture", True)]
        assert covered, "no seed-architecture products found — the predicate is wrong"
        for m in covered:
            assert m["e2e"] is True, f"{m['product']} missing E2E tests"

    def test_a_divergent_absorption_is_reported_not_hidden(self):
        """The exemption must be visible in the matrix rather than a silent
        omission — "why is permutas not required to have e2e?" has to be
        answerable from the output alone."""
        result = analyze_test_coverage()
        assert all("seed_architecture" in m for m in result["matrix"])
        by_slug = {m["product"]: m for m in result["matrix"]}
        if "permutas" in by_slug:
            assert by_slug["permutas"]["seed_architecture"] is False


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
        # `routers <= 2` is the meaningful structural anchor (catches drift
        # toward "seed as a real product" — domain routers); the line bound is
        # a coarse bloat guard only. Bound raised 500→600 on 2026-05-17: the
        # seed-standalone-dev-ergonomics work added the dev-auth wiring seam to
        # products/seed/backend/app/dependencies.py (a legitimately-shipped
        # feature, ledger slug `seed-standalone-dev-ergonomics`), pushing the
        # demo backend to 509. Bound raised 600→750 on 2026-05-25: the demo
        # skeletons grew (example_router 161 + webhook_router 114 +
        # example_service 109 — the day-one route/webhook/FE-BE skeleton the
        # seed ships), totalling 662; still 2 demo routers, no domain drift.
        # Anchor + headroom, not just a moved threshold
        # (feedback_hardcoded_fleet_size_literal_keeper: count guards need a
        # positive content anchor, not a bare number).
        assert seed["routers"] <= 2, (
            f"seed routers should stay ≤2 (demos only); got {seed['routers']}"
        )
        assert seed["backend_lines"] < 750, (
            f"seed backend should stay under 750 lines; got {seed['backend_lines']}"
        )


class TestRunAll:
    def test_run_all_returns_all_sections(self):
        results = run_all_analyzers()
        assert "duplicated_functions" in results
        assert "inline_hooks" in results
        assert "python_dep_mismatches" in results
        assert "test_coverage" in results
        assert "code_metrics" in results
