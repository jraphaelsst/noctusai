"""maya-blocks T2 wired into the boards: `mover-etapa` (funil + processos) and `aceitar-proposta` call the
block-boundary hook after the move (CONTRACT §2.2). The org saves its own block map here, because this suite's
stages are the generic 034 ones, not the 060 real-estate defaults."""
from __future__ import annotations

from .conftest import ORG_A, PROC_STAGE_ID, STAGE_ID, atendimento, auth_headers, processo, seed_titular


def _blocos(scoped, *, supervisao: bool = True) -> None:
    scoped.set_table_data("supervisao_config", [{"org_id": ORG_A, "supervisao_ativa": supervisao, "horas_para_assumir": 24}])
    scoped.set_table_data("atendimento_handoffs", [])
    scoped.set_table_data("atendimento_blocos", [
        {"org_id": ORG_A, "bloco": "atendimento", "agent_key": None, "ativo": True, "pipeline": "funil",
         "etapas": ["novo", "contato", "qualificado", "proposta"]},
        {"org_id": ORG_A, "bloco": "negociacao", "agent_key": None, "ativo": True, "pipeline": "funil",
         "etapas": ["negociacao", "fechado"]},
        {"org_id": ORG_A, "bloco": "juridico", "agent_key": None, "ativo": True, "pipeline": "processos_venda",
         "etapas": ["contrato", "onboarding"]},
        {"org_id": ORG_A, "bloco": "financeiro", "agent_key": None, "ativo": True, "pipeline": "processos_venda",
         "etapas": ["briefing"]},
    ])


def _handoffs(scoped):
    return scoped.table("atendimento_handoffs").select("*").execute().data or []


def _mover(http_client, path, para):
    return http_client.post(path, json={"para_etapa_id": para}, headers=auth_headers())


def test_funil_move_across_a_boundary_records_a_handoff(http_client):
    s = http_client.scoped
    _blocos(s)
    s.set_table_data("atendimentos", [atendimento("neg-1", "proposta")])
    seed_titular(s)
    assert _mover(http_client, "/api/atendimentos-venda/neg-1/mover-etapa", STAGE_ID["negociacao"]).status_code == 200
    (h,) = _handoffs(s)
    assert (h["de_bloco"], h["para_bloco"], h["gatilho"], h["atendimento_id"]) == ("atendimento", "negociacao", "movimento_etapa", "neg-1")


def test_a_move_inside_a_block_and_supervision_off_record_nothing(http_client):
    s = http_client.scoped
    _blocos(s)
    s.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
    seed_titular(s)
    assert _mover(http_client, "/api/atendimentos-venda/neg-1/mover-etapa", STAGE_ID["contato"]).status_code == 200
    assert _handoffs(s) == []
    _blocos(s, supervisao=False)
    assert _mover(http_client, "/api/atendimentos-venda/neg-1/mover-etapa", STAGE_ID["negociacao"]).status_code == 200
    assert _handoffs(s) == []


def test_processos_move_across_a_boundary_records_a_handoff(http_client):
    s = http_client.scoped
    _blocos(s)
    s.set_table_data("atendimentos", [atendimento("neg-1", "proposta")])
    s.set_table_data("processos_venda", [processo("proc-1", "onboarding")])
    assert _mover(http_client, "/api/processos-venda/proc-1/mover-etapa", PROC_STAGE_ID["briefing"]).status_code == 200
    (h,) = _handoffs(s)
    assert (h["de_bloco"], h["para_bloco"], h["atendimento_id"]) == ("juridico", "financeiro", "neg-1")


def test_accept_route_writes_the_entry_movement_with_the_acting_user_and_the_handoff(http_client):
    s = http_client.scoped
    _blocos(s)
    s.set_table_data("atendimentos", [atendimento("neg-1", "proposta")])
    assert http_client.post("/api/atendimentos-venda/neg-1/aceitar-proposta", headers=auth_headers()).status_code == 200
    (mov,) = s.table("pipeline_movimentos").inserted_payloads
    # the session's user (the mock resolves TEST_USER_ID to a uuid) -- never None: responsavel_id is NOT NULL
    assert mov["responsavel_id"] and mov["responsavel_id"] != "None" and mov["de_etapa_id"] is None
    assert mov["para_etapa_id"] == PROC_STAGE_ID["contrato"] and mov["pipeline"] == "processos_venda"
    (h,) = _handoffs(s)
    assert (h["de_bloco"], h["para_bloco"]) == ("atendimento", "juridico")  # the accept stage `proposta` is atendimento's here
