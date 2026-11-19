"""``POST /api/channels/turns`` on channel ``app``: the Diretor de Criacao's in-product chat (slice S8b).

Declared capability (never a blanket channel), brand = ``connection_id`` bound server-side, org owns the brand (tenant
isolation, fail closed), idempotent on the user message, no Julia machinery. Julia's ``whatsapp`` path is pinned by its own
suites; the cross-checks here only prove the two channels do not reach each other's agents. Strict statuses: a bad
credential is exactly 401."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

import pytest
from noctusai_lib.integrations.llm import FakeProvider

from app.studio.catalog import StoreKnowledgeCatalog
from tests.channels.conftest import turn_body
from tests.channels.diretor_mundo import DIRETOR_KEY, MARCA, OUTRA_MARCA, montar_diretor
from tests.channels.test_julia_v2_e2e import call, say, step, tool_results
from tests.routers.conftest import DEFAULT_USER_ID


def app_body(*texts: str, chat_id: str = "conversa-1", marca: UUID = MARCA, ids: list[str] | None = None,
             agent_key: str = DIRETOR_KEY, **extra) -> dict:
    texts = texts or ("Quero roteiros sobre sono",)
    ids = ids or [f"msg-{abs(hash((chat_id, t))) % 10**8}" for t in texts]
    return {
        "agent_key": agent_key, "channel": "app", "channel_ref": {"connection_id": str(marca), "chat_id": chat_id},
        "messages": [
            {"texto": t, "provider_message_id": i, "at": datetime(2026, 11, 19, 12, 0, n, tzinfo=timezone.utc).isoformat()}
            for n, (t, i) in enumerate(zip(texts, ids, strict=True))
        ],
        **extra,
    }


def _contexto_marca(args: dict) -> dict:
    """SW's answer: the brand of THIS org echoes its id; anything else is what the client folds a 404 into."""
    if args.get("marca_id") == str(MARCA):
        return {"marca_id": str(MARCA), "perfil": {"bio": "b"}, "memorias": []}
    return {"erro": "indisponivel"}


@pytest.fixture
def diretor(chan):
    chan.agent = montar_diretor(
        chan.rt.studio, StoreKnowledgeCatalog(chan.rt.knowledge), chan.org_id, DEFAULT_USER_ID, chan.controles)
    chan.sw.criacao_token_orgs.add(chan.org_id)
    chan.sw.criacao_responses["contexto_marca"] = _contexto_marca
    chan.use_provider(FakeProvider(tool_responses=[say("### Publicação 1\n- Legenda: oi")]))
    return chan


def _conversas(chan):
    return list(chan.rt.stores.conversations._rows.values())


class TestAuth:
    def test_no_credential_is_401(self, diretor):
        assert diretor.request("POST", "/api/channels/turns", json=app_body()).status_code == 401

    def test_a_human_session_is_403_product_required(self, diretor):
        resp = diretor.client.post("/api/channels/turns", json=app_body())
        assert resp.status_code == 403 and resp.json()["code"] == "product_required"

    def test_a_token_bound_to_another_agent_is_403_agent_not_allowed(self, diretor):
        resp = diretor.turn(app_body(), principal=UUID(int=0xDEAD))
        assert resp.status_code == 403 and resp.json()["code"] == "agent_not_allowed"


class TestCapacidadeDeclarada:
    def test_an_agent_that_does_not_declare_the_app_channel_is_refused(self, chan):
        chan.seed_agent()  # Julia
        resp = chan.turn(app_body(agent_key="julia"))
        assert resp.status_code == 403 and resp.json()["code"] == "canal_nao_permitido"
        assert chan.provider.calls == []

    def test_the_declaring_agent_is_not_reachable_through_the_lead_pipeline(self, diretor):
        resp = diretor.turn(turn_body(agent_key=DIRETOR_KEY))  # channel whatsapp
        assert resp.status_code == 403 and resp.json()["code"] == "canal_nao_permitido"
        assert diretor.provider.calls == []

    @pytest.mark.parametrize("extra", [
        {"lead": {"ref": "contato-1"}}, {"gatilho": "reengajamento"}, {"remetente": "dono"},
    ])
    def test_the_lead_machinery_is_rejected_on_the_app_channel(self, diretor, extra):
        resp = diretor.turn(app_body(**extra))
        assert resp.status_code == 422

    def test_deletion_on_request_stays_whatsapp_only(self, diretor):
        body = {k: app_body()[k] for k in ("agent_key", "channel", "channel_ref")}
        with diretor.as_token():
            assert diretor.request("DELETE", "/api/channels/conversations", json=body).status_code == 422


class TestTurno:
    def test_a_turn_answers_stores_both_messages_and_binds_the_brand(self, diretor):
        diretor.use_provider(FakeProvider(tool_responses=[step(call("cerebros")), say("### Publicação 1\n- Legenda: oi")]))
        resp = diretor.turn(app_body("Quero roteiros sobre sono"))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "respondido" and "### Publicação 1" in "\n".join(body["reply"]["partes"])
        # the brand rides every tool call, never the model's arguments; every call is the TOKEN's org
        tools = {n: a for _o, n, a in diretor.sw.criacao_calls}
        assert tools["cerebros"] == {"marca_id": str(MARCA)}
        assert all(o == diretor.org_id for o, _n, _a in diretor.sw.criacao_calls)
        # the conversation is a plain app row: no lead, none of the thread machinery
        (conv,) = _conversas(diretor)
        assert (conv["channel"], conv["tipo"], conv["lead_ref_id"]) == ("app", "chat", None)
        assert conv["channel_ref"] == {"connection_id": str(MARCA), "chat_id": "conversa-1"}
        papeis = [m.role for m in diretor.rt.stores.messages.list(diretor.org_id, conv["id"])]
        assert papeis == ["user", "assistant"]

    def test_no_tool_schema_the_model_sees_names_the_brand(self, diretor):
        diretor.use_provider(FakeProvider(tool_responses=[say("ok")]))
        assert diretor.turn(app_body()).status_code == 200
        ofertadas = [t for c in diretor.provider.calls for t in (c.get("tools") or [])]
        assert ofertadas, "the Diretor's tools must be offered"
        assert "marca_id" not in json.dumps([getattr(t, "parameters", t) for t in ofertadas])

    def test_a_model_supplied_brand_is_refused_not_obeyed(self, diretor):
        diretor.use_provider(FakeProvider(tool_responses=[
            step(call("cerebros", marca_id=str(OUTRA_MARCA))), say("ok")]))
        assert diretor.turn(app_body()).status_code == 200
        assert [r for r in tool_results(diretor.provider) if r.get("codigo") == "argumentos_invalidos"]
        assert [a for _o, n, a in diretor.sw.criacao_calls if n == "cerebros"] == []

    def test_the_same_message_replays_the_stored_reply_without_a_second_model_run(self, diretor):
        body = app_body("Quero roteiros", ids=["m-1"])
        first = diretor.turn(body)
        again = diretor.turn(body)
        assert first.status_code == again.status_code == 200 and first.json() == again.json()
        assert len(diretor.provider.calls) == 1

    def test_the_same_id_with_other_text_is_409_idempotency_conflict(self, diretor):
        assert diretor.turn(app_body("um", ids=["m-1"])).status_code == 200
        resp = diretor.turn(app_body("outro", ids=["m-1"]))
        assert resp.status_code == 409 and resp.json()["code"] == "idempotency_conflict"

    def test_a_second_turn_of_the_conversation_sees_the_first_and_does_not_re_verify_the_brand(self, diretor):
        diretor.use_provider(FakeProvider(tool_responses=[say("primeira"), say("segunda")]))
        assert diretor.turn(app_body("pergunta 1", ids=["m-1"])).status_code == 200
        assert diretor.turn(app_body("pergunta 2", ids=["m-2"])).status_code == 200
        historico = [m.content for m in diretor.provider.calls[-1]["messages"]]
        assert any("pergunta 1" in (c or "") for c in historico) and any("primeira" in (c or "") for c in historico)
        assert len([1 for _o, n, _a in diretor.sw.criacao_calls if n == "contexto_marca"]) == 1
        assert len(_conversas(diretor)) == 1

    def test_a_switched_off_agent_answers_without_running_the_model(self, diretor):
        diretor.controles.set(diretor.org_id, diretor.agent.id, modo="desligado")
        resp = diretor.turn(app_body())
        assert resp.status_code == 200 and resp.json()["status"] == "agente_desligado"
        assert resp.json()["reply"]["partes"] == [] and diretor.provider.calls == []
        assert _conversas(diretor) == []


class TestIsolamentoDeTenant:
    def test_a_brand_the_org_does_not_own_is_404_with_zero_trace(self, diretor):
        resp = diretor.turn(app_body(marca=OUTRA_MARCA))
        assert resp.status_code == 404 and resp.json()["code"] == "marca_nao_encontrada"
        assert diretor.provider.calls == [] and _conversas(diretor) == []
        assert diretor.inbound.find(diretor.org_id, OUTRA_MARCA, ["x"]) == {}

    def test_an_unreachable_sw_is_not_verified_so_it_fails_closed(self, diretor):
        diretor.sw.criacao_fail = True
        resp = diretor.turn(app_body())
        assert resp.status_code == 404 and resp.json()["code"] == "marca_nao_encontrada"
        assert diretor.provider.calls == [] and _conversas(diretor) == []

    def test_sw_answering_for_another_brand_is_not_a_proof(self, diretor):
        diretor.sw.criacao_responses["contexto_marca"] = lambda _a: {"marca_id": str(OUTRA_MARCA)}
        assert diretor.turn(app_body()).status_code == 404

    def test_an_org_without_the_criacao_token_is_424_not_a_silent_run(self, diretor):
        diretor.sw.criacao_token_orgs.clear()
        resp = diretor.turn(app_body())
        assert resp.status_code == 424 and resp.json()["code"] == "criacao_nao_configurada"
        assert diretor.provider.calls == [] and _conversas(diretor) == []

    def test_the_conversation_of_one_org_is_invisible_to_another(self, diretor):
        assert diretor.turn(app_body(ids=["m-1"])).status_code == 200
        outra = UUID(int=424242)
        assert diretor.rt.stores.conversations.find_channel(
            outra, diretor.agent.id, "app", {"connection_id": str(MARCA), "chat_id": "conversa-1"}) is None
