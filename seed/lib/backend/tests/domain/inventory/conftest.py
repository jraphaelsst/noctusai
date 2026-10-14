"""Shared harness for the inventory organ suite.

The mock PostgREST client validates EVERY column the code touches against the schema EMITTED BY
`inventory_migration` (through the mock's own `set_cache_for_tests` seam). RPC behaviour (locks, moving average,
overselling) is proven on a real Postgres in `test_inventory_on_real_postgres.py`; here `rpc()` is the mock's own
canned-data seam, so these tests cover what is Python's job: org scoping, auth, validation, the refusal -> HTTP map.
Nothing is monkeypatched: db is the factory's DI seam, auth is a real FastAPI dependency pair (staff read / admin write).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.inventory import InventoryConfig, InventoryContext, inventory_migration, make_inventory_router
from noctusai_lib.domain.inventory._common import Scope
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from noctusai_lib.testing import _schema_cache
from noctusai_lib.testing.migration_parser import parse_function_sql, parse_sql
from noctusai_lib.testing.mocks import MockSupabaseClient

ORG_A = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b"
ORG_B = "9c8d7e6f-5a4b-4c3d-8e2f-1a0b9c8d7e6f"
USER_ID = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
ITEM = "11111111-1111-4111-8111-111111111111"
ITEM2 = "22222222-2222-4222-8222-222222222222"
WH1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
WH2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SCHEMA = "invx"

CFG = InventoryConfig(schema=SCHEMA)


@pytest.fixture
def inventory_schema_cache():
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    generated = parse_sql(inventory_migration(CFG, SCHEMA), source_label="inventory_migration")
    _schema_cache.set_cache_for_tests({**base, **generated})
    # RPCs resolve by argument NAME against the generated function signatures (PGRST202 otherwise).
    prev_fns = _schema_cache.set_functions_for_tests(parse_function_sql(inventory_migration(CFG, SCHEMA)))
    yield
    _schema_cache.set_cache_for_tests(base)
    _schema_cache.set_functions_for_tests(prev_fns, merge=False)


def make_db() -> MockSupabaseClient:
    return MockSupabaseClient(validate_schema=True, schema=SCHEMA)


@pytest.fixture
def db(inventory_schema_cache) -> MockSupabaseClient:
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
    return {"org_id": ORG_B if role.startswith("org-b") else ORG_A, "user_id": USER_ID, "admin": role in ("admin", "org-b-admin")}


def _admin(auth: dict = Depends(_auth)) -> dict:
    if not auth["admin"]:
        raise HTTPException(status_code=403, detail="Admin only")
    return auth


def _resolve(auth: dict, db: Any) -> InventoryContext:
    return InventoryContext(db=db, org_id=auth["org_id"], user_id=auth["user_id"], is_admin=auth["admin"])


@dataclass
class Harness:
    db: MockSupabaseClient
    app: FastAPI
    client: TestClient

    def staff(self, role: str = "user") -> dict:
        return {"Authorization": f"Bearer {role}"}

    @property
    def admin(self) -> dict:
        return self.staff("admin")


def build_harness() -> Harness:
    db = make_db()
    router = make_inventory_router(CFG, _auth, _admin, resolve_context=_resolve, get_db=lambda: db)
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return Harness(db, app, TestClient(app))


@pytest.fixture
def h(inventory_schema_cache) -> Harness:
    return build_harness()
