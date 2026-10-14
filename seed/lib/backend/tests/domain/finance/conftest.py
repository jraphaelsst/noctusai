"""Shared harness for the finance organ suite.

The mock PostgREST client validates EVERY column the code touches against the schema
EMITTED BY `finance_migration` (injected through the mock's own `set_cache_for_tests`
seam), so a column the services write that the generator forgot fails here, not in prod.
Nothing is monkeypatched: db and storage are the factories' own DI seams, auth is a real
FastAPI dependency pair (staff read / admin write).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.finance import (
    FinanceConfig,
    FinanceContext,
    finance_migration,
    make_finance_router,
)
from noctusai_lib.domain.finance._common import Scope
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from noctusai_lib.testing import _schema_cache
from noctusai_lib.testing.migration_parser import parse_function_sql, parse_sql
from noctusai_lib.testing.mocks import MockSupabaseClient

from ..money_rpc import RpcMockClient

ORG_A = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b"
ORG_B = "9c8d7e6f-5a4b-4c3d-8e2f-1a0b9c8d7e6f"
USER_ID = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
SCHEMA = "finx"
VALID_CPF = "52998224725"
VALID_CNPJ = "11222333000181"

CFG = FinanceConfig(schema=SCHEMA)


def run(coro):
    """Drive a coroutine to completion (the suite does not depend on an asyncio pytest plugin)."""
    return asyncio.run(coro)


@pytest.fixture
def finance_schema_cache():
    """Extend the mock's migration-derived schema map with the organ's generator output
    (restored afterwards: a reset would re-parse every product's migrations)."""
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    generated = parse_sql(finance_migration(CFG, SCHEMA), source_label="finance_migration")
    _schema_cache.set_cache_for_tests({**base, **generated})
    prev_fns = _schema_cache.set_functions_for_tests(parse_function_sql(finance_migration(CFG, SCHEMA)))
    yield
    _schema_cache.set_cache_for_tests(base)
    _schema_cache.set_functions_for_tests(prev_fns, merge=False)


def make_db() -> MockSupabaseClient:
    return RpcMockClient(validate_schema=True, schema=SCHEMA)


@pytest.fixture
def db(finance_schema_cache) -> MockSupabaseClient:
    return make_db()


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
    return {
        "org_id": ORG_B if role.startswith("org-b") else ORG_A,
        "user_id": USER_ID,
        "admin": role in ("admin", "org-b-admin"),
    }


def _admin(auth: dict = Depends(_auth)) -> dict:
    if not auth["admin"]:
        raise HTTPException(status_code=403, detail="Admin only")
    return auth


def _resolve(auth: dict, db: Any) -> FinanceContext:
    return FinanceContext(db=db, org_id=auth["org_id"], user_id=auth["user_id"], is_admin=auth["admin"])


@dataclass
class Harness:
    db: MockSupabaseClient
    storage: FakeStorageBackend
    app: FastAPI
    client: TestClient

    def staff(self, role: str = "user") -> dict:
        return {"Authorization": f"Bearer {role}"}

    @property
    def admin(self) -> dict:
        return self.staff("admin")


def build_harness() -> Harness:
    db = make_db()
    storage = FakeStorageBackend()
    router = make_finance_router(
        CFG, _auth, _admin, resolve_context=_resolve, get_db=lambda: db, get_storage=lambda: storage
    )
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return Harness(db, storage, app, TestClient(app))


@pytest.fixture
def h(finance_schema_cache) -> Harness:
    return build_harness()


# ── domain seeding through the services themselves ──────────────────────────


def mk_account(s: Scope, name: str = "Banco", kind: str = "checking", **over: Any) -> dict:
    from noctusai_lib.domain.finance import accounts

    return accounts.create_account(s, {"name": name, "kind": kind, **over})


def mk_entry(s: Scope, **over: Any) -> dict:
    from noctusai_lib.domain.finance import entries

    data = {
        "direction": "receivable",
        "description": "Mensalidade",
        "due_date": "2026-10-20",
        "amount_cents": 10000,
        **over,
    }
    return entries.create_entry(s, data)[0]
