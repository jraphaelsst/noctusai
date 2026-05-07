"""Tests for `check_test_status_assertion` keeper detector.

Defends against the YouTube Crawler Phase 1 "false-green" slip where a
substring assertion on `resp.text.lower()` matched the wrong of two error
entries in a 422 body, and the test went green even though the endpoint was
unusable due to an upstream broken `Depends(get_org_id)` chain. The
structural fix: every test asserting on response BODY (`.text` / `.json()` /
`.content`) must also assert on response STATUS CODE (`.status_code`) in the
SAME method body.

Per KB § PATTERNS/testing.md § Status-code-assertion rule + KB § PATTERNS/
testing.md § Regression-test-the-detector.

All tests use `tmp_path` so the detector runs against fixture-built test
files — no dependency on the live `products/` state.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_test_status_assertion,
)


def _mk_test_file(product_root: Path, rel: str, source: str) -> Path:
    """Write a fake test file at <product_root>/backend/tests/<rel>.

    Creates parent dirs as needed. The detector walks
    `<product_root>/backend/tests/` so the layout matters.
    """
    target = product_root / "backend" / "tests" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source)
    return target


# ---------------------------------------------------------------------------
# Core detector behavior
# ---------------------------------------------------------------------------

class TestCheckTestStatusAssertion:
    def test_body_text_with_status_code_pass(self, tmp_path: Path):
        """Body-text assertion paired with status-code check → no finding.

        This is the canonical correct shape — flag is body+status, both
        load-bearing, in the same method.
        """
        source = (
            "def test_recipient_rejected(client):\n"
            "    resp = client.post('/x', json={})\n"
            "    assert resp.status_code == 422\n"
            "    assert 'at least one of' in resp.text.lower()\n"
        )
        _mk_test_file(tmp_path, "test_router.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert findings == [], f"Expected zero findings, got: {findings}"

    def test_body_text_without_status_code_flagged(self, tmp_path: Path):
        """Body-text assertion alone → finding.

        This is the YouTube Crawler Phase 1 slip exactly.
        """
        source = (
            "def test_recipient_rejected(client):\n"
            "    resp = client.post('/x', json={})\n"
            "    assert 'at least one of' in resp.text.lower()\n"
        )
        _mk_test_file(tmp_path, "test_router.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert len(findings) == 1, f"Expected 1 finding, got: {findings}"
        f = findings[0]
        assert f["method"] == "test_recipient_rejected"
        assert f["severity"] == "warning"
        assert "test_router.py" in f["file"]
        assert f["line"] >= 1

    def test_json_body_with_status_code_pass(self, tmp_path: Path):
        """JSON-body assertion paired with status-code → no finding.

        Both `resp.json()["x"]` and `resp.status_code == N` are present.
        """
        source = (
            "def test_create_returns_payload(client):\n"
            "    resp = client.post('/api/x', json={'name': 'x'})\n"
            "    assert resp.status_code == 201\n"
            "    assert resp.json()['name'] == 'x'\n"
        )
        _mk_test_file(tmp_path, "test_create.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert findings == [], f"Expected zero findings, got: {findings}"

    def test_json_body_without_status_code_flagged(self, tmp_path: Path):
        """JSON-body assertion alone → finding."""
        source = (
            "def test_create_returns_payload(client):\n"
            "    resp = client.post('/api/x', json={'name': 'x'})\n"
            "    assert resp.json()['name'] == 'x'\n"
        )
        _mk_test_file(tmp_path, "test_create.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert len(findings) == 1
        assert findings[0]["method"] == "test_create_returns_payload"

    def test_content_body_without_status_code_flagged(self, tmp_path: Path):
        """`.content` (binary body) assertion alone → finding.

        Same fingerprint as `.text` — body without status pin is unsafe.
        """
        source = (
            "def test_image_endpoint(client):\n"
            "    resp = client.get('/api/img/1')\n"
            "    assert b'PNG' in resp.content\n"
        )
        _mk_test_file(tmp_path, "test_image.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert len(findings) == 1
        assert findings[0]["method"] == "test_image_endpoint"

    def test_no_response_body_assertion_no_finding(self, tmp_path: Path):
        """Test with no body assertions at all → no finding.

        Even without a status_code check — the rule only fires when body
        assertion is present.
        """
        source = (
            "def test_nothing_to_assert():\n"
            "    x = 1 + 1\n"
            "    assert x == 2\n"
        )
        _mk_test_file(tmp_path, "test_misc.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert findings == [], f"Expected zero findings, got: {findings}"

    def test_helper_function_not_scanned(self, tmp_path: Path):
        """Non-`test_*` helper function with body assertion → not flagged.

        Per PROJECT.md § 3 design principle 1: method-scope detection.
        The detector only walks `def test_*` methods. A helper without
        the prefix is out of scope (the test author may have status_code
        elsewhere; we conservatively skip).
        """
        source = (
            "def _assert_error_msg(resp, msg):\n"
            "    assert msg in resp.text\n"
            "\n"
            "def test_uses_helper(client):\n"
            "    resp = client.post('/x', json={})\n"
            "    assert resp.status_code == 422\n"
            "    _assert_error_msg(resp, 'at least one of')\n"
        )
        _mk_test_file(tmp_path, "test_helper.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert findings == [], f"Expected zero findings, got: {findings}"

    # -----------------------------------------------------------------
    # Variable-name agnosticism
    # -----------------------------------------------------------------

    def test_matches_any_response_variable_name(self, tmp_path: Path):
        """Detector matches by attribute name, not variable name.

        `r.text` / `response.text` / `result.text` / `resp.text` all qualify
        as body access — the detector flags whichever lacks status_code.
        """
        source = (
            "def test_using_r(client):\n"
            "    r = client.get('/a')\n"
            "    assert 'ok' in r.text\n"
            "\n"
            "def test_using_response(client):\n"
            "    response = client.get('/b')\n"
            "    assert response.status_code == 200\n"
            "    assert 'ok' in response.text\n"
            "\n"
            "def test_using_result(client):\n"
            "    result = client.get('/c')\n"
            "    assert 'ok' in result.text\n"
        )
        _mk_test_file(tmp_path, "test_var_names.py", source)
        findings = check_test_status_assertion(tmp_path)
        method_names = {f["method"] for f in findings}
        assert method_names == {"test_using_r", "test_using_result"}

    def test_class_nested_methods_walked(self, tmp_path: Path):
        """Class-nested `test_*` methods get scanned the same as module-level.

        pytest collects both shapes; the detector must handle both.
        """
        source = (
            "class TestRouter:\n"
            "    def test_ok(self, client):\n"
            "        resp = client.get('/x')\n"
            "        assert resp.status_code == 200\n"
            "        assert 'ok' in resp.text\n"
            "\n"
            "    def test_bad(self, client):\n"
            "        resp = client.get('/x')\n"
            "        assert 'err' in resp.text\n"
        )
        _mk_test_file(tmp_path, "test_class.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert len(findings) == 1
        assert findings[0]["method"] == "test_bad"

    def test_async_test_methods_walked(self, tmp_path: Path):
        """`async def test_*` (pytest-asyncio) is scanned the same as sync."""
        source = (
            "import pytest\n"
            "\n"
            "@pytest.mark.asyncio\n"
            "async def test_async_handler(client):\n"
            "    resp = await client.get('/x')\n"
            "    assert 'oops' in resp.text\n"
        )
        _mk_test_file(tmp_path, "test_async.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert len(findings) == 1
        assert findings[0]["method"] == "test_async_handler"

    def test_status_code_in_tuple_pass(self, tmp_path: Path):
        """`assert resp.status_code in (401, 403)` satisfies the rule.

        Any comparison op is acceptable — the rule is "is status_code
        attribute referenced in any assertion", not a specific operator.
        """
        source = (
            "def test_either_unauthorized(client):\n"
            "    resp = client.get('/x')\n"
            "    assert resp.status_code in (401, 403)\n"
            "    assert 'unauthorized' in resp.text.lower()\n"
        )
        _mk_test_file(tmp_path, "test_tuple.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert findings == [], f"Expected zero findings, got: {findings}"

    def test_status_code_inequality_pass(self, tmp_path: Path):
        """`assert resp.status_code != 500` also satisfies — any op."""
        source = (
            "def test_no_500(client):\n"
            "    resp = client.get('/x')\n"
            "    assert resp.status_code != 500\n"
            "    assert 'data' in resp.json()\n"
        )
        _mk_test_file(tmp_path, "test_inequality.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert findings == [], f"Expected zero findings, got: {findings}"

    def test_chained_text_lower_still_detected(self, tmp_path: Path):
        """`resp.text.lower()` is body access — the `.lower()` chain doesn't hide it."""
        source = (
            "def test_chained(client):\n"
            "    resp = client.get('/x')\n"
            "    assert 'oops' in resp.text.lower().strip()\n"
        )
        _mk_test_file(tmp_path, "test_chain.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert len(findings) == 1
        assert findings[0]["method"] == "test_chained"

    # -----------------------------------------------------------------
    # Edge cases
    # -----------------------------------------------------------------

    def test_no_tests_dir_returns_empty(self, tmp_path: Path):
        """Product without `backend/tests/` → empty list, not crash."""
        # tmp_path has no backend/tests directory.
        findings = check_test_status_assertion(tmp_path)
        assert findings == []

    def test_syntax_error_file_skipped(self, tmp_path: Path):
        """Files with SyntaxError are skipped (logged), not crashed on."""
        _mk_test_file(tmp_path, "test_broken.py", "def test_x(:\n    pass\n")
        # And a valid file with a real finding so we know the walker continues.
        _mk_test_file(
            tmp_path,
            "test_good.py",
            "def test_y(client):\n"
            "    resp = client.get('/x')\n"
            "    assert 'oops' in resp.text\n",
        )
        findings = check_test_status_assertion(tmp_path)
        assert len(findings) == 1
        assert findings[0]["method"] == "test_y"

    def test_non_test_file_skipped(self, tmp_path: Path):
        """A `helpers.py` with body asserts is not scanned (not `test_*.py`)."""
        target = tmp_path / "backend" / "tests" / "helpers.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "def test_should_be_ignored_because_filename_not_test(client):\n"
            "    resp = client.get('/x')\n"
            "    assert 'oops' in resp.text\n"
        )
        findings = check_test_status_assertion(tmp_path)
        assert findings == []

    def test_underscore_test_py_suffix_scanned(self, tmp_path: Path):
        """`*_test.py` suffix is also a pytest convention — gets scanned."""
        target = tmp_path / "backend" / "tests" / "router_test.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "def test_x(client):\n"
            "    resp = client.get('/x')\n"
            "    assert 'oops' in resp.text\n"
        )
        findings = check_test_status_assertion(tmp_path)
        assert len(findings) == 1

    def test_multiple_findings_in_one_file(self, tmp_path: Path):
        """Each violating test method generates its own finding."""
        source = (
            "def test_a(client):\n"
            "    resp = client.get('/a')\n"
            "    assert 'a' in resp.text\n"
            "\n"
            "def test_b(client):\n"
            "    resp = client.get('/b')\n"
            "    assert resp.status_code == 200\n"
            "    assert 'b' in resp.text\n"
            "\n"
            "def test_c(client):\n"
            "    resp = client.get('/c')\n"
            "    assert resp.json()['x'] == 1\n"
        )
        _mk_test_file(tmp_path, "test_multi.py", source)
        findings = check_test_status_assertion(tmp_path)
        flagged = {f["method"] for f in findings}
        assert flagged == {"test_a", "test_c"}

    def test_finding_shape(self, tmp_path: Path):
        """Findings carry product, file, method, line, issue, severity."""
        source = (
            "def test_x(client):\n"
            "    resp = client.get('/x')\n"
            "    assert 'oops' in resp.text\n"
        )
        _mk_test_file(tmp_path, "test_shape.py", source)
        findings = check_test_status_assertion(tmp_path)
        assert len(findings) == 1
        f = findings[0]
        assert set(f.keys()) >= {
            "product", "file", "method", "line", "issue", "severity",
        }
        assert f["product"] == tmp_path.name
        assert f["severity"] == "warning"
        assert "Status-code-assertion rule" in f["issue"]
