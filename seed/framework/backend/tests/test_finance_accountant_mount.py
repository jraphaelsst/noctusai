"""`mount_finance` wires the ACCOUNTANT READ grant: org admin OR the per-org permission -> reports/exports; never a write.

A real core mock (noctus_users membership, so admin is decided in the SELECTED org), the real permission repo's Fake, and the
finance schema EMITTED by the generator in the mock's schema cache. Nothing is monkeypatched.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.domain.finance import FinanceConfig, accountant_permission_for, finance_migration
from noctusai_lib.domain.permissions import FakePermissionGrantRepository
from noctusai_lib.testing import MockSupabaseClient, _schema_cache
from noctusai_lib.testing.migration_parser import parse_sql
from noctusai_seed.organs import mount_finance

SCHEMA = "finx"
ORG, OTHER = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b", "9c8d7e6f-5a4b-4c3d-8e2f-1a0b9c8d7e6f"
CFG = FinanceConfig(schema=SCHEMA)
USERS = {"admin": "u-admin", "accountant": "u-acc", "member": "u-member", "global": "u-global", "elsewhere": "u-else"}


@pytest.fixture
def client():
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    _schema_cache.set_cache_for_tests({**base, **parse_sql(finance_migration(CFG, SCHEMA), source_label="finance_migration")})
    core = MockSupabaseClient()
    core.set_table_data("noctus_users", [
        {"id": "u-admin", "org_id": ORG, "org_role": "owner", "role": "user"},
        {"id": "u-acc", "org_id": ORG, "org_role": "member", "role": "user"},
        {"id": "u-member", "org_id": ORG, "org_role": "member", "role": "user"},
        {"id": "u-global", "org_id": ORG, "org_role": "member", "role": "user"},
        {"id": "u-else", "org_id": ORG, "org_role": "member", "role": "user"},
    ])
    perms = FakePermissionGrantRepository([
        ("u-acc", accountant_permission_for(CFG, ORG)),
        ("u-global", CFG.accountant_permission),  # the bare, user-global name: must NOT open anything
        ("u-else", accountant_permission_for(CFG, OTHER)),  # granted for ANOTHER client's org only
    ])

    async def auth(authorization: str | None = Header(None), x_org: str | None = Header(None)):
        role = (authorization or "").removeprefix("Bearer ")
        if role not in USERS:
            raise HTTPException(status_code=401, detail="no auth")
        return (SimpleNamespace(id=USERS[role]), "tok", x_org or ORG)

    db = MockSupabaseClient(validate_schema=True, schema=SCHEMA)
    organ = mount_finance(schema=SCHEMA, auth_dependency=auth, get_admin_client=lambda: db, get_core_client=lambda: core, permissions=perms)
    app = FastAPI()
    from noctusai_lib.primitives.exceptions import AppException, app_exception_handler, http_exception_handler
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    for r in organ:
        app.include_router(r)
    yield TestClient(app)
    _schema_cache.set_cache_for_tests(base)


def H(role: str, org: str | None = None) -> dict:
    return {"Authorization": f"Bearer {role}", **({"X-Org": org} if org else {})}


READS = ["/reports/dre", "/reports/budget", "/reports/livro-caixa", "/reports/mei-monthly", "/accountant-checklist", "/exports/dre.csv",
         "/exports/entries.csv", "/exports/livro-caixa.csv"]


@pytest.mark.parametrize("path", READS)
def test_reads_admin_and_granted_accountant_pass_others_do_not(client, path):
    url = f"/api/finance{path}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=H("admin")).status_code == 200
    assert client.get(url, headers=H("accountant")).status_code == 200
    assert client.get(url, headers=H("member")).status_code == 403
    assert client.get(url, headers=H("global")).status_code == 403  # a user-global grant is not a per-org grant


def test_the_grant_is_per_org(client):
    """A grant issued by another client's admin (permission for OTHER) opens nothing in ORG, even for an ORG member."""
    assert client.get("/api/finance/reports/dre", headers=H("elsewhere")).status_code == 403
    assert accountant_permission_for(CFG, ORG) != accountant_permission_for(CFG, OTHER)


@pytest.mark.parametrize("method,path,body", [
    ("post", "/entries", {"direction": "payable", "description": "x", "due_date": "2026-10-20", "amount_cents": 1}),
    ("put", "/dre-settings", {"tax_regime": "mei"}),
    ("put", "/budgets", {"items": [{"category_id": "11111111-1111-4111-8111-111111111111", "month": "2026-10-01", "amount_cents": 1}]}),
    ("post", "/accounts", {"name": "x", "kind": "cash"}),
])
def test_writes_stay_admin_only_even_with_the_grant(client, method, path, body):
    url = f"/api/finance{path}"
    assert client.request(method, url, json=body).status_code == 401
    assert client.request(method, url, headers=H("accountant"), json=body).status_code == 403
    assert client.request(method, url, headers=H("member"), json=body).status_code == 403


def test_a_home_org_owner_selecting_another_org_has_no_admin_read(client):
    assert client.get("/api/finance/reports/dre", headers=H("admin", OTHER)).status_code == 403
