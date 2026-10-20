"""julia-v2: every `contexto` SW can render validates against agents' request schema; a 422 from agents is LOUD.

The W0 422 root cause: `contexto.estado` carried keys (`atendente_nome`, `reengajamento`, `reescrever`, `texto_base`, ...) that
agents' `ContextoEstado` (`extra="forbid"`) rejected, so every turn for a contato with a responsavel and EVERY re-engagement
turn got a 422 that SW logged as a "client bug" and answered nothing. agents closed that in v2 (the keys are fields now, A-RT)
and SW sends them as DATA instead of stripping them.

The oracle is `tests/support/agents_channel_contexto.py` (a copy of agents' `ChannelContexto`); the drift gate below compares it
with agents' published `channels.v2.json`.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.clients.agents import AgentsBadRequest, FakeAgentsClient
from app.services import julia_contatos_service as contatos
from app.services import julia_contexto_service as ctxsvc
from app.services import julia_envio_gate
from app.services import julia_equipes_service  # noqa: F401  (registers the atendente_nome provider)
from app.services import julia_notificacoes_service as notif
from app.services import julia_reengajamento_service as reeng
from app.services.julia_lead_turn_service import process_lead_batch, run_reengajamento_turn
from tests.support.agents_channel_contexto import ChannelContexto
from tests.support.julia_world import CONNECTION_ID, LEAD_CHAT, ORG_ID, OWNER_ID, World, buffer_lead

SCHEMA_PATH = Path(os.environ.get("AGENTS_CONTRACT_SCHEMA") or Path(__file__).resolve().parents[5] / "products" / "agents" / "backend" / "contracts" / "channels.v2.json")


def _sem_descricao(node):
    """Docstrings and titles are prose, not contract: compare the schema without `description` / `title`."""
    if isinstance(node, dict):
        return {k: _sem_descricao(v) for k, v in node.items() if k not in ("description", "title")}
    if isinstance(node, list):
        return [_sem_descricao(v) for v in node]
    return node


def test_the_test_mirror_matches_the_published_agents_schema():
    """Drift gate: the copy under tests/support is the oracle for every other test here, so it must equal agents' file."""
    assert SCHEMA_PATH.exists(), f"{SCHEMA_PATH} is missing"
    published = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["ChannelTurnRequest"]["$defs"]
    mirror = ChannelContexto.model_json_schema()
    mirror_defs = {**mirror.get("$defs", {}), "ChannelContexto": {k: v for k, v in mirror.items() if k != "$defs"}}
    for nome in ("ChannelContexto", "ContextoEstado", "ContextoOrigem", "ContextoCredito", "ContextoCapacidades", "ContextoPergunta"):
        assert _sem_descricao(mirror_defs[nome]) == _sem_descricao(published[nome]), (
            f"agents' {nome} changed: update tests/support/agents_channel_contexto.py AND the SW contexto builder")
    assert set(ctxsvc.ESTADO_CHAVES_AGENTS) <= set(published["ContextoEstado"]["properties"])


def _validar(contexto: dict) -> None:
    # the mock DB mints `mock-julia_interacoes-1` ids; production ids are UUIDs (the only thing normalised here)
    estado = {**contexto["estado"], "interacao_id": str(uuid4())}
    ChannelContexto.model_validate({**contexto, "estado": estado})


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    w.seed_chat()
    return w


def _contato(w: World, **over) -> dict:
    c = contatos.obter_ou_criar_contato(w.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT)
    c, _ = contatos.registrar_inbound(w.sw, c)
    if over:
        contatos.atualizar_contato(w.sw, c["id"], over)
    return w.contato()


def _montar(w: World, c: dict, **kw) -> dict:
    """Like production: a turn always renders against an OPEN interacao (`interacao_id` is a required UUID)."""
    kw.setdefault("ferramentas_habilitadas", False)
    return ctxsvc.montar(w.sw, ORG_ID, c, interacao=contatos.abrir_interacao(w.sw, ORG_ID, c), **kw)


class TestContextoValidaContraAgents:
    def test_base_contexto_validates(self, world):
        _validar(_montar(world, _contato(world), ferramentas_habilitadas=True))

    def test_contato_with_a_responsavel_sends_the_attendant_name_as_data(self, world):
        c = _contato(world, responsavel_user_id=OWNER_ID)
        world.core.set_table_data("noctus_users", [{"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner", "nome": "Marcos"}])
        with patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=world.root):  # the DB seam, not our code
            contexto = _montar(world, c)
        assert contexto["estado"]["atendente_nome"] == "Marcos"
        _validar(contexto)

    @pytest.mark.parametrize("estado_extra", [
        {"reengajamento": "minutos"},
        {"reengajamento": "horas"},
        {"reengajamento": "regua", "reescrever": True, "texto_base": "Oi, tudo bem?", "tentativa": 2, "regua_id": "r-1"},
    ])
    def test_every_reengagement_estado_validates_and_is_sent(self, world, estado_extra):
        contexto = _montar(world, _contato(world), estado_extra=estado_extra)
        _validar(contexto)
        enviado = {k: v for k, v in estado_extra.items() if k != "regua_id"}  # the regua id goes to the gate, never to agents
        assert {k: contexto["estado"][k] for k in enviado} == enviado and "regua_id" not in contexto["estado"]

    def test_an_unknown_estado_key_is_stripped_and_logged_at_error(self, world, caplog):
        with caplog.at_level(logging.ERROR):
            contexto = _montar(world, _contato(world), estado_extra={"chave_nova": 1})
        _validar(contexto)
        assert "chave_nova" in caplog.text

    def test_credito_state_is_kept_and_validates(self, world):
        c = _contato(world)
        contexto = _montar(world, c,
                          providers=[("estado", lambda ctx: {"estado": {"interacao_id": str(uuid4()), "encerrado": False,
                                                                          "credito": {"ativo": True, "consentimento": None}}})])
        assert contexto["estado"]["credito"] == {"ativo": True, "consentimento": None}
        _validar(contexto)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tier", ["minutos", "horas", "regua"])
    async def test_the_real_reengagement_turn_sends_a_valid_contexto(self, world, tier):
        c = _contato(world)
        extra = {"reengajamento": tier}
        if tier == "regua":
            extra |= {"reescrever": True, "texto_base": "Oi?", "tentativa": 1, "regua_id": "r-1"}
        connection = world.record(CONNECTION_ID)
        try:
            await run_reengajamento_turn(world.deps(), connection, LEAD_CHAT, c, extra, "reeng:test")
        except julia_envio_gate.EnvioBloqueado:
            pass
        assert world.agents.turns, "the turn must reach agents"
        _validar(world.agents.turns[-1].contexto)


@pytest.mark.asyncio
class TestA422IsLoud:
    async def test_a_422_logs_error_and_emits_an_owner_visible_event_and_notification(self, world, caplog):
        world.agents = FakeAgentsClient([AgentsBadRequest("agents rejected the request shape", code="invalid_field")])
        notif.registrar()
        notif.registrar_core_provider(lambda: world.core)
        try:
            k = buffer_lead(world, LEAD_CHAT, ["Oi"])
            with caplog.at_level(logging.ERROR):
                await process_lead_batch(k, world.buffer.memory_for(k), deps=world.deps())
        finally:
            notif.registrar_core_provider(None)
        assert world.sent_texts() == []  # the lead got nothing...
        eventos = world.rows("julia_eventos", tipo="agents_contrato_invalido")
        assert len(eventos) == 1 and eventos[0]["payload"]["codigo"] == "invalid_field"  # ...but the failure is on record
        assert [n["user_id"] for n in world.notifications()] == [OWNER_ID]  # owners only
        assert "client bug" in caplog.text and "NO reply" in caplog.text

    async def test_a_second_422_the_same_day_is_a_second_event_but_not_a_second_notification(self, world):
        notif.registrar()
        notif.registrar_core_provider(lambda: world.core)
        try:
            for i in range(2):
                world.agents = FakeAgentsClient([AgentsBadRequest("x", code="invalid_field")])
                k = buffer_lead(world, LEAD_CHAT, ["Oi"], ids=[f"m{i}"])
                await process_lead_batch(k, world.buffer.memory_for(k), deps=world.deps())
        finally:
            notif.registrar_core_provider(None)
        assert len(world.rows("julia_eventos", tipo="agents_contrato_invalido")) == 2
        assert len(world.notifications()) == 1
