"""LGPD delete-by-lead + retention across the qualification tables, what an org admin may read of a lead thread
(no blocks / token usage / version stamps; realtime stripped too), the scopes, and the generated contract."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import jsonschema
import pytest
from noctusai_lib.integrations.llm import ChatToolsResponse, FakeProvider, LLMUsage

from app.channels.retention import purge_expired
from app.dependencies import MINTABLE_TOKEN_SCOPES
from app.qualificacao.models import EventoImovel
from app.qualificacao.service import ItemPerfil
from app.schemas import channels_contract
from tests.channels.conftest import CONNECTION_ID, contexto_body, turn_body
from tests.channels.test_julia_v2_e2e import call, say, step


def _qualificar(chan, ref: str, texto: str = "Quero comprar um apartamento"):
    """A lead with a thread, records, a property event, an identity and a violation row."""
    chan.use_provider(FakeProvider(tool_responses=[
        step(call("registrar_perfil", itens=[{"criterio": "operacao", "valor": "compra", "trecho": "Quero comprar"}])),
        say("Qual o bairro?")]))
    r = chan.turn(turn_body(texto, ids=[f"id-{ref}"], lead_ref=ref, chat_id=f"chat-{ref}")).json()
    lead = chan.threads.get_lead_ref_by_externa(chan.org_id, ref)
    chan.leads.adicionar_evento(chan.org_id, lead.id, agent_id=chan.agent.id, thread_id=None,
                                evento=EventoImovel("B1", "oferecido", "similar", 1))
    chan.ident._store.salvar_campos(chan.org_id, lead.id, {"nome": "Maria"}, agent_id=None, origem_msg_id=None)
    return r, lead


class TestDeleteByLeadCascadesToTheQualification:
    def test_the_lead_goes_with_its_threads_records_events_state_identity_and_ledger(self, chan):
        chan.seed_agent()
        r, lead = _qualificar(chan, "contato-1")
        keep, keep_lead = _qualificar(chan, "contato-2")
        assert chan.leads.listar_registros(chan.org_id, lead.id) and chan.ident.coletados(chan.org_id, lead.id)
        with chan.as_token("agents:channel-turn"):
            resp = chan.request("DELETE", "/api/channels/leads/contato-1")
        assert resp.status_code == 204
        assert chan.threads.get_lead_ref_by_externa(chan.org_id, "contato-1") is None
        assert chan.rt.stores.messages.list(chan.org_id, UUID(r["thread_id"]), limite=50) == []
        assert chan.leads.listar_registros(chan.org_id, lead.id) == []
        assert chan.leads.listar_eventos(chan.org_id, lead.id) == []
        assert chan.leads.obter_estado(chan.org_id, lead.id) is None
        assert chan.ident.coletados(chan.org_id, lead.id) == frozenset()
        assert chan.inbound.find(chan.org_id, CONNECTION_ID, ["id-contato-1"]) == {}
        # another lead of the org is untouched
        assert chan.leads.listar_registros(chan.org_id, keep_lead.id)
        assert chan.rt.stores.messages.list(chan.org_id, UUID(keep["thread_id"]), limite=50)

    def test_it_is_idempotent_and_a_running_turn_blocks_it(self, chan):
        chan.seed_agent()
        r, _ = _qualificar(chan, "contato-1")
        chan.rt.stores.conversations.try_acquire_turn(chan.org_id, UUID(r["thread_id"]), "outro", 60)
        with chan.as_token("agents:channel-turn"):
            assert chan.request("DELETE", "/api/channels/leads/contato-1").status_code == 409
        chan.rt.stores.conversations.release_turn(chan.org_id, UUID(r["thread_id"]), "outro")
        with chan.as_token("agents:channel-turn"):
            assert chan.request("DELETE", "/api/channels/leads/contato-1").status_code == 204
            assert chan.request("DELETE", "/api/channels/leads/contato-1").status_code == 204


class TestRetentionPurgeCascadesToo:
    def test_a_thread_idle_past_the_retention_takes_the_lead_and_its_qualification_with_it(self, chan):
        chan.seed_agent()
        r, lead = _qualificar(chan, "contato-1")
        chan.rt.stores.conversations._rows[UUID(r["thread_id"])]["last_message_at"] = (
            datetime.now(timezone.utc) - timedelta(days=181))
        assert purge_expired(chan.retention, retention_days=180) == 1
        assert chan.threads.get_lead_ref_by_externa(chan.org_id, "contato-1") is None
        assert chan.leads.listar_registros(chan.org_id, lead.id) == []
        assert chan.ident.coletados(chan.org_id, lead.id) == frozenset()

    def test_qualification_that_outlived_every_thread_is_purged_whole(self, chan):
        chan.seed_agent()
        ref = chan.threads.upsert_lead_ref(chan.org_id, "orfao")
        chan.qual.registrar_perfil(
            chan.org_id, ref.id, agent_id=chan.agent.id, versao_id=chan.padrao_versao_id, fonte="humano",
            mensagens_lead=[], itens=[ItemPerfil("operacao", "compra")])
        assert purge_expired(chan.retention, retention_days=180, now=datetime.now(timezone.utc) + timedelta(days=200)) == 0
        assert chan.leads.listar_registros(chan.org_id, ref.id) == []


class TestWhatAnOrgAdminReadsOfALeadThread:
    def _thread_with_a_tool_turn(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("avaliar_lead")),
            ChatToolsResponse(text="Qual o bairro?", usage=LLMUsage(100, 20, 0, 0, 0.004))]))
        return chan.turn(turn_body("Oi", contexto=contexto_body())).json()["thread_id"]

    def test_the_conversation_messages_route_strips_blocks_usage_and_version_stamps(self, chan):
        thread = self._thread_with_a_tool_turn(chan)
        items = chan.client.get(f"/api/conversations/{thread}/messages").json()["items"]
        assert [m["role"] for m in items] == ["user", "assistant"]
        for m in items:
            assert m["blocks"] == [] and m["token_usage"] is None
            assert m["version_id"] is None and m["compiled_hash"] is None
            assert m["custo_usd"] is None and m["tokens_entrada"] is None and m["tokens_saida"] is None
        # ...although the platform keeps them (they feed the cost caps and the per-agent context)
        [assistente] = [r for r in chan.rt.stores.messages.list(chan.org_id, UUID(thread), limite=20) if r.role == "assistant"]
        assert assistente.blocks and assistente.compiled_hash and assistente.custo_usd == pytest.approx(0.005)

    def test_a_silent_turn_cost_row_and_a_system_notice_are_not_conversation(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[
            ChatToolsResponse(text="", usage=LLMUsage(10, 5, 0, 0, 0.002))]))
        thread = chan.turn().json()["thread_id"]
        chan.rt.stores.messages.add(chan.org_id, UUID(thread), "system", "O turno falhou.")
        items = chan.client.get(f"/api/conversations/{thread}/messages").json()["items"]
        assert [m["role"] for m in items] == ["user"]

    def test_a_user_conversation_keeps_its_full_shape(self, rt):
        agent, version = rt.make_agent("isa")
        conv = rt.stores.conversations.create(rt.org_id, agent.id, rt.user_id, version_id=version.id)
        rt.stores.messages.add(rt.org_id, conv.id, "assistant", "oi", version_id=version.id, compiled_hash="sha256:x")
        item = rt.get(f"/api/conversations/{conv.id}/messages").json()["items"][0]
        assert item["compiled_hash"] == "sha256:x" and item["version_id"] == str(version.id)

    def test_the_realtime_stream_of_a_lead_thread_carries_no_internals(self, chan):
        thread = self._thread_with_a_tool_turn(chan)
        events = chan.events(thread)
        assert not [e for e in events if e.event in ("tool.started", "tool.finished", "message.updated")]
        for e in events:
            if e.event == "message.new":
                assert set(e.payload) == {"id", "conversation_id", "role", "texto", "created_at"}
            if e.event == "session.status":
                assert set(e.payload) <= {"status"}


class TestScopes:
    def test_content_write_is_not_mintable_by_an_org_admin(self):
        assert "studio:content-write" not in MINTABLE_TOKEN_SCOPES

    def test_the_channel_scopes_are_the_only_ones_the_channel_routes_demand(self, chan):
        chan.seed_agent()
        with chan.as_token("agents:channel-status"):
            assert chan.request("POST", "/api/channels/turns", json=turn_body()).status_code == 403
        with chan.as_token("agents:channel-turn"):
            assert chan.request("GET", "/api/channels/agents/julia/status").status_code == 403


class TestTheGeneratedContract:
    def test_the_file_is_what_the_models_generate(self):
        assert channels_contract.CONTRACT_PATH.read_text(encoding="utf-8") == channels_contract.render(), (
            "channels.v2.json drifted from the pydantic models; run "
            "`python -m app.schemas.channels_contract --write` and commit the result"
        )

    def test_a_request_the_models_accept_validates_against_the_file_and_an_unknown_key_does_not(self):
        schema = json.loads(Path(channels_contract.CONTRACT_PATH).read_text(encoding="utf-8"))
        req = schema["ChannelTurnRequest"]
        body = turn_body("Oi", contexto=contexto_body(
            atendente_nome="Bia", reengajamento="horas", reescrever=True, texto_base="x", tentativa=2,
            origem={"canal_origem": "meta_ads", "codigo_imovel_campanha": "AP1"},
            credito={"ativo": True, "consentimento": None}))
        jsonschema.validate(body, req)
        for bad in ({**body, "surprise": 1}, {**body, "gatilho": "outro"},
                    {**body, "contexto": {**body["contexto"], "estado": {**body["contexto"]["estado"], "x": 1}}}):
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(bad, req)

    def test_the_closed_estado_names_what_sw_used_to_strip(self):
        props = json.loads(Path(channels_contract.CONTRACT_PATH).read_text(encoding="utf-8"))["ContextoEstado"]["properties"]
        assert {"atendente_nome", "reengajamento", "reescrever", "texto_base", "tentativa", "origem"} <= set(props)

    def test_a_real_response_validates_against_the_file(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[say("Qual o bairro?")]))
        resp = chan.turn(turn_body(contexto=contexto_body())).json()
        schema = json.loads(Path(channels_contract.CONTRACT_PATH).read_text(encoding="utf-8"))["ChannelTurnResponse"]
        jsonschema.validate(resp, schema)

    def test_every_status_the_route_can_answer_is_in_the_contract(self):
        statuses = set(json.loads(Path(channels_contract.CONTRACT_PATH).read_text(encoding="utf-8"))
                       ["ChannelTurnResponse"]["properties"]["status"]["enum"])
        assert {"respondido", "silencio", "handoff", "encerrado", "concluido", "agente_desligado", "novo_lead_recusado",
                "conversa_pausada", "conversa_com_outro_responsavel", "conversa_com_outro_agente",
                "reengajamento_ignorado", "lead_opt_out", "limite_atingido", "limite_taxa", "novo_lead_limitado",
                "loop_detectado"} == statuses
