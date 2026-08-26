"""Fixtures for the pipeline (Funil / Processos) module tests.

Backed by `MockSupabaseClient` and wired through the same schema-scoped
`.schema()` seam the Leads module uses — `deps.get_pipeline_client()` caches
the bound instance, so the fixture must hand back the SAME object across
requests or every write vanishes between POST and GET.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import (
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

ORG_A = "00000000-0000-4000-8000-0000000000a1"
ORG_B = "00000000-0000-4000-8000-0000000000b2"

# Stage rows as migration 034 seeds them. Cards reference these by ID.
FUNIL_STAGES = [
    {"id": f"fstage-{i}", "org_id": ORG_A, "pipeline": "funil", "slug": slug,
     "label": label, "cor": "secondary", "posicao": i, "papel": papel, "ativo": True}
    for i, (slug, label, papel) in enumerate([
        ("novo", "Novo", None),
        ("contato", "Contato", None),
        ("qualificado", "Qualificado", None),
        ("proposta", "Proposta", "proposta_aceite"),
        # The STAGE keeps its name — after migration 060 it is the only
        # negociação in the system, which is the point of the rename.
        ("negociacao", "Negociação", None),
        ("fechado", "Fechado", "final"),
    ])
]
PROC_STAGES = [
    {"id": f"pstage-{i}", "org_id": ORG_A, "pipeline": "processos_venda", "slug": slug,
     "label": label, "cor": "secondary", "posicao": i,
     "papel": "final" if slug == "faturamento" else None, "ativo": True}
    for i, (slug, label) in enumerate([
        ("contrato", "Contrato"), ("onboarding", "Onboarding"), ("briefing", "Briefing"),
        ("planejamento", "Planejamento"), ("execucao", "Execução"),
        ("entrega", "Entrega"), ("faturamento", "Faturamento"),
    ])
]
# Another tenant's stage — proves org scoping is real, not assumed.
OTHER_ORG_STAGE = {
    "id": "fstage-other", "org_id": ORG_B, "pipeline": "funil", "slug": "novo",
    "label": "Novo (outra org)", "cor": "secondary", "posicao": 0,
    "papel": None, "ativo": True,
}

STAGE_ID = {s["slug"]: s["id"] for s in FUNIL_STAGES}
PROC_STAGE_ID = {s["slug"]: s["id"] for s in PROC_STAGES}


def atendimento(nid="neg-1", etapa="novo", status="aberta", **over):
    row = {
        "id": nid,
        "org_id": ORG_A,
        "lead_id": f"lead-{nid}",
        # Every real atendimento has one — the stage gate reads it to ask
        # whether we know who this is (`pipeline.stage_gate`).
        "cliente_id": f"cli-{nid}",
        "meta_ads_lead_id": None,
        "etapa_id": STAGE_ID[etapa],
        "status": status,
        "titulo": "Lead Teste",
        "valor_estimado": 1000,
        "kanban_pos": 0,
        "arquivado": False,
        "closed_at": None,
        "lead": {"id": f"lead-{nid}", "cliente_nome": "Lead Teste", "contato": "11999998888"},
        "campanha": None,
        "etapa_rel": next(s for s in FUNIL_STAGES if s["id"] == STAGE_ID[etapa]),
    }
    row.update(over)
    return row


def processo(pid="proc-1", etapa="contrato", **over):
    row = {
        "id": pid,
        "org_id": ORG_A,
        "atendimento_id": "neg-1",
        "etapa_id": PROC_STAGE_ID[etapa],
        "valor": 1000,
        "observacoes": None,
        "kanban_pos": 0,
        "arquivado": False,
        "atendimento": {"id": "neg-1", "titulo": "Lead Teste"},
        "etapa_rel": next(s for s in PROC_STAGES if s["id"] == PROC_STAGE_ID[etapa]),
    }
    row.update(over)
    return row


@pytest.fixture
def mock_db():
    return MockSupabaseClient()


@pytest.fixture
def http_client(mock_db):
    mock_db.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=ORG_A))
    )

    # `.schema()` must return the SAME instance every call — `deps` caches it,
    # and a fresh wrapper per call has an empty row cache (see deps.py).
    scoped = mock_db.schema("social_wiring")
    mock_db.schema = lambda _name: scoped

    scoped.set_table_data("pipeline_stages", FUNIL_STAGES + PROC_STAGES + [OTHER_ORG_STAGE])
    scoped.set_table_data("pipeline_movimentos", [])
    scoped.set_table_data("atendimentos", [])
    scoped.set_table_data("processos_venda", [])

    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_db),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_db),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_db),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_db)
        tc = TestClient(app, raise_server_exceptions=True)
        tc.scoped = scoped
        yield tc


def seed_titular(scoped, nid="neg-1", *, apto=True, **over):
    """Seed the cliente behind an atendimento, ready (or not) to move stages.

    `apto=True` gives them a real full name and a phone, which is exactly what
    `pipeline.stage_gate.CAMPOS_OBRIGATORIOS` requires — so a test about
    MOVING a card is not accidentally a test about the gate.

    `apto=False` seeds the same person with neither, which is what an
    untouched Meta/OLX lead actually looks like: a push name and nothing else.

    The two empty sibling tables are not optional. `documento_checklist_service
    .listar` reads them on every call, and a MockSupabaseClient table that was
    never `set_table_data` is absent rather than empty.
    """
    row = {
        "id": f"cli-{nid}",
        "org_id": ORG_A,
        "nome": "Luciano" if apto else "Ana",
        "nome_completo": "Luciano Mauricio" if apto else None,
        "nome_oficial": None,
        "celular": "+5511999998888" if apto else None,
        "chave_canonica": None,
        "chave_tipo": None,
        "email": None,
        "data_nascimento": None,
        "profissao": None,
        "genero": None,
    }
    row.update(over)
    scoped.set_table_data("clientes", [row])
    scoped.set_table_data("cliente_documentos", [])
    scoped.set_table_data("cliente_documento_checklist", [])
    return row


def auth_headers() -> dict:
    return {"Authorization": "Bearer test-token"}


__all__ = [
    "ORG_A", "ORG_B", "FUNIL_STAGES", "PROC_STAGES", "OTHER_ORG_STAGE",
    "STAGE_ID", "PROC_STAGE_ID", "atendimento", "processo", "auth_headers",
    "seed_titular",
]
