"""Fixtures for maya-blocks S2: the org's real default stages (migration 060 slugs), the 286 tables, and a few
builders. Mock DB of `tests.support.julia_world` -- nothing of ours is patched."""
from __future__ import annotations

from typing import Any

import pytest

from tests.support.julia_world import ORG_ID, OTHER_ORG_ID, World

FUNIL = ["qualificacao", "visitas", "proposta_recebida", "negociacao", "proposta_decisao"]
PROCESSOS = [
    "elaboracao_contrato", "analise_partes", "revisao_contrato", "assinatura",
    "financiamento_escritura", "finalizacao", "entrega_chaves", "nota_fiscal",
]


def _stages(org: str) -> list[dict[str, Any]]:
    rows = []
    for pipeline, slugs in (("funil", FUNIL), ("processos_venda", PROCESSOS)):
        for i, slug in enumerate(slugs):
            rows.append({
                "id": f"{org[-4:]}-{pipeline}-{slug}", "org_id": org, "pipeline": pipeline, "slug": slug,
                "label": slug.replace("_", " ").title(), "cor": "secondary", "posicao": i, "ativo": True,
                "papel": "proposta_aceite" if slug == "proposta_decisao" else ("final" if slug == "nota_fiscal" else None),
            })
    return rows


def stage_id(slug: str, pipeline: str = "funil", org: str = ORG_ID) -> str:
    if slug in PROCESSOS and pipeline == "funil":
        pipeline = "processos_venda"
    return f"{org[-4:]}-{pipeline}-{slug}"


@pytest.fixture
def world() -> World:
    w = World()
    w.sw.set_table_data("pipeline_stages", _stages(ORG_ID) + _stages(OTHER_ORG_ID))
    for t in ("atendimento_blocos", "supervisao_config", "atendimento_handoffs", "pipeline_movimentos", "atendimentos",
              "processos_venda", "julia_atribuicoes", "julia_envio_entregas", "cliente_notas", "julia_eventos"):
        w.sw.set_table_data(t, [])
    return w


def supervisao_on(world: World, org: str = ORG_ID, horas: int = 24) -> None:
    world.sw.set_table_data("supervisao_config", [
        {"org_id": org, "supervisao_ativa": True, "horas_para_assumir": horas},
    ])


def atendimento(world: World, nid: str = "a1", etapa: str = "qualificacao", *, lead_id: str = "lead-1",
                org: str = ORG_ID, **over: Any) -> dict[str, Any]:
    row = {"id": nid, "org_id": org, "lead_id": lead_id, "cliente_id": f"cli-{nid}", "etapa_id": stage_id(etapa, org=org),
           "status": "aberta", "titulo": "Lead", "valor_estimado": 1000, "kanban_pos": 0, "arquivado": False,
           "substituida_por": None, **over}
    world.sw.table("atendimentos").insert(row).execute()
    return row


def processo(world: World, pid: str = "p1", etapa: str = "elaboracao_contrato", *, atendimento_id: str = "a1",
             org: str = ORG_ID) -> dict[str, Any]:
    row = {"id": pid, "org_id": org, "atendimento_id": atendimento_id, "etapa_id": stage_id(etapa, "processos_venda", org),
           "valor": 1000, "kanban_pos": 0, "arquivado": False}
    world.sw.table("processos_venda").insert(row).execute()
    return row


def movimento(world: World, mid: str, card: str, de: str | None, para: str, *, pipeline: str = "funil",
              created_at: str = "2026-10-19T12:00:00+00:00", org: str = ORG_ID) -> dict[str, Any]:
    row = {"id": mid, "org_id": org, "pipeline": pipeline, "entidade_id": card,
           "de_etapa_id": stage_id(de, pipeline, org) if de else None, "para_etapa_id": stage_id(para, pipeline, org),
           "responsavel_id": "00000000-0000-4000-8000-0000000000e2", "motivo": None, "created_at": created_at}
    world.sw.table("pipeline_movimentos").insert(row).execute()
    return row


def handoffs(world: World) -> list[dict[str, Any]]:
    return world.sw.table("atendimento_handoffs").select("*").execute().data or []
