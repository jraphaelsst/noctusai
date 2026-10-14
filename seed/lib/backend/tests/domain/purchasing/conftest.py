"""Shared harness for the purchasing organ suite.

The mock PostgREST client validates EVERY column the code touches against the schema EMITTED BY the generators of the
organs the host mounts (purchasing + parties + inventory + finance(with_parties)), through the mock's own
`set_cache_for_tests` seam. RPC behaviour (locks, proration, state machine) is proven on a real Postgres in
`test_purchasing_on_real_postgres.py`; here `rpc()` is the mock's canned-data seam, so these tests cover what is
Python's job: org scoping, the approval rule, validation, the refusal -> HTTP map and the two posting legs.
Nothing is monkeypatched: db is the factory's DI seam, auth is a real FastAPI dependency pair, the cross-organ ports
are the REAL `SupabaseStockPort` / `SupabaseFinanceBooking` over the mock (and the Fakes where a test needs to count).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.finance import FinanceConfig, finance_migration
from noctusai_lib.domain.inventory import InventoryConfig, inventory_migration
from noctusai_lib.domain.parties import PartiesConfig, parties_migration
from noctusai_lib.domain.purchasing import PurchasingConfig, PurchasingContext, make_purchasing_router, purchasing_migration
from noctusai_lib.domain.purchasing._common import Scope
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from noctusai_lib.testing import _schema_cache
from noctusai_lib.testing.migration_parser import parse_sql
from noctusai_lib.testing.mocks import MockSupabaseClient

ORG_A = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b"
ORG_B = "9c8d7e6f-5a4b-4c3d-8e2f-1a0b9c8d7e6f"
USER_ID = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
PARTY = "33333333-3333-4333-8333-333333333333"
ITEM = "11111111-1111-4111-8111-111111111111"
ITEM2 = "22222222-2222-4222-8222-222222222222"
WH1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ORDER = "44444444-4444-4444-8444-444444444444"
SCHEMA = "purx"

CFG = PurchasingConfig(schema=SCHEMA)
FIN_CFG = FinanceConfig(schema=SCHEMA, with_parties=True)
INV_CFG = InventoryConfig(schema=SCHEMA, with_items=False)

#: Roles by bearer token: who is an org admin / is in the org-A approver list / belongs to org B.
ROLES = {
    "user": dict(admin=False, approve=False, org=ORG_A, uid="00000000-0000-4000-8000-000000000001"),
    "admin": dict(admin=True, approve=False, org=ORG_A, uid="00000000-0000-4000-8000-000000000002"),
    "approver": dict(admin=False, approve=True, org=ORG_A, uid="00000000-0000-4000-8000-000000000003"),
    "admin-approver": dict(admin=True, approve=True, org=ORG_A, uid="00000000-0000-4000-8000-000000000004"),
    "org-b-admin": dict(admin=True, approve=False, org=ORG_B, uid="00000000-0000-4000-8000-000000000005"),
    # staff of org A whose ONLY approver grant is in org B (the old global-permission hole): must not approve in A
    "cross-org-approver": dict(admin=False, approve=False, org=ORG_A, uid="00000000-0000-4000-8000-000000000006", grant_org=ORG_B),
    "cross-org-admin-approver": dict(admin=True, approve=False, org=ORG_A, uid="00000000-0000-4000-8000-000000000007", grant_org=ORG_B),
}


@pytest.fixture
def purchasing_schema_cache():
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    generated: dict[str, set] = {}
    for label, sql in (
        ("parties", parties_migration(PartiesConfig(schema=SCHEMA), SCHEMA)),
        ("inventory", inventory_migration(INV_CFG, SCHEMA)),
        ("finance", finance_migration(FIN_CFG, SCHEMA)),
        ("purchasing", purchasing_migration(CFG, SCHEMA)),
    ):
        generated.update(parse_sql(sql, source_label=label))
    _schema_cache.set_cache_for_tests({**base, **generated})
    yield
    _schema_cache.set_cache_for_tests(base)


def make_db() -> MockSupabaseClient:
    return MockSupabaseClient(validate_schema=True, schema=SCHEMA)


@pytest.fixture
def db(purchasing_schema_cache) -> MockSupabaseClient:
    return make_db()


@pytest.fixture
def s(db) -> Scope:
    return Scope(db, CFG, ORG_A)


@pytest.fixture
def s_b(db) -> Scope:
    return Scope(db, CFG, ORG_B)


def _auth(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    role = authorization.split(" ", 1)[1]
    if role not in ROLES:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {**ROLES[role], "user_id": ROLES[role]["uid"]}


def _admin(auth: dict = Depends(_auth)) -> dict:
    if not auth["admin"]:
        raise HTTPException(status_code=403, detail="Admin only")
    return auth


def resolve(auth: dict, db: Any) -> PurchasingContext:
    return PurchasingContext(db=db, org_id=auth["org"], user_id=auth["user_id"], is_admin=auth["admin"])


@dataclass
class Harness:
    db: MockSupabaseClient
    app: FastAPI
    client: TestClient

    def as_(self, role: str = "user") -> dict:
        return {"Authorization": f"Bearer {role}"}

    @property
    def admin(self) -> dict:
        return self.as_("admin")


def build_harness(cfg: PurchasingConfig = CFG, **router_kw: Any) -> Harness:
    db = make_db()
    for spec in ROLES.values():  # approver grants live in the organ's own org-scoped table
        grant_org = spec.get("grant_org") or (spec["org"] if spec["approve"] else None)
        if grant_org:
            db.table("pur_approvers").insert({"org_id": grant_org, "user_id": spec["uid"]}).execute()
    router = make_purchasing_router(cfg, _auth, _admin, resolve_context=resolve, get_db=lambda: db, **router_kw)
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return Harness(db, app, TestClient(app))


@pytest.fixture
def h(purchasing_schema_cache) -> Harness:
    return build_harness()


def seed_order(db: MockSupabaseClient, *, org: str = ORG_A, status: str = "approved", total: int = 100_000, **over: Any) -> dict:
    row = {
        "id": ORDER, "org_id": org, "number": 1, "status": status, "party_id": None, "supplier_name": "Fornecedor Ltda",
        "warehouse_id": WH1, "installments_count": 1, "first_due_days": 30, "interval_days": 30, "freight_cents": 0,
        "discount_cents": 0, "other_cents": 0, "goods_cents": total, "total_cents": total, "approved_at": "2026-10-14T12:00:00+00:00",
        **over,
    }
    db.table("pur_orders").insert(row).execute()
    return row


def seed_line(db: MockSupabaseClient, line_id: str, *, org: str = ORG_A, item: str = ITEM, no: int = 1, qty: str = "10.000", cost: int = 10_000) -> dict:
    row = {
        "id": line_id, "org_id": org, "order_id": ORDER, "line_no": no, "item_id": item, "description": f"Item {no}",
        "qty": qty, "unit_cost_cents": cost, "line_total_cents": int(float(qty) * cost), "received_qty": "0.000",
    }
    db.table("pur_order_lines").insert(row).execute()
    return row


def seed_receipt(db: MockSupabaseClient, receipt_id: str, *, org: str = ORG_A, no: int = 1, received_on: str = "2026-10-14",
                 goods: int = 100_000, adj: int = 0, **over: Any) -> dict:
    row = {
        "id": receipt_id, "org_id": org, "order_id": ORDER, "receipt_no": no, "received_on": received_on, "goods_cents": goods,
        "adjustment_cents": adj, "total_cents": goods + adj, "order_goods_before_cents": 0, **over,
    }
    db.table("pur_receipts").insert(row).execute()
    return row


def seed_receipt_line(db: MockSupabaseClient, rl_id: str, receipt_id: str, line_id: str, *, org: str = ORG_A, qty: str = "10.000",
                      cost: int = 10_000, landed: int = 10_000, adj: int = 0) -> dict:
    row = {
        "id": rl_id, "org_id": org, "receipt_id": receipt_id, "order_line_id": line_id, "qty": qty, "unit_cost_cents": cost,
        "goods_cents": int(float(qty) * cost), "adjustment_cents": adj, "landed_unit_cost_cents": landed,
    }
    db.table("pur_receipt_lines").insert(row).execute()
    return row
