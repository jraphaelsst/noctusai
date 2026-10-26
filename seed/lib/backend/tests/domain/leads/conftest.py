"""Harness of the leads organ suite.

The Real store runs against the repo's PostgREST double with `validate_schema=True`, whose schema map is the
one EMITTED BY `leads_table_ddl` -- a column the code writes that the DDL forgot fails here. Auth is a real
FastAPI dependency (bearer role => org); nothing of ours is monkeypatched.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.leads import (
    FakeLeadsStore,
    LeadOrigin,
    LeadsConfig,
    LeadsService,
    LeadStage,
    SupabaseLeadsStore,
    create_leads_router,
    leads_table_ddl,
)
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
CONN = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
SCHEMA = "leadsx"

CFG = LeadsConfig(
    stages=[
        LeadStage("lead", "Lead"),
        LeadStage("atendimento", "Atendimento"),
        LeadStage("negociacao", "Negociação"),
        LeadStage("fechado", "Fechado", "success"),
    ],
    origins=[
        LeadOrigin("whatsapp", "WhatsApp"),
        LeadOrigin("instagram", "Instagram"),
        LeadOrigin("indicacao", "Indicação"),
        LeadOrigin("outro", "Outro"),
    ],
)


@pytest.fixture
def leads_schema_cache():
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    _schema_cache.set_cache_for_tests({**base, **parse_sql(leads_table_ddl(SCHEMA), source_label="leads_table_ddl")})
    yield
    _schema_cache.set_cache_for_tests(base)


def _fake() -> FakeLeadsStore:
    return FakeLeadsStore()


def _real() -> SupabaseLeadsStore:
    return SupabaseLeadsStore(MockSupabaseClient(validate_schema=True, schema=SCHEMA), table="leads")


@pytest.fixture(params=["fake", "real"])
def store(request, leads_schema_cache):
    """The SAME suite runs against both stores: the Fake is only trustworthy while it behaves like the Real one."""
    return _fake() if request.param == "fake" else _real()


@pytest.fixture
def svc(store) -> LeadsService:
    return LeadsService(store, CFG)


def _auth(authorization: Optional[str] = Header(None)) -> tuple:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    org = ORG_B if authorization.split(" ", 1)[1].startswith("org-b") else ORG_A

    class _User:
        id = "00000000-0000-4000-8000-000000000001"

    return _User(), "tok", org


@dataclass
class Harness:
    store: object
    service: LeadsService
    client: TestClient

    def a(self) -> dict:
        return {"Authorization": "Bearer org-a"}

    def b(self) -> dict:
        return {"Authorization": "Bearer org-b"}


def build_harness(store) -> Harness:
    router = create_leads_router(store_factory=lambda: store, get_current_user_org=_auth, config=CFG)
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return Harness(store, LeadsService(store, CFG), TestClient(app))


@pytest.fixture
def h(store) -> Harness:
    return build_harness(store)
