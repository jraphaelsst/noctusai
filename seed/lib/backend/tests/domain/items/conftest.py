"""Shared harness for the items organ suite.

The mock PostgREST client validates EVERY column the code touches against the schema EMITTED BY
`items_migration` (via the mock's own `set_cache_for_tests` seam), so a column the services write that the
generator forgot fails here. Nothing is monkeypatched: db is the factory's own DI seam, auth is a real
FastAPI dependency pair (staff read / admin write).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.items import ItemsConfig, ItemsContext, items_migration, make_items_router
from noctusai_lib.domain.items._common import Scope
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
SCHEMA = "itx"
CFG = ItemsConfig(schema=SCHEMA)

#: A real EAN-13 (check digit 5) and a real UPC-A (check digit 2) -- GS1 worked examples.
EAN13 = "7891000100103"
GTIN8 = "40170725"


@pytest.fixture
def items_schema_cache():
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    generated = parse_sql(items_migration(CFG), source_label="items_migration")
    _schema_cache.set_cache_for_tests({**base, **generated})
    yield
    _schema_cache.set_cache_for_tests(base)


@pytest.fixture
def db(items_schema_cache) -> MockSupabaseClient:
    return MockSupabaseClient(validate_schema=True, schema=SCHEMA)


@pytest.fixture
def s(db) -> Scope:
    return Scope(db, CFG, ORG_A)


@pytest.fixture
def s_b(db) -> Scope:
    """Org B on the SAME database -- for isolation tests."""
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


def _resolve(auth: dict, db: Any) -> ItemsContext:
    return ItemsContext(db=db, org_id=auth["org_id"], user_id=auth["user_id"], is_admin=auth["admin"])


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

    @property
    def admin_b(self) -> dict:
        return self.staff("org-b-admin")


@pytest.fixture
def h(items_schema_cache) -> Harness:
    db = MockSupabaseClient(validate_schema=True, schema=SCHEMA)
    router = make_items_router(CFG, _auth, _admin, resolve_context=_resolve, get_db=lambda: db)
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return Harness(db, app, TestClient(app))


def mk_item(s: Scope, sku: str = "SKU-1", **over: Any) -> dict:
    from noctusai_lib.domain.items import items

    return items.create_item(s, {"sku": sku, "name": over.pop("name", f"Item {sku}"), **over})
