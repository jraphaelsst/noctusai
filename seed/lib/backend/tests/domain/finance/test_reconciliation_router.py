"""Slice-D HTTP contract: every route is unauthenticated => strictly 401, staff writes/exports => 403, staff reads work."""
from __future__ import annotations

import pytest

from .recon_support import ofx1, rh  # noqa: F401

P = "/api/finance"
U0 = "11111111-1111-1111-1111-111111111111"

#: (method, path, kind) kind: read | write | export
ROUTES = [
    ("POST", f"{P}/statements", "write"),
    ("GET", f"{P}/statements", "read"),
    ("GET", f"{P}/statements/{U0}/lines", "read"),
    ("POST", f"{P}/statement-lines/{U0}/match", "write"),
    ("POST", f"{P}/statement-lines/{U0}/ignore", "write"),
    ("POST", f"{P}/accounts/{U0}/gateway-sync", "write"),
    ("GET", f"{P}/exports/entries.csv", "export"),
    ("GET", f"{P}/exports/ledger.ofx?account_id={U0}", "export"),
]


@pytest.mark.parametrize("method, path, kind", ROUTES)
def test_unauthenticated_is_strictly_401(rh, method, path, kind):
    assert rh.client.request(method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path, kind", [r for r in ROUTES if r[2] != "read"])
def test_staff_cannot_write_or_export(rh, method, path, kind):
    r = rh.client.request(method, path, headers=rh.staff("user"), json={})
    assert r.status_code == 403, (path, r.status_code)


@pytest.mark.parametrize("method, path, kind", [r for r in ROUTES if r[2] == "read"])
def test_staff_can_read(rh, method, path, kind):
    assert rh.client.request(method, path, headers=rh.staff("user")).status_code in (200, 404)


def test_staff_upload_with_a_file_is_403_and_stores_nothing(rh):
    from .conftest import mk_account

    acc = mk_account(rh.s)
    r = rh.upload(acc["id"], "e.ofx", ofx1(("20261003", "1.00", "F", "x")), headers=rh.staff("user"))
    assert r.status_code == 403 and rh.s.rows("statement_imports") == []


def test_extra_body_fields_are_rejected(rh):
    assert rh.client.post(f"{P}/statement-lines/{U0}/match", headers=rh.admin, json={"entry_id": U0, "typo": 1}).status_code == 422
    assert rh.client.post(f"{P}/accounts/{U0}/gateway-sync", headers=rh.admin, json={"since": "2026-10-01", "typo": 1}).status_code == 422


def test_upload_route_is_covered_by_the_documented_body_override(rh):
    from noctusai_lib.domain.finance import STATEMENT_UPLOAD_MAX_BYTES, STATEMENT_UPLOAD_PATH_PATTERN, statements

    assert STATEMENT_UPLOAD_PATH_PATTERN == f"{P}/statements"
    assert STATEMENT_UPLOAD_MAX_BYTES > statements.MAX_STATEMENT_BYTES
