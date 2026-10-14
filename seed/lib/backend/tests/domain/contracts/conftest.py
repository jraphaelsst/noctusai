"""Shared harness for the contracts organ suite.

The mock PostgREST client validates EVERY column the code touches against the schema EMITTED BY the
generators (`contracts_migration` + the parties / finance ones the organ talks to), injected through the
mock's own `set_cache_for_tests` seam. Nothing is monkeypatched: db, storage, billing and the signature
adapter are the factories' own DI seams, auth is a real FastAPI dependency pair (staff read / admin write).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.contracts import (
    ContractsConfig, ContractsContext, FakeContractsBilling, contracts_migration, make_contracts_router,
)
from noctusai_lib.domain.contracts._common import Scope
from noctusai_lib.domain.finance import FinanceConfig, finance_migration
from noctusai_lib.domain.parties import PartiesConfig, parties_migration
from noctusai_lib.integrations.signature import make_signature_adapter
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.primitives.exceptions import (
    AppException, app_exception_handler, http_exception_handler, validation_exception_handler,
)
from noctusai_lib.testing import _schema_cache
from noctusai_lib.testing.migration_parser import parse_function_sql, parse_sql
from noctusai_lib.testing.mocks import MockSupabaseClient

ORG_A = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b"
ORG_B = "9c8d7e6f-5a4b-4c3d-8e2f-1a0b9c8d7e6f"
USER_ID = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
SCHEMA = "ctrx"
VALID_CPF = "52998224725"
VALID_CPF_2 = "11144477735"
ITEM_DDL = f"CREATE TABLE IF NOT EXISTS {SCHEMA}.itm_items (id UUID PRIMARY KEY, org_id UUID NOT NULL, name TEXT);"

CFG = ContractsConfig(schema=SCHEMA, with_parties=True, with_items=True)
FIN_CFG = FinanceConfig(schema=SCHEMA)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def contracts_schema_cache():
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    sql = "\n".join([contracts_migration(CFG, SCHEMA), parties_migration(PartiesConfig(schema=SCHEMA), SCHEMA),
                     finance_migration(FIN_CFG, SCHEMA), ITEM_DDL])
    _schema_cache.set_cache_for_tests({**base, **parse_sql(sql, source_label="contracts_migration")})
    prev_fns = _schema_cache.set_functions_for_tests(parse_function_sql(sql))
    yield
    _schema_cache.set_cache_for_tests(base)
    _schema_cache.set_functions_for_tests(prev_fns, merge=False)


def make_db() -> MockSupabaseClient:
    return MockSupabaseClient(validate_schema=True, schema=SCHEMA)


@pytest.fixture
def db(contracts_schema_cache) -> MockSupabaseClient:
    return make_db()


@pytest.fixture
def s(db) -> Scope:
    return Scope(db, CFG, ORG_A)


@pytest.fixture
def s_b(db) -> Scope:
    return Scope(db, CFG, ORG_B)


@pytest.fixture
def billing() -> FakeContractsBilling:
    return FakeContractsBilling()


def _auth(authorization: str | None = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    role = authorization.split(" ", 1)[1]
    return {"org_id": ORG_B if role.startswith("org-b") else ORG_A, "user_id": USER_ID, "admin": role in ("admin", "org-b-admin")}


def _admin(auth: dict = Depends(_auth)) -> dict:
    if not auth["admin"]:
        raise HTTPException(status_code=403, detail="Admin only")
    return auth


def _resolve(auth: dict, db: Any) -> ContractsContext:
    return ContractsContext(db=db, org_id=auth["org_id"], user_id=auth["user_id"], is_admin=auth["admin"])


@dataclass
class Harness:
    db: MockSupabaseClient
    app: FastAPI
    client: TestClient
    billing: FakeContractsBilling
    storage: FakeStorageBackend
    adapter: Any

    def staff(self, role: str = "user") -> dict:
        return {"Authorization": f"Bearer {role}"}

    @property
    def admin(self) -> dict:
        return self.staff("admin")


def build_harness(*, with_signature: bool = True, with_storage: bool = True) -> Harness:
    db, billing, storage = make_db(), FakeContractsBilling(), FakeStorageBackend()
    adapter = make_signature_adapter()
    router = make_contracts_router(
        CFG, _auth, _admin, resolve_context=_resolve, get_db=lambda: db, get_billing=lambda _db: billing,
        get_signature=(lambda _ctx: adapter) if with_signature else None,
        get_storage=(lambda: storage) if with_storage else None,
    )
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return Harness(db, app, TestClient(app), billing, storage, adapter)


@pytest.fixture
def h(contracts_schema_cache) -> Harness:
    return build_harness()


def body(**over: Any) -> dict:
    """A valid recurring contract body."""
    return {"title": "Gestão de tráfego", "billing_model": "recurring", "amount_cents": 150000, "due_day": 10,
            "first_due_date": "2026-11-10", "start_date": "2026-11-01", **over}


def mk(s: Scope, **over: Any) -> dict:
    from noctusai_lib.domain.contracts import contracts

    return contracts.create_contract(s, body(**over), user_id=USER_ID)


def mk_party(s: Scope, name: str = "Ana Souza", doc: str | None = VALID_CPF) -> dict:
    from noctusai_lib.domain.parties import parties

    return parties.create_party(Scope_parties(s), {"kind": "PF", "legal_name": name, "doc": doc})


def Scope_parties(s: Scope):
    from noctusai_lib.domain.parties._common import Scope as PScope

    return PScope(s.db, PartiesConfig(schema=SCHEMA), s.org_id)


D = date
