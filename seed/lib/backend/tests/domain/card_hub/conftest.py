"""Shared harness for the seed card-hub suite.

Every behavioural test runs TWICE, once per config (`hub` is parametrized):

- ``lead`` — a neutral config (igig-shaped: entity ``leads``, members in
  ``membros_equipe``, schema ``crm``, no stage FK). Its mock validates every
  column the code touches against the schema EMITTED BY
  ``card_hub_migration`` — injected through the mock's own test seam
  (``set_cache_for_tests``) — so a column the code writes but the template
  forgot fails here.
- ``sw`` — social-wiring's exact names (migrations 056/057/083, schema
  ``social_wiring``, ``lead_corretores`` members). Its mock validates against
  social-wiring's REAL migration files, so the lifted code is proven to still
  fit the tables it was lifted from.

Nothing here is monkeypatched: auth, db and storage are the factory's own DI
seams, overridden by construction (`KB § PATTERNS/backend/di-test-seam.md`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional
from uuid import uuid4

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.card_hub import (
    CardHubConfig,
    CardHubContext,
    MemberSource,
    card_hub_migration,
    card_hub_routers,
)
from noctusai_lib.integrations.persistence.table_reads import actor_resolver
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from noctusai_lib.testing import _schema_cache
from noctusai_lib.testing.migration_parser import parse_sql
from noctusai_lib.testing.mocks import MockSupabaseClient

ORG_ID = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b"
USER_ID = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
AUTH = {"Authorization": "Bearer test-token"}

#: The prerequisite tables `card_hub_migration` references but does not
#: create (the entity + the member source) — the neutral config's product
#: would own these in its own earlier migration.
_LEAD_PREREQS = """
CREATE TABLE IF NOT EXISTS crm.leads (
    id UUID PRIMARY KEY, org_id UUID NOT NULL, nome TEXT, created_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS crm.membros_equipe (
    id UUID PRIMARY KEY, org_id UUID NOT NULL, nome TEXT NOT NULL, cor TEXT, created_at TIMESTAMPTZ
);
"""


@dataclass
class _User:
    id: str


def _auth_dependency(authorization: Optional[str] = Header(None)) -> tuple:
    """The factory's `auth_dependency` for tests: 401 without a bearer, else
    the social-wiring-shaped `(user, token, org)` triple."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return (_User(USER_ID), authorization.split(" ", 1)[1], ORG_ID)


def _resolve_context(auth: tuple, db: Any) -> CardHubContext:
    user, _token, org = auth
    return CardHubContext(db=db, org_id=org, user_id=user.id)


def lead_config(resolver: Callable) -> CardHubConfig:
    return CardHubConfig(
        entity_kind="lead",
        entity_table="leads",
        entity_fk="lead_id",
        id_param="lead_id",
        table_prefix="lead",
        member_source=MemberSource(table="membros_equipe", fk="membro_id"),
        bucket="crm-documentos",
        actor_resolver=resolver,
        entity_datas=False,
        stage_table=None,
    )


def sw_config(resolver: Callable) -> CardHubConfig:
    """Social-wiring's card hub, by name only (no SW import)."""
    return CardHubConfig(
        entity_kind="cliente",
        entity_table="clientes",
        entity_fk="cliente_id",
        id_param="cliente_id",
        table_prefix="cliente",
        member_source=MemberSource(table="lead_corretores", fk="lead_corretor_id"),
        bucket="social-wiring-documentos",
        actor_resolver=resolver,
    )


@dataclass
class Hub:
    """One mounted card hub + its seams, for one test."""

    name: str
    cfg: CardHubConfig
    schema: str
    prefix: str
    db: MockSupabaseClient
    core: MockSupabaseClient
    storage: FakeStorageBackend
    app: FastAPI
    client: TestClient
    anon: TestClient

    # ── paths ──────────────────────────────────────────────────────────
    def url(self, entity_id: str, suffix: str = "") -> str:
        return f"{self.prefix}/{entity_id}{suffix}"

    # ── seeding ────────────────────────────────────────────────────────
    def seed(self, table: str, rows: list[dict]) -> None:
        self.db.set_table_data(table, rows)

    def rows(self, table: str) -> list[dict]:
        return self.db.table(table).select("*").execute().data or []

    def entity_row(self, id_=None, **extra) -> dict:
        row = {
            "id": id_ or str(uuid4()),
            "org_id": ORG_ID,
            "nome": "Ana",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        if self.cfg.entity_datas:
            row.update(
                {
                    "data_inicio": None,
                    "data_entrega": None,
                    "entrega_concluida": False,
                    "lembrete_minutos_antes": None,
                    "recorrencia": None,
                }
            )
        row.update(extra)
        return row

    def new_entity(self, **extra) -> str:
        row = self.entity_row(**extra)
        existing = self.db.table(self.cfg.entity_table).select("*").execute().data or []
        self.seed(self.cfg.entity_table, [*existing, row])
        return row["id"]

    def nota_row(self, id_, entity_id, *, corpo="uma nota", tipo="comentario", autor_id=None,
                 editado_em=None, deleted_at=None, created_at="2026-01-05T00:00:00+00:00") -> dict:
        return {
            "id": id_, "org_id": ORG_ID, self.cfg.entity_fk: entity_id, "autor_id": autor_id,
            "tipo": tipo, "corpo": corpo, "editado_em": editado_em, "deleted_at": deleted_at,
            "created_at": created_at,
        }

    def tag_row(self, id_, *, nome="Quente", cor="#ff0000") -> dict:
        return {"id": id_, "org_id": ORG_ID, "nome": nome, "cor": cor, "created_at": "2026-01-01T00:00:00+00:00"}

    def member_row(self, id_, *, nome="Bia", cor="#00ff00") -> dict:
        return {"id": id_, "org_id": ORG_ID, "nome": nome, "cor": cor, "created_at": "2026-01-01T00:00:00+00:00"}

    def checklist_row(self, id_, entity_id, *, titulo="Checklist", posicao=0) -> dict:
        return {
            "id": id_, "org_id": ORG_ID, self.cfg.entity_fk: entity_id, "titulo": titulo,
            "posicao": posicao, "origem": "ad_hoc", "etapa_id": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }

    def checklist_item_row(self, id_, checklist_id, *, texto="item", concluido=False,
                           concluido_em=None, concluido_por=None, posicao=0) -> dict:
        return {
            "id": id_, "org_id": ORG_ID, "checklist_id": checklist_id, "texto": texto,
            "concluido": concluido, "concluido_em": concluido_em, "concluido_por": concluido_por,
            "posicao": posicao, "created_at": "2026-01-01T00:00:00+00:00",
        }

    def documento_tipo_row(self, tipo="contrato", *, categoria="contratual", retencao_dias=1825,
                           ativo=True, identidade=False) -> dict:
        return {
            "tipo_documento": tipo, "categoria_lgpd": categoria, "retencao_dias": retencao_dias,
            "identidade": identidade, "ativo": ativo, "descricao": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }

    def documento_row(self, id_, entity_id, *, tipo_documento="contrato", categoria_lgpd="contratual",
                      deleted_at=None, retencao_ate=None, enviado_por=None,
                      created_at="2026-01-01T00:00:00+00:00") -> dict:
        return {
            "id": id_, "org_id": ORG_ID, self.cfg.entity_fk: entity_id,
            "storage_path": f"{ORG_ID}/{self.cfg.storage_segment}/{entity_id}/{id_}",
            "nome_original": "arquivo.pdf", "mime_type": "application/pdf", "tamanho_bytes": 1024,
            "tipo_documento": tipo_documento, "categoria_lgpd": categoria_lgpd,
            "retencao_ate": retencao_ate, "enviado_por": enviado_por, "deleted_at": deleted_at,
            "delete_motivo": None, "delete_solicitado_por": None, "created_at": created_at,
        }

    def checklist_extra_row(self, id_, entity_id, *, label="Convenção do condomínio", tipo="texto",
                            valor_texto=None, documento_id=None, ordem=0, deleted_at=None,
                            created_at="2026-01-01T00:00:00+00:00") -> dict:
        # No `concluido` key: completion is DERIVED, never stored.
        return {
            "id": id_, "org_id": ORG_ID, self.cfg.entity_fk: entity_id, "label": label, "tipo": tipo,
            "valor_texto": valor_texto, "documento_id": documento_id, "ordem": ordem,
            "created_at": created_at, "updated_at": created_at, "deleted_at": deleted_at,
        }


_HUBS = {
    "lead": ("crm", "/api/leads", lead_config),
    "sw": ("social_wiring", "/api/clientes", sw_config),
}


def build_hub(name: str, *, cfg_transform: Optional[Callable[[CardHubConfig], CardHubConfig]] = None,
              upload_hook=None) -> Hub:
    schema, prefix, make_cfg = _HUBS[name]
    core = MockSupabaseClient(validate_schema=False, schema="public")
    core.set_table_data("noctus_users", [{"id": USER_ID, "nome": "Rapha", "email": "r@x.io"}])
    cfg = make_cfg(actor_resolver(lambda: core))
    if cfg_transform is not None:
        cfg = cfg_transform(cfg)
    db = MockSupabaseClient(validate_schema=True, schema=schema)
    storage = FakeStorageBackend()

    def get_db():
        return db

    def get_storage():
        return storage

    collection, entity = card_hub_routers(
        cfg,
        auth_dependency=_auth_dependency,
        resolve_context=_resolve_context,
        get_db=get_db,
        get_storage=get_storage,
        prefix=prefix,
        documento_upload_hook=upload_hook,
    )
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(collection)
    app.include_router(entity)
    return Hub(
        name=name, cfg=cfg, schema=schema, prefix=prefix, db=db, core=core, storage=storage, app=app,
        client=TestClient(app), anon=TestClient(app),
    )


@pytest.fixture
def lead_schema_cache():
    """Extend the mock's migration-derived schema map with the NEUTRAL
    config's template output (via the mock's own `set_cache_for_tests` seam),
    restoring the untouched derived map afterwards (restored, not reset: a
    reset would re-parse every product's migrations on the next test)."""
    base = {table: set(cols) for table, cols in _schema_cache.get_schema_map().items()}
    cfg = lead_config(lambda ids: {})
    generated = parse_sql(_LEAD_PREREQS + card_hub_migration(cfg, "crm"), source_label="card_hub_migration(lead)")
    _schema_cache.set_cache_for_tests({**base, **generated})
    yield
    _schema_cache.set_cache_for_tests(base)


@pytest.fixture(params=["lead", "sw"])
def hub(request, lead_schema_cache) -> Hub:
    return build_hub(request.param)
