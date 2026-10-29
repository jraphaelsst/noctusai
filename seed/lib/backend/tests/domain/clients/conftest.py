"""Harness of the clients organ suite.

The Real store runs against the repo's PostgREST double with `validate_schema=True`, whose schema map is the one
EMITTED BY `clients_table_ddl` -- a column the code writes that the DDL forgot fails here. Money goes through the
finance seam's own Fake (`FakeFinanceBooking`: real idempotency keys, amounts, settlements). The clock is the
service's injected seam; auth is a real FastAPI dependency pair. Nothing of ours is monkeypatched.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.clients import (
    ClientsConfig,
    ClientsService,
    FakeClientsStore,
    SupabaseClientsStore,
    clients_table_ddl,
    create_clients_router,
)
from noctusai_lib.domain.finance import FakeFinanceBooking
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
ACCOUNT = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
SCHEMA = "clientsx"
VALID_CPF = "52998224725"

CFG = ClientsConfig(noun_singular="Paciente", noun_plural="Pacientes", timezone="America/Sao_Paulo")

#: Monday 2026-11-02 12:00 UTC = 09:00 in São Paulo
T0 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, at: datetime = T0) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


@pytest.fixture
def clients_schema_cache():
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    _schema_cache.set_cache_for_tests({**base, **parse_sql(clients_table_ddl(SCHEMA, CFG), source_label="clients_table_ddl")})
    yield
    _schema_cache.set_cache_for_tests(base)


def _real() -> SupabaseClientsStore:
    return SupabaseClientsStore(MockSupabaseClient(validate_schema=True, schema=SCHEMA), CFG)


@pytest.fixture(params=["fake", "real"])
def store(request, clients_schema_cache):
    """The SAME suite runs against both stores: the Fake is only trustworthy while it behaves like the Real one."""
    return FakeClientsStore() if request.param == "fake" else _real()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def booking() -> FakeFinanceBooking:
    return FakeFinanceBooking()


@pytest.fixture
def svc(store, booking, clock) -> ClientsService:
    return ClientsService(store, CFG, booking, clock=clock)


class _User:
    id = "00000000-0000-4000-8000-000000000001"


class _Auth(tuple):
    is_admin: bool = False


def _auth(authorization: Optional[str] = Header(None)) -> tuple:
    """`Bearer org-a[-admin]` / `Bearer org-b[-admin]`; anything else is a strict 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    out = _Auth((_User(), "tok", ORG_B if token.startswith("org-b") else ORG_A))
    out.is_admin = token.endswith("-admin")
    return out


def _admin(a: tuple = Depends(_auth)) -> tuple:
    if not getattr(a, "is_admin", False):
        raise HTTPException(status_code=403, detail="restrito a administradores")
    return a


@dataclass
class Harness:
    store: object
    booking: FakeFinanceBooking
    clock: Clock
    client: TestClient

    def a(self, admin: bool = False) -> dict:
        return {"Authorization": "Bearer org-a" + ("-admin" if admin else "")}

    def b(self, admin: bool = False) -> dict:
        return {"Authorization": "Bearer org-b" + ("-admin" if admin else "")}


def build_harness(store, booking, clock) -> Harness:
    router = create_clients_router(
        store_factory=lambda: store, get_current_user_org=_auth, admin_dependency=_admin, config=CFG,
        booking_factory=lambda: booking,
    )
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return Harness(store, booking, clock, TestClient(app))


@pytest.fixture
def h(store, booking, clock) -> Harness:
    return build_harness(store, booking, clock)
