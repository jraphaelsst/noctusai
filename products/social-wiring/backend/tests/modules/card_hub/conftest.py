"""Shared fixtures + row builders for `card_hub` module tests.

Rows are seeded directly against the `social_wiring`-scoped mock
(`get_card_hub_client()`) — mirrors `tests/routers/test_clientes_router.py`'s
shape exactly, but keyed off THIS module's own DI seam
(`app.modules.card_hub.deps.get_card_hub_client`), which is a SEPARATE
weakref cache from `clientes_router.get_clientes_client` (see that
dependency's docstring: two independent `.schema()` calls on the same
underlying mock produce two independent per-table data stores). Seeding
through the wrong one would silently seed data this module's routes can
never see.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import coerce_org_uuid
from app.modules.card_hub.deps import get_card_hub_client, get_storage_backend
from noctusai_lib.integrations.storage import FakeStorageBackend
from tests.conftest import (  # type: ignore[attr-defined]
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

ORG_RAW = "test-org-123"
ORG_ID = str(coerce_org_uuid(ORG_RAW))


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def anon_client():
    """A TestClient sending NO Authorization header — see
    `test_clientes_router.py`'s identical fixture for why the shared
    `client` fixture can never produce a 401."""
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_RAW)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        tc = TestClient(app)
        yield tc
        app.dependency_overrides.clear()


@pytest.fixture
def scoped(client):
    """The `social_wiring`-scoped mock `card_hub`'s own DI seam resolves
    and caches — seeding through THIS instance is what makes rows
    visible to a subsequent request in the same test."""
    return get_card_hub_client()


@pytest.fixture
def fake_storage(client):
    """Installs a `FakeStorageBackend` via the DI seam — never relies on
    `MockSupabaseClient.storage` (a bare `MagicMock()` that would
    silently "succeed" with garbage signed URLs instead of failing
    loudly). Per `KB § PATTERNS/backend/di-test-seam.md` Class-B."""
    from app.main import app

    backend = FakeStorageBackend()
    prev = app.dependency_overrides.get(get_storage_backend)
    app.dependency_overrides[get_storage_backend] = lambda: backend
    yield backend
    if prev is None:
        app.dependency_overrides.pop(get_storage_backend, None)
    else:
        app.dependency_overrides[get_storage_backend] = prev


# ─── row builders ────────────────────────────────────────────────────────


def cliente_row(
    id_=None,
    nome="Ana",
    *,
    ativo=True,
    arquivado_em=None,
    created_at="2026-01-01T00:00:00+00:00",
    ultimo_contato_em="2026-01-01T00:00:00+00:00",
    **extra,
) -> dict:
    row = {
        "id": id_ or str(uuid4()),
        "org_id": ORG_ID,
        "nome": nome,
        "chave_canonica": None,
        "chave_tipo": None,
        "identidade_incerta": False,
        "ativo": ativo,
        "inativo_em": None,
        "arquivado_em": arquivado_em,
        "primeiro_contato_em": created_at,
        "ultimo_contato_em": ultimo_contato_em,
        "created_at": created_at,
        "updated_at": None,
        "data_inicio": None,
        "data_entrega": None,
        "entrega_concluida": False,
        "lembrete_minutos_antes": None,
        "recorrencia": None,
    }
    row.update(extra)
    return row


def nota_row(id_, cliente_id, *, corpo="uma nota", tipo="comentario", autor_id=None, editado_em=None, deleted_at=None, created_at="2026-01-05T00:00:00+00:00") -> dict:
    return {
        "id": id_,
        "org_id": ORG_ID,
        "cliente_id": cliente_id,
        "autor_id": autor_id,
        "tipo": tipo,
        "corpo": corpo,
        "editado_em": editado_em,
        "deleted_at": deleted_at,
        "created_at": created_at,
    }


def tag_row(id_, *, nome="Quente", cor="#ff0000") -> dict:
    return {"id": id_, "org_id": ORG_ID, "nome": nome, "cor": cor, "created_at": "2026-01-01T00:00:00+00:00"}


def corretor_row(id_, *, nome="Bia", cor="#00ff00", ativo=True) -> dict:
    return {
        "id": id_,
        "org_id": ORG_ID,
        "nome": nome,
        "nome_norm": nome.lower(),
        "cor": cor,
        "ativo": ativo,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": None,
    }


def touch_row(id_, cliente_id, *, origem_id, ocorreu_em, origem_tabela="leads", nome=None) -> dict:
    return {
        "id": id_,
        "cliente_id": cliente_id,
        "org_id": ORG_ID,
        "origem_tabela": origem_tabela,
        "origem_id": origem_id,
        "ocorreu_em": ocorreu_em,
        "nome": nome,
        "chave_canonica": None,
        "origem_label": None,
        "created_at": ocorreu_em,
    }


def checklist_row(id_, cliente_id, *, titulo="Checklist", posicao=0, origem="ad_hoc", etapa_id=None) -> dict:
    return {
        "id": id_,
        "org_id": ORG_ID,
        "cliente_id": cliente_id,
        "titulo": titulo,
        "posicao": posicao,
        "origem": origem,
        "etapa_id": etapa_id,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def checklist_item_row(id_, checklist_id, *, texto="item", concluido=False, concluido_em=None, concluido_por=None, posicao=0) -> dict:
    return {
        "id": id_,
        "org_id": ORG_ID,
        "checklist_id": checklist_id,
        "texto": texto,
        "concluido": concluido,
        "concluido_em": concluido_em,
        "concluido_por": concluido_por,
        "posicao": posicao,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def documento_tipo_row(tipo="contrato", *, categoria="contratual", retencao_dias=1825, ativo=True, identidade=False) -> dict:
    return {
        "tipo_documento": tipo,
        "categoria_lgpd": categoria,
        "retencao_dias": retencao_dias,
        "identidade": identidade,
        "ativo": ativo,
        "descricao": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def retencao_politica_row(tipo_documento="contrato", *, superficie="cliente", dias=1825, org_id=None) -> dict:
    """A `documento_retencao_politicas` row (migration 079).

    🔴 Seed this alongside `documento_tipo_row` whenever a test asserts on
    `retencao_ate`. Since 079 the upload path reads the retention from the
    POLICY table, not from `cliente_documento_tipos.retencao_dias` — a test
    that seeds only the catalogue gets a null clock and fails at its own
    fixture rather than at a defect.
    """
    from uuid import uuid4 as _uuid4

    return {
        "id": str(_uuid4()),
        "org_id": org_id,
        "superficie": superficie,
        "tipo_documento": tipo_documento,
        "retencao_dias": dias,
        "motivo": None,
        "atualizado_em": None,
        "atualizado_por": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def documento_row(id_, cliente_id, *, tipo_documento="contrato", categoria_lgpd="contratual", storage_path=None, deleted_at=None, retencao_ate=None, enviado_por=None, created_at="2026-01-01T00:00:00+00:00") -> dict:
    return {
        "id": id_,
        "org_id": ORG_ID,
        "cliente_id": cliente_id,
        "storage_path": storage_path or f"{ORG_ID}/clientes/{cliente_id}/{id_}",
        "nome_original": "arquivo.pdf",
        "mime_type": "application/pdf",
        "tamanho_bytes": 1024,
        "tipo_documento": tipo_documento,
        "categoria_lgpd": categoria_lgpd,
        "retencao_ate": retencao_ate,
        "enviado_por": enviado_por,
        "deleted_at": deleted_at,
        "delete_motivo": None,
        "delete_solicitado_por": None,
        "created_at": created_at,
    }


__all__ = [
    "ORG_ID",
    "ORG_RAW",
    "checklist_item_row",
    "checklist_row",
    "cliente_row",
    "corretor_row",
    "documento_row",
    "documento_tipo_row",
    "nota_row",
    "tag_row",
    "touch_row",
]
