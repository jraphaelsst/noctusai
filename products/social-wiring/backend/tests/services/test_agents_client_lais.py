"""`AgentsClient` Lais extension (lais-build-contract 2.1 a/d/e/f, client side): the `contexto`
in the turn request, the action shapes of the response, `/resumo`, and the tools-token push.

`HttpAgentsClient` is driven through an `httpx.MockTransport` (the HTTP seam is the external
boundary; nothing of ours is patched)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from app.clients.agents import (
    AgentsTokenInvalid,
    AgentsUpstreamError,
    ConversationNotFound,
    FakeAgentsClient,
    HandoffAction,
    HttpAgentsClient,
    LaisAction,
    ResumoRequest,
    ResumoResult,
    TurnMessage,
    TurnRequest,
    TurnResult,
)

AT = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
CONV = "11111111-1111-4111-8111-111111111111"


def _client(handler) -> HttpAgentsClient:
    return HttpAgentsClient("https://agents.example.test", "pk_channel_token", transport=httpx.MockTransport(handler))


def _req(contexto=None) -> TurnRequest:
    return TurnRequest(
        agent_key="lead-imob", connection_id="c1", chat_id="5511900000000@c.us", contexto=contexto,
        messages=(TurnMessage(texto="oi", provider_message_id="m1", at=AT),),
    )


def _body(**over):
    base = {"conversation_id": CONV, "reply": {"partes": ["Oi!"]}, "actions": [], "status": "respondido", "usage": {}}
    base.update(over)
    return base


@pytest.mark.asyncio
class TestTurn:
    async def test_contexto_rides_in_the_request_only_when_set(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json=_body())

        await _client(handler).run_turn(_req())
        await _client(handler).run_turn(_req({"hash": "a" * 64}))
        assert "contexto" not in seen[0]
        assert seen[1]["contexto"] == {"hash": "a" * 64}

    async def test_lais_actions_are_parsed_with_seq_and_payload_and_handoff_stays_a_handoff(self):
        actions = [
            {"type": "salvar_slots", "seq": 2, "slots": {"bairro": "Granja"}},
            {"type": "handoff", "motivo": "quer humano"},
            {"type": "encerrar", "seq": 1, "motivo": "sem_interesse"},
        ]
        result = await _client(lambda r: httpx.Response(200, json=_body(actions=actions, status="encerrado"))).run_turn(_req())
        assert result.status == "encerrado"
        assert isinstance(result.handoff, HandoffAction) and result.handoff.motivo == "quer humano"
        # ordered by seq, payload = the object minus type/seq
        assert [(a.type, a.seq, a.payload) for a in result.lais_actions] == [
            ("encerrar", 1, {"motivo": "sem_interesse"}),
            ("salvar_slots", 2, {"slots": {"bairro": "Granja"}}),
        ]

    async def test_a_malformed_action_is_skipped_with_the_rest_kept(self):
        result = await _client(lambda r: httpx.Response(200, json=_body(
            actions=["oops", {"seq": 1}, {"type": "encerrar", "seq": 1, "motivo": "outro"}]))).run_turn(_req())
        assert [a.type for a in result.lais_actions] == ["encerrar"]

    async def test_a_missing_seq_falls_back_to_arrival_order(self):
        result = await _client(lambda r: httpx.Response(200, json=_body(
            actions=[{"type": "salvar_slots", "slots": {}}, {"type": "encerrar", "motivo": "outro"}]))).run_turn(_req())
        assert [(a.type, a.seq) for a in result.lais_actions] == [("salvar_slots", 0), ("encerrar", 1)]


@pytest.mark.asyncio
class TestResumo:
    async def test_posts_to_the_conversation_route_and_parses_the_2_1_e_body(self):
        seen = {}

        def handler(request):
            seen.update(method=request.method, path=request.url.path, body=json.loads(request.content),
                        auth=request.headers["authorization"])
            return httpx.Response(200, json={
                "resumo": "Procura casa de 3 quartos.", "slots": {"bairro": "Granja"}, "operacao": "compra",
                "intencoes": ["visita", "encerrar"], "desfecho": "qualificado",
                "usage": {"custo_usd": 0.02, "tokens_entrada": 100, "tokens_saida": 20},
            })

        res = await _client(handler).resumo(CONV, ResumoRequest(perguntas=({"chave": "bairro"},), desde=AT))
        assert (seen["method"], seen["path"], seen["auth"]) == ("POST", f"/api/channels/conversations/{CONV}/resumo", "Bearer pk_channel_token")
        assert seen["body"] == {"perguntas": [{"chave": "bairro"}], "desde": AT.isoformat()}
        assert res == ResumoResult(
            resumo="Procura casa de 3 quartos.", slots={"bairro": "Granja"}, operacao="compra",
            intencoes=("visita", "encerrar"), desfecho="qualificado", custo_usd=0.02, tokens_entrada=100, tokens_saida=20,
        )

    async def test_desde_null_is_sent_as_null(self):
        seen = {}

        def handler(request):
            seen.update(json.loads(request.content))
            return httpx.Response(200, json={"resumo": "", "slots": {}, "intencoes": [], "desfecho": "frio"})

        await _client(handler).resumo(CONV, ResumoRequest())
        assert seen == {"perguntas": [], "desde": None}

    async def test_404_conversation_not_found_is_typed(self):
        h = lambda r: httpx.Response(404, json={"detail": {"detail": "x", "code": "conversation_not_found"}})  # noqa: E731
        with pytest.raises(ConversationNotFound):
            await _client(h).resumo(CONV, ResumoRequest())

    async def test_a_malformed_200_is_an_upstream_fault(self):
        with pytest.raises(AgentsUpstreamError):
            await _client(lambda r: httpx.Response(200, json={"resumo": "x"})).resumo(CONV, ResumoRequest())


@pytest.mark.asyncio
class TestFerramentasToken:
    async def test_put_sends_the_token_in_the_body_with_the_channel_bearer(self):
        seen = {}

        def handler(request):
            seen.update(method=request.method, path=request.url.path, body=json.loads(request.content),
                        auth=request.headers["authorization"])
            return httpx.Response(204)

        await _client(handler).put_ferramentas_token("pk_tools_secret")
        assert seen == {"method": "PUT", "path": "/api/channels/ferramentas-token",
                        "body": {"token": "pk_tools_secret"}, "auth": "Bearer pk_channel_token"}

    async def test_a_refusal_is_typed(self):
        with pytest.raises(AgentsTokenInvalid):
            await _client(lambda r: httpx.Response(401, json={"detail": "no"})).put_ferramentas_token("pk_x")

    async def test_an_empty_token_is_refused_before_any_call(self):
        called = []
        with pytest.raises(ValueError):
            await _client(lambda r: called.append(r) or httpx.Response(204)).put_ferramentas_token("")
        assert called == []


@pytest.mark.asyncio
class TestFake:
    async def test_records_resumos_and_tokens_and_follows_the_scripts(self):
        fake = FakeAgentsClient(resumo_script=[ResumoResult(resumo="r1", desfecho="frio")])
        assert (await fake.resumo(CONV, ResumoRequest())).resumo == "r1"
        assert (await fake.resumo(CONV, ResumoRequest())).resumo  # default after the script
        assert [c for c, _ in fake.resumos] == [CONV, CONV]
        await fake.put_ferramentas_token("pk_t")
        assert fake.ferramentas_tokens == ["pk_t"]

    async def test_errors_are_scriptable(self):
        fake = FakeAgentsClient(resumo_script=[ConversationNotFound(code="conversation_not_found")],
                                ferramentas_token_error=AgentsTokenInvalid())
        with pytest.raises(ConversationNotFound):
            await fake.resumo(CONV, ResumoRequest())
        with pytest.raises(AgentsTokenInvalid):
            await fake.put_ferramentas_token("pk_t")

    async def test_turn_actions_helper_orders_by_seq(self):
        r = TurnResult(conversation_id=CONV, partes=(), status="respondido",
                       actions=(LaisAction("b", 2), HandoffAction("m"), LaisAction("a", 1)))
        assert [a.type for a in r.lais_actions] == ["a", "b"]
