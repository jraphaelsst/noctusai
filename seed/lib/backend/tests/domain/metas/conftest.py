"""Harness of the metas organ suite.

The service suite runs against BOTH stores: the Fake, and the Real `SupabaseMetasStore` over the repo's PostgREST double with
`validate_schema=True` whose schema map is the one EMITTED BY `metas_migration` -- a column the code writes that the DDL
forgot fails here. The SQL aggregate (`event_totals`) is a Postgres function the double cannot execute: for the Real store it
is served by Python over the same rows (the function itself is probed on PGlite in
`mcp/noctusai/tests/test_organ_guard_probes.py`). Auth is a real FastAPI dependency (bearer role => org + admin flag).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.metas import (
    EventType,
    FakeMetasStore,
    GoalCategory,
    MetasActor,
    MetasConfig,
    MetasService,
    Modality,
    RuleSeed,
    SupabaseMetasStore,
    create_metas_router,
    metas_migration,
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
ADMIN = "00000000-0000-4000-8000-0000000000a1"
ANA = "00000000-0000-4000-8000-0000000000b1"
BIA = "00000000-0000-4000-8000-0000000000b2"
CAIO = "00000000-0000-4000-8000-0000000000b3"
SCHEMA = "metasx"

CFG = MetasConfig(
    schema=SCHEMA,
    event_types=(EventType("captacao", "Captação"), EventType("venda", "Venda"), EventType("visita", "Visita")),
    modalities=(Modality("padrao", "Padrão"), Modality("compartilhada", "Compartilhada")),
    categories=(
        GoalCategory("vgv", "VGV", "value"),
        GoalCategory("vendas", "Vendas", "count:venda"),
        GoalCategory("pontos", "Pontos", "points"),
        GoalCategory("pessoal", "Pessoal", "manual"),
    ),
    default_rules=(RuleSeed("captacao", "padrao", 1.0), RuleSeed("venda", "padrao", 50.0), RuleSeed("venda", "compartilhada", 25.0)),
)


@pytest.fixture
def metas_schema_cache():
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    _schema_cache.set_cache_for_tests({**base, **parse_sql(metas_migration(CFG), source_label="metas_migration")})
    yield
    _schema_cache.set_cache_for_tests(base)


class RealWithAggregate(SupabaseMetasStore):
    """The Real store whose RPC aggregate is computed in Python over the same double."""

    def event_totals(self, org_id, start, end, *, members=None, team_id=None):
        return FakeMetasStore.event_totals(self, org_id, start, end, members=members, team_id=team_id)  # type: ignore[arg-type]


@pytest.fixture(params=["fake", "real"])
def store(request, metas_schema_cache):
    """The SAME suite runs against both stores: the Fake is only trustworthy while it behaves like the Real one."""
    if request.param == "fake":
        return FakeMetasStore(CFG)
    return RealWithAggregate(MockSupabaseClient(validate_schema=True, schema=SCHEMA), CFG)


@pytest.fixture
def svc(store) -> MetasService:
    return MetasService(store, CFG)


def actor(org: str = ORG_A, user: str = ADMIN, admin: bool = True) -> MetasActor:
    return MetasActor(org, user, admin)


ROLES = {"admin": (ADMIN, True), "ana": (ANA, False), "bia": (BIA, False), "caio": (CAIO, False)}


class _Auth(tuple):
    is_admin: bool = False


def _auth(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    org = ORG_B if token.startswith("b-") else ORG_A
    uid, is_admin = ROLES[token[2:] if token.startswith("b-") else token]

    class _User:
        id = uid

    a = _Auth((_User(), "tok", org))
    a.is_admin = is_admin
    return a


async def _admin_dep(authorization: Optional[str] = Header(None)):
    a = _auth(authorization)
    if not a.is_admin:
        raise HTTPException(status_code=403, detail="Metas restrito a administradores.")
    return a


@dataclass
class Harness:
    store: object
    client: TestClient

    def as_(self, who: str = "admin", org: str = "a") -> dict:
        return {"Authorization": f"Bearer {'b-' + who if org == 'b' else who}"}


def build_harness(store) -> Harness:
    router = create_metas_router(CFG, _auth, _admin_dep, get_store=lambda: store)
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return Harness(store, TestClient(app))


@pytest.fixture
def h() -> Harness:
    """HTTP harness on the Fake: the PostgREST double mints non-UUID ids (`mock-mt_periods-1`) that the router's UUID path
    params correctly refuse; the Real store's behaviour is covered by the service suite (both stores)."""
    return build_harness(FakeMetasStore(CFG))


@pytest.fixture
def unique_enforced(store):
    """Skip (loudly) for a store whose double cannot enforce UNIQUE indexes: the PostgREST double has no index engine."""
    if isinstance(store, RealWithAggregate):
        pytest.skip(
            "the PostgREST double does not enforce UNIQUE indexes; the guards are probed on PGlite "
            "(mcp/noctusai/tests/test_organ_guard_probes.py) and the 23505 -> StoreConflict mapping is pinned in test_table_store.py"
        )
