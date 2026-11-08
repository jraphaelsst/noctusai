"""Shared harness for the funnel-organ suite.

Two funnels are built per test, by NAME ONLY (no product import), the way the
card-hub suite builds `lead` and `sw`:

- ``org``      — tenancy="org": card table `crm.oportunidades` carries `org_id`.
- ``platform`` — tenancy="platform": card table `plat.leads_site` has NO `org_id`
  (the shape of core's `website_leads`); the funnel's own rows carry the one
  declared `PLATFORM_ORG`.

The mock validates every column the code touches against the schema EMITTED BY
`pipeline_migration` (plus a hand-written card table), injected through the
mock's own test seam (`set_cache_for_tests`) -- so a column the code writes but
the DDL does not create fails here. Nothing is monkeypatched: auth, db and the
audit sink are the factory's own DI seams.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.pipeline import PipelineConfig, PipelineContext, pipeline_migration
from noctusai_lib.domain.pipeline.funnel import (
    FunnelAction,
    FunnelConfig,
    FunnelGate,
    LostReason,
    Pendencia,
    mount_funnel,
)
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from noctusai_lib.primitives.responses import success_response
from noctusai_lib.testing import _schema_cache
from noctusai_lib.testing.migration_parser import parse_sql
from noctusai_lib.testing.mocks import MockSupabaseClient

ORG = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b"
OTHER_ORG = "a1a1a1a1-2222-4333-8444-555555555555"
PLATFORM_ORG = "0d0d0d0d-1111-4222-8333-444444444444"
USER = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
HEADERS = {"Authorization": "Bearer t", "X-Org": ORG, "X-Can-Write": "1"}
READ_ONLY = {"Authorization": "Bearer t", "X-Org": ORG}

#: A stage carrying this role is behind a gate.
GATED_ROLE = "proposta_aceite"

_ORG_CARDS = """
CREATE TABLE IF NOT EXISTS crm.oportunidades (
    id UUID PRIMARY KEY, org_id UUID NOT NULL, titulo TEXT, valor NUMERIC,
    responsavel_id UUID, telefone TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
);
"""
_PLATFORM_CARDS = """
CREATE TABLE IF NOT EXISTS plat.leads_site (
    id UUID PRIMARY KEY, titulo TEXT, valor NUMERIC,
    responsavel_id UUID, telefone TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
);
"""

LOST = (
    LostReason("preco", "Preço"),
    LostReason("outro", "Outro", exige_texto=True),
)


def _checklist_gate(db: Any, ctx: Any, card: dict) -> list[Pendencia]:
    """Refuse entering the gated stage until the card has a phone, or the
    operator confirms by other means via the declared `confirmado` input."""
    if card.get("telefone") or ctx.extra.get("confirmado") is True:
        return []
    return [Pendencia("telefone", "Informe o telefone antes de avançar.")]


def make_cfg(tenancy: str, **overrides: Any) -> FunnelConfig:
    table = "oportunidades" if tenancy == "org" else "leads_site"

    def _aceitar(db: Any, ctx: Any, card: dict, payload: dict) -> dict:
        db.table(table).update({"valor": payload.get("valor", 1)}).eq("id", card["id"]).execute()
        return {"aceito": True, "valor": payload.get("valor", 1)}

    base = dict(
        pipeline=PipelineConfig(
            pipeline="crm", card_table=table, value_field="valor",
            entity_label="oportunidade", entity_kind="oportunidade", cliente_field=None,
        ),
        tenancy=tenancy,
        platform_org_id=PLATFORM_ORG if tenancy == "platform" else None,
        editable_fields={"telefone": "telefone"},
        lost_reasons=LOST,
        gates={GATED_ROLE: FunnelGate("telefone_obrigatorio", _checklist_gate, inputs=("confirmado",), mensagem="Telefone")},
        actions={
            "aceitar": FunnelAction("aceitar", "Aceitar", _aceitar, allowed_papeis=(GATED_ROLE,)),
            "livre": FunnelAction("livre", "Livre", lambda db, ctx, card, p: {"ok": True}),
        },
    )
    base.update(overrides)
    return FunnelConfig(**base)


def _auth(authorization: Optional[str] = Header(None), x_org: Optional[str] = Header(None)) -> tuple:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return (USER, x_org or None)


def _require_write(auth: tuple = Depends(_auth), x_can_write: Optional[str] = Header(None)) -> None:
    """Like a real `require_admin`: authenticates first (401), then authorises (403)."""
    if x_can_write != "1":
        raise HTTPException(status_code=403, detail="read only")


@dataclass
class Funnel:
    name: str
    cfg: FunnelConfig
    schema: str
    prefix: str
    db: MockSupabaseClient
    app: FastAPI
    client: TestClient
    audit: list = field(default_factory=list)
    stages: dict = field(default_factory=dict)

    @property
    def effective_org(self) -> str:
        return PLATFORM_ORG if self.name == "platform" else ORG

    @property
    def card_table(self) -> str:
        return self.cfg.pipeline.card_table

    def url(self, suffix: str = "") -> str:
        return f"{self.prefix}{suffix}"

    def rows(self, table: str) -> list[dict]:
        return list(self.db.table(table).select("*").execute().data or [])

    def seed(self, table: str, rows: list[dict]) -> None:
        self.db.set_table_data(table, rows)

    def add_stage(self, slug: str, *, posicao: int, papel: str | None = None, ativo: bool = True, org: str | None = None) -> str:
        sid = str(uuid4())
        row = {
            "id": sid, "org_id": org or self.effective_org, "pipeline": "crm", "slug": slug,
            "label": slug.title(), "cor": "secondary", "posicao": posicao, "papel": papel, "ativo": ativo,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }
        self.seed("pipeline_stages", [*self.rows("pipeline_stages"), row])
        self.stages[slug] = sid
        return sid

    def add_card(self, *, titulo: str = "Lead", etapa: str | None = None, pos: str = "0", valor: float = 0,
                 status: str = "aberto", org: str | None = None, **extra: Any) -> str:
        cid = str(uuid4())
        row = {
            "id": cid, "titulo": titulo, "valor": valor, "responsavel_id": None, "telefone": None,
            "etapa_id": self.stages[etapa] if etapa else None, "kanban_pos": pos, "status": status,
            "motivo_perda_codigo": None, "motivo_perda": None,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }
        if self.name == "org":
            row["org_id"] = org or ORG
        row.update(extra)
        self.seed(self.card_table, [*self.rows(self.card_table), row])
        return cid

    def card(self, card_id: str) -> dict:
        return next(r for r in self.rows(self.card_table) if r["id"] == card_id)

    def movimentos(self, card_id: str | None = None) -> list[dict]:
        rows = self.rows("pipeline_movimentos")
        return [r for r in rows if card_id is None or r["entidade_id"] == card_id]

    def snapshot(self) -> tuple:
        """Everything a write could touch -- compared before/after a refused call."""
        return (
            repr(self.rows(self.card_table)), repr(self.rows("pipeline_movimentos")),
            repr(self.rows("pipeline_stages")), len(self.audit),
        )


def build_funnel(name: str, *, cfg: FunnelConfig | None = None, schema_validate: bool = True,
                 with_write_gate: bool = True, resolve: Callable | None = None) -> Funnel:
    schema = "crm" if name == "org" else "plat"
    prefix = "/api/funil" if name == "org" else "/api/admin/funnel"
    cfg = cfg or make_cfg(name)
    db = MockSupabaseClient(validate_schema=schema_validate, schema=schema)
    audit: list = []

    def resolve_context(auth: tuple) -> PipelineContext:
        user, org = auth
        return PipelineContext(db=db, org_id=org, user_id=user)

    def log_action(*args: Any) -> None:
        audit.append(args)

    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    mount_funnel(
        app, cfg, prefix=prefix, auth_dependency=_auth, resolve_context=resolve or resolve_context,
        success_response=success_response, log_action=log_action,
        require_stage_admin=_require_write if with_write_gate else None,
        require_card_write=_require_write if with_write_gate else None,
    )
    funnel = Funnel(name=name, cfg=cfg, schema=schema, prefix=prefix, db=db, app=app,
                    client=TestClient(app, raise_server_exceptions=False), audit=audit)
    return funnel


@pytest.fixture
def funnel_schema_cache():
    """Extend the mock's migration-derived schema map with the funnels' DDL
    (via the mock's own `set_cache_for_tests` seam), restoring it afterwards."""
    base = {table: set(cols) for table, cols in _schema_cache.get_schema_map().items()}
    generated: dict = {}
    for name, schema, cards, tier in (("org", "crm", _ORG_CARDS, "org"), ("platform", "plat", _PLATFORM_CARDS, "platform")):
        cfg = make_cfg(name)
        sql = f"CREATE SCHEMA IF NOT EXISTS {schema};\n" + cards + pipeline_migration(cfg.pipeline, schema, tier=tier)
        generated.update(parse_sql(sql, source_label=f"pipeline_migration({name})"))
    _schema_cache.set_cache_for_tests({**base, **generated})
    yield
    _schema_cache.set_cache_for_tests(base)


@pytest.fixture(params=["org", "platform"])
def fn(request, funnel_schema_cache) -> Funnel:
    """A funnel with three active stages: entrada -> proposta (GATED) -> fechado."""
    f = build_funnel(request.param)
    f.add_stage("entrada", posicao=0)
    f.add_stage("proposta", posicao=1, papel=GATED_ROLE)
    f.add_stage("fechado", posicao=2)
    return f


@pytest.fixture
def org_fn(funnel_schema_cache) -> Funnel:
    f = build_funnel("org")
    f.add_stage("entrada", posicao=0)
    f.add_stage("proposta", posicao=1, papel=GATED_ROLE)
    f.add_stage("fechado", posicao=2)
    return f
