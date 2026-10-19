"""Gate 0 of `julia_envio_gate` (maya-blocks): a send for a block OTHER than `sdr` needs that block `ativo` with an
`agent_key`; `sdr` (the default) skips it -- Julia stays governed by gate 1 exactly as before.
Seams: the mock DB of `tests.support.julia_world`; nothing of ours is patched."""
from __future__ import annotations

import pytest

from app.services import julia_envio_gate as gate

from tests.support.julia_world import CONNECTION_ID, ORG_ID, World

Fluxo = gate.Fluxo


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    for t in (gate.T_REENGAJAMENTO_CONFIG, gate.T_REGUAS, gate.T_MODELOS, gate.T_AVALIACOES_CONFIG,
              "atendimento_blocos", "julia_eventos"):
        w.sw.set_table_data(t, [])
    return w


def _bloco(world: World, bloco: str, *, ativo: bool, agent_key: str | None) -> None:
    world.sw.table("atendimento_blocos").insert({
        "org_id": ORG_ID, "bloco": bloco, "agent_key": agent_key, "ativo": ativo,
        "pipeline": None if bloco == "sdr" else "funil", "etapas": []}).execute()


def _eventos(world: World) -> list[dict]:
    return [e for e in world.sw.table("julia_eventos").select("*").execute().data or [] if e["tipo"] == "envio_bloqueado"]


def test_sdr_is_untouched_by_gate_0_even_with_no_block_row(world):
    lib = gate.exigir(world.sw, ORG_ID, CONNECTION_ID, Fluxo.RESPOSTA)
    assert lib.bloco == "sdr"
    assert gate.exigir(world.sw, ORG_ID, CONNECTION_ID, Fluxo.RESPOSTA, bloco="sdr").bloco == "sdr"


def test_sdr_block_switched_off_still_does_not_stop_julia(world):
    _bloco(world, "sdr", ativo=False, agent_key=None)  # `ativo` = Maya supervises, never "Julia may talk"
    gate.exigir(world.sw, ORG_ID, CONNECTION_ID, Fluxo.RESPOSTA)


@pytest.mark.parametrize("setup,motivo", [
    (None, "bloco_inativo"),                                   # absent row = default = off
    ({"ativo": False, "agent_key": None}, "bloco_inativo"),
    ({"ativo": True, "agent_key": None}, "bloco_sem_agente"),  # humans run it -- no automatic send
])
def test_a_non_sdr_block_needs_ativo_and_an_agent(world, setup, motivo):
    if setup is not None:
        _bloco(world, "atendimento", **setup)
    with pytest.raises(gate.EnvioBloqueado) as exc:
        gate.exigir(world.sw, ORG_ID, CONNECTION_ID, Fluxo.RESPOSTA, contato_id=None, bloco="atendimento")
    assert exc.value.motivo == motivo
    (ev,) = _eventos(world)
    assert ev["payload"] == {"fluxo": "resposta", "motivo": motivo, "connection_id": CONNECTION_ID, "bloco": "atendimento"}


def test_an_unknown_block_is_refused(world):
    with pytest.raises(gate.EnvioBloqueado) as exc:
        gate.exigir(world.sw, ORG_ID, CONNECTION_ID, Fluxo.RESPOSTA, bloco="marketing")
    assert exc.value.motivo == "bloco_desconhecido"


def test_gate_0_passing_falls_through_to_gates_1_and_2(world):
    _bloco(world, "atendimento", ativo=True, agent_key="corretor-bot")
    assert gate.exigir(world.sw, ORG_ID, CONNECTION_ID, Fluxo.RESPOSTA, bloco="atendimento").bloco == "atendimento"
    with pytest.raises(gate.EnvioBloqueado) as exc:  # gate 2 still applies
        gate.exigir(world.sw, ORG_ID, CONNECTION_ID, Fluxo.REENGAJAMENTO_HORAS, bloco="atendimento")
    assert exc.value.motivo == "reengajamento_desativado"
    world.sw.table("whatsapp_connections").update({"agente_leads_ativo": False}).eq("id", CONNECTION_ID).execute()
    with pytest.raises(gate.EnvioBloqueado) as exc:  # and gate 1
        gate.exigir(world.sw, ORG_ID, CONNECTION_ID, Fluxo.RESPOSTA, bloco="atendimento")
    assert exc.value.motivo == "julia_desligada"


def test_a_block_liberacao_is_still_sealed():
    with pytest.raises(TypeError):
        gate.Liberacao(org_id=ORG_ID, connection_id=CONNECTION_ID, fluxo=Fluxo.RESPOSTA, bloco="atendimento")
