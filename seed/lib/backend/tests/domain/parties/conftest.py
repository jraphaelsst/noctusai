"""Shared harness for the parties organ suite.

The mock PostgREST client validates EVERY column the code touches against the schema EMITTED BY
`parties_migration` (through the mock's own `set_cache_for_tests` seam), so a column the services
write that the generator forgot fails here, not in prod. Nothing is monkeypatched: db is the
factory's own DI seam, auth is a real FastAPI dependency pair (staff read / admin write).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.parties import PartiesConfig, PartiesContext, make_parties_router, parties_migration
from noctusai_lib.domain.parties._common import Scope
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
SCHEMA = "ptyx"
VALID_CPF = "52998224725"
VALID_CPF_2 = "11144477735"
VALID_CNPJ = "11222333000181"

#: A stand-in for ANOTHER organ's table pointing at a party (the finance link, later).
REF_DDL = f"CREATE TABLE IF NOT EXISTS {SCHEMA}.ref_things (id UUID PRIMARY KEY, org_id UUID NOT NULL, party_id UUID);"

CFG = PartiesConfig(schema=SCHEMA, reference_tables=(("ref_things", "party_id"),))


@pytest.fixture
def parties_schema_cache():
    """Extend the mock's migration-derived schema map with the generator's output (restored afterwards)."""
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    generated = parse_sql(parties_migration(CFG, SCHEMA) + REF_DDL, source_label="parties_migration")
    _schema_cache.set_cache_for_tests({**base, **generated})
    yield
    _schema_cache.set_cache_for_tests(base)


def make_db() -> MockSupabaseClient:
    return MockSupabaseClient(validate_schema=True, schema=SCHEMA)


@pytest.fixture
def db(parties_schema_cache) -> MockSupabaseClient:
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


def _resolve(auth: dict, db: Any) -> PartiesContext:
    return PartiesContext(db=db, org_id=auth["org_id"], user_id=auth["user_id"], is_admin=auth["admin"])


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
    router = make_parties_router(CFG, _auth, _admin, resolve_context=_resolve, get_db=lambda: db)
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return Harness(db, app, TestClient(app))


@pytest.fixture
def h(parties_schema_cache) -> Harness:
    return build_harness()


def mk_party(s: Scope, **over: Any) -> dict:
    from noctusai_lib.domain.parties import parties

    data = {"kind": "PF", "legal_name": "Ana Souza", **over}
    return parties.create_party(s, data)
