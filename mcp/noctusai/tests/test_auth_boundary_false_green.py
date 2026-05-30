"""Colocated regression tests for `check_auth_boundary_false_green`.

Coverage:
  positive — flags (401,404) / (404,401) / {401,404} + (401,422) [validation-before-auth]
  negative — (200,201) / (401,403) / (404,500) / strict `== 401` are NOT flagged
  syntax-error-surfaces — a file with SyntaxError produces a warning finding
                           (no `except: pass`)
  fleet-regression — dev-team stays clean (9d6bf79c fix); whole-fleet scan is
                     advisory (warning-only) and may surface known debt
                     (personal-finance `in (401, 422)` backlog)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_auth_boundary_false_green  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_product_with_test(tmp_path: Path, test_source: str) -> Path:
    """Build a minimal product tree containing one test file."""
    product = tmp_path / "testprod"
    tests_dir = product / "backend" / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_auth.py").write_text(test_source, encoding="utf-8")
    return product


# ---------------------------------------------------------------------------
# Positive — should be flagged
# ---------------------------------------------------------------------------

class TestAuthBoundaryFalseGreenPositive:
    """Each of these assertion shapes MUST produce at least one warning finding."""

    def test_flags_tuple_401_404(self, tmp_path: Path):
        product = _make_product_with_test(
            tmp_path,
            "def test_x(client):\n    resp = client.get('/api/team')\n    assert resp.status_code in (401, 404)\n",
        )
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert len(issues) == 1, f"Expected 1 issue, got: {issues}"
        assert issues[0]["severity"] == "warning"
        assert "401" in issues[0]["issue"]
        assert "404" in issues[0]["issue"]

    def test_flags_tuple_404_401(self, tmp_path: Path):
        """Order must not matter — (404, 401) is equally a false-green."""
        product = _make_product_with_test(
            tmp_path,
            "def test_x(client):\n    resp = client.get('/api/run')\n    assert resp.status_code in (404, 401)\n",
        )
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"

    def test_flags_tuple_401_422(self, tmp_path: Path):
        """`(401, 422)` is the same false-green class: an unauthenticated request
        with an invalid body returns 422 (validation before auth), so the test
        passes even if the auth dependency were removed. Fix = send a VALID body
        and assert strict 401."""
        product = _make_product_with_test(
            tmp_path,
            "def test_x(client):\n    resp = client.post('/api/items', json={})\n    assert resp.status_code in (401, 422)\n",
        )
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert len(issues) == 1, f"Expected 1 issue, got: {issues}"
        assert issues[0]["severity"] == "warning"
        assert "422" in issues[0]["issue"]

    def test_flags_set_form_401_404(self, tmp_path: Path):
        """`in {401, 404}` is the same false-green shape."""
        product = _make_product_with_test(
            tmp_path,
            "def test_x(client):\n    resp = client.get('/api/agents')\n    assert resp.status_code in {401, 404}\n",
        )
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"

    def test_flags_set_form_404_401(self, tmp_path: Path):
        """`in {404, 401}` — same predicate, different order."""
        product = _make_product_with_test(
            tmp_path,
            "def test_x(client):\n    resp = client.get('/api/metrics')\n    assert resp.status_code in {404, 401}\n",
        )
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"

    def test_reports_line_number_in_issue(self, tmp_path: Path):
        product = _make_product_with_test(
            tmp_path,
            "# line 1\n# line 2\ndef test_x(client):\n    resp = client.get('/api/team')\n    assert resp.status_code in (401, 404)\n",
        )
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert issues, "Expected at least one finding"
        assert "line 5" in issues[0]["issue"]

    def test_multiple_violations_in_same_file(self, tmp_path: Path):
        product = _make_product_with_test(
            tmp_path,
            (
                "def test_a(client):\n"
                "    resp = client.get('/api/team')\n"
                "    assert resp.status_code in (401, 404)\n"
                "def test_b(client):\n"
                "    resp = client.get('/api/run')\n"
                "    assert resp.status_code in (404, 401)\n"
            ),
        )
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert len(issues) == 2, f"Expected 2 issues, got {len(issues)}: {issues}"


# ---------------------------------------------------------------------------
# Negative — must NOT be flagged
# ---------------------------------------------------------------------------

class TestAuthBoundaryFalseGreenNegative:
    """These assertion shapes are legitimate — the keeper must stay quiet."""

    def test_clean_200_201_not_flagged(self, tmp_path: Path):
        """Success-range disjunction has nothing to do with auth."""
        product = _make_product_with_test(
            tmp_path,
            "def test_create(client):\n    resp = client.post('/api/items', json={})\n    assert resp.status_code in (200, 201)\n",
        )
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert issues == []

    def test_clean_401_403_not_flagged(self, tmp_path: Path):
        """`(401, 403)` is a legitimate auth check — both codes mean
        unauthorized/forbidden; 404 is absent so no false-green risk."""
        product = _make_product_with_test(
            tmp_path,
            "def test_auth(client):\n    resp = client.get('/api/runs')\n    assert resp.status_code in (401, 403)\n",
        )
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert issues == []

    def test_clean_strict_eq_401_not_flagged(self, tmp_path: Path):
        """The fixed form — strict `== 401` — must never be flagged."""
        product = _make_product_with_test(
            tmp_path,
            "def test_auth(client):\n    resp = client.get('/api/team')\n    assert resp.status_code == 401\n",
        )
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert issues == []

    def test_clean_404_500_not_flagged(self, tmp_path: Path):
        """`(404, 500)` is a resource-not-found / error range — no 401 present."""
        product = _make_product_with_test(
            tmp_path,
            "def test_notfound(client):\n    resp = client.get('/api/nonexistent')\n    assert resp.status_code in (404, 500)\n",
        )
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert issues == []

    def test_no_tests_dir_returns_empty(self, tmp_path: Path):
        """Product without a backend/tests dir is out of scope."""
        product = tmp_path / "notestprod"
        product.mkdir()
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert issues == []

    def test_empty_test_file_returns_empty(self, tmp_path: Path):
        product = _make_product_with_test(tmp_path, "# no assertions\n")
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert issues == []


# ---------------------------------------------------------------------------
# SyntaxError surfaces (never silent)
# ---------------------------------------------------------------------------

class TestAuthBoundaryFalseGreenSyntaxError:
    """A file with SyntaxError must produce a warning finding, not be silently
    skipped — this tests the `no-silent-errors` rule."""

    def test_syntax_error_produces_warning_finding(self, tmp_path: Path):
        product = _make_product_with_test(
            tmp_path,
            "def broken(\n    # unclosed parenthesis — SyntaxError\n",
        )
        issues = check_auth_boundary_false_green(product_path=product, products_dir=tmp_path)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "SyntaxError" in issues[0]["issue"] or "manual review" in issues[0]["issue"].lower()


# ---------------------------------------------------------------------------
# Fleet regression — current products must be clean
# ---------------------------------------------------------------------------

class TestAuthBoundaryFalseGreenFleetRegression:
    """Live-fleet guards.

    The keeper is advisory and the fleet is NOT globally clean: `personal-finance`
    carries a known backlog of `in (401, 422)` assertions (tracked for
    remediation). So we do NOT assert whole-fleet-clean. Instead:
      - `dev-team` MUST stay clean (regression guard for the 9d6bf79c fix), and
      - the fleet scan must not crash and must emit only `warning` severity.
    """

    def test_dev_team_is_clean(self):
        """The 9d6bf79c fix replaced dev-team's `in (401, 404)` with strict
        `== 401`; this guards against a revert/reintroduction."""
        from settings import PRODUCTS_DIR  # noqa: E402
        dev_team = PRODUCTS_DIR / "dev-team"
        if not dev_team.exists():
            pytest.skip("dev-team not available in this environment")
        issues = check_auth_boundary_false_green(product_path=dev_team)
        assert issues == [], (
            f"dev-team regressed — {len(issues)} false-green finding(s):\n"
            + "\n".join(f"  {i['file']}: {i['issue']}" for i in issues)
        )

    def test_fleet_scan_is_advisory_and_safe(self):
        """Whole-fleet scan must not crash and must surface only warnings
        (never blocks a commit). Documents that real debt may be present."""
        from settings import PRODUCTS_DIR  # noqa: E402
        if not PRODUCTS_DIR.exists():
            pytest.skip("PRODUCTS_DIR not available in this environment")
        issues = check_auth_boundary_false_green()
        assert isinstance(issues, list)
        assert all(i["severity"] == "warning" for i in issues), (
            "All auth-boundary-false-green findings must be advisory (warning)."
        )
