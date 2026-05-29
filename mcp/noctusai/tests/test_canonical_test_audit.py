"""Colocated regression tests for `canonical_test_audit`.

Tests:
- discover_canonical_tests: finds products with inherited suite imports
- discover_canonical_tests: finds products with inlined canonical classes
- discover_canonical_tests: ignores products with no canonical tests
- audit_canonical_tests: enriches with venv_present + execution_ready
- audit_canonical_tests: venv-absent products are flagged but not excluded
- fleet smoke: discovers at least dev-team in the current fleet
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.canonical_test_audit import (  # noqa: E402
    discover_canonical_tests,
    audit_canonical_tests,
    CANONICAL_SUITES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_product_tree(
    tmp_path: Path,
    name: str,
    test_files: dict[str, str] | None = None,
    venv: bool = False,
) -> Path:
    """Build a minimal product tree under tmp_path/<name>/."""
    product = tmp_path / name
    tests_root = product / "backend" / "tests" / "integration"
    tests_root.mkdir(parents=True)
    for filename, content in (test_files or {}).items():
        (tests_root / filename).write_text(content, encoding="utf-8")
    if venv:
        venv_bin = product / "backend" / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").write_text("#!/bin/sh\npython3 $@\n")
    return product


_LIB_IMPORT_CONTENT = """\
from noctusai_lib.testing import (
    FrameworkEndpointsSuite,
    AuthBoundarySuite,
)

class TestFrameworkEndpoints(FrameworkEndpointsSuite):
    expected_product_name = "Test"

class TestAuthBoundary(AuthBoundarySuite):
    pass
"""

_INLINED_CONTENT = """\
class TestFrameworkEndpoints:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
"""

_IRRELEVANT_CONTENT = """\
class TestBusiness:
    def test_create_item(self, client):
        resp = client.post("/api/items", json={})
        assert resp.status_code == 201
"""


# ---------------------------------------------------------------------------
# discover_canonical_tests
# ---------------------------------------------------------------------------

class TestDiscoverCanonicalTests:
    def test_finds_lib_testing_imports(self, tmp_path: Path):
        _make_product_tree(
            tmp_path, "myprod",
            test_files={"test_e2e_flows.py": _LIB_IMPORT_CONTENT},
        )
        results = discover_canonical_tests(products_dir=tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r["product"] == "myprod"
        assert r["uses_lib_testing"] is True
        assert not r["has_inlined_copy"]
        assert "FrameworkEndpointsSuite" in r["canonical_files"][0]["inherited_suites"]
        assert "AuthBoundarySuite" in r["canonical_files"][0]["inherited_suites"]

    def test_finds_inlined_canonical_class(self, tmp_path: Path):
        _make_product_tree(
            tmp_path, "inlined",
            test_files={"test_e2e_flows.py": _INLINED_CONTENT},
        )
        results = discover_canonical_tests(products_dir=tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r["product"] == "inlined"
        assert r["has_inlined_copy"] is True
        assert r["uses_lib_testing"] is False

    def test_ignores_irrelevant_test_files(self, tmp_path: Path):
        _make_product_tree(
            tmp_path, "clean",
            test_files={"test_business.py": _IRRELEVANT_CONTENT},
        )
        results = discover_canonical_tests(products_dir=tmp_path)
        assert results == []

    def test_no_tests_dir_returns_empty(self, tmp_path: Path):
        product = tmp_path / "noprod"
        product.mkdir()
        results = discover_canonical_tests(products_dir=tmp_path)
        assert results == []

    def test_scoped_to_single_product(self, tmp_path: Path):
        _make_product_tree(
            tmp_path, "alpha",
            test_files={"test_e2e_flows.py": _LIB_IMPORT_CONTENT},
        )
        _make_product_tree(
            tmp_path, "beta",
            test_files={"test_e2e_flows.py": _INLINED_CONTENT},
        )
        results = discover_canonical_tests(products_dir=tmp_path, product_slug="alpha")
        assert len(results) == 1
        assert results[0]["product"] == "alpha"

    def test_missing_slug_returns_empty(self, tmp_path: Path):
        results = discover_canonical_tests(products_dir=tmp_path, product_slug="nonexistent")
        assert results == []


# ---------------------------------------------------------------------------
# audit_canonical_tests
# ---------------------------------------------------------------------------

class TestAuditCanonicalTests:
    def test_execution_ready_when_venv_present_and_lib_testing(self, tmp_path: Path):
        _make_product_tree(
            tmp_path, "readyprod",
            test_files={"test_e2e_flows.py": _LIB_IMPORT_CONTENT},
            venv=True,
        )
        report = audit_canonical_tests(products_dir=tmp_path)
        assert report["ok"] is True
        assert report["total_products_with_canonical_tests"] == 1
        prods = report["products"]
        assert prods[0]["execution_ready"] is True
        assert prods[0]["venv_present"] is True
        assert "readyprod" in report["execution_ready_products"]

    def test_not_execution_ready_when_venv_absent(self, tmp_path: Path):
        _make_product_tree(
            tmp_path, "novenv",
            test_files={"test_e2e_flows.py": _LIB_IMPORT_CONTENT},
            venv=False,
        )
        report = audit_canonical_tests(products_dir=tmp_path)
        prods = report["products"]
        assert prods[0]["venv_present"] is False
        assert prods[0]["execution_ready"] is False
        assert "novenv" not in report["execution_ready_products"]

    def test_not_execution_ready_when_inlined(self, tmp_path: Path):
        _make_product_tree(
            tmp_path, "inline",
            test_files={"test_e2e_flows.py": _INLINED_CONTENT},
            venv=True,
        )
        report = audit_canonical_tests(products_dir=tmp_path)
        prods = report["products"]
        assert prods[0]["has_inlined_copy"] is True
        assert prods[0]["execution_ready"] is False

    def test_empty_fleet_returns_ok(self, tmp_path: Path):
        (tmp_path / "irrelevant").mkdir()
        (tmp_path / "irrelevant" / "backend" / "tests").mkdir(parents=True)
        (tmp_path / "irrelevant" / "backend" / "tests" / "test_foo.py").write_text(
            _IRRELEVANT_CONTENT
        )
        report = audit_canonical_tests(products_dir=tmp_path)
        assert report["ok"] is True
        assert report["total_products_with_canonical_tests"] == 0

    def test_execution_note_present(self, tmp_path: Path):
        report = audit_canonical_tests(products_dir=tmp_path)
        assert "NOC-REMEDIATE[canonical-runner-exec]" in report["execution_note"]


# ---------------------------------------------------------------------------
# Fleet smoke — current fleet must include known canonical-test products
# ---------------------------------------------------------------------------

class TestCanonicalTestAuditFleetSmoke:
    """Smoke test against the live fleet. dev-team must be discovered since it
    carries `TestFrameworkEndpoints` + `TestDevTeamAPISurfaceAuthBoundary` in
    its integration tests."""

    def test_fleet_includes_dev_team(self):
        from settings import PRODUCTS_DIR
        if not PRODUCTS_DIR.exists():
            pytest.skip("PRODUCTS_DIR not available in this environment")
        results = discover_canonical_tests()
        product_names = [r["product"] for r in results]
        assert "dev-team" in product_names, (
            f"Expected dev-team in canonical test inventory, got: {product_names}"
        )

    def test_fleet_audit_returns_ok(self):
        from settings import PRODUCTS_DIR
        if not PRODUCTS_DIR.exists():
            pytest.skip("PRODUCTS_DIR not available in this environment")
        report = audit_canonical_tests()
        assert report["ok"] is True
        assert report["total_products_with_canonical_tests"] > 0, (
            "Expected at least one product with canonical inherited tests"
        )
        # Sanity: execution note must always be present
        assert "NOC-REMEDIATE[canonical-runner-exec]" in report["execution_note"]
