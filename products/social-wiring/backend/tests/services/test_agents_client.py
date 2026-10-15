"""`AgentsClient` (contract 3.1 / 3.2 client side): the real client against the exact
request/response shapes and EVERY row of the 3.1 error table; the Fake; the factory.

`HttpAgentsClient` is driven through an `httpx.MockTransport` -- the HTTP seam is the
EXTERNAL boundary, so nothing of ours is patched.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from app.clients.agents import (
    AgentNotFound,
    AgentsBadRequest,
    AgentsClient,
    AgentsTimeout,
    AgentsTokenInvalid,
    AgentsUpstreamError,
    AgentUnavailable,
    CapacityExceeded,
    DeletionRequest,
    FakeAgentsClient,
    HttpAgentsClient,
    IdempotencyConflict,
    LlmNotConfigured,
    TurnInProgress,
    TurnMessage,
    TurnRequest,
    TurnResult,
    make_agents_client,
)

CONN = "00000000-0000-4000-8000-0000000000e3"
AT = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def _req(*ids: str) -> TurnRequest:
    return TurnRequest(
        agent_key="lead-imob", connection_id=CONN, chat_id="5511999990000@c.us",
        phone_e164="+5511999990000", display_name="Ana",
        messages=tuple(TurnMessage(texto=f"oi {i}", provider_message_id=i, at=AT) for i in (ids or ("m1",))),
    )


def _ok_body(**over):
    base = {
        "conversation_id": "11111111-1111-4111-8111-111111111111",
        "reply": {"partes": ["Oi!", "Comprar ou alugar?"]},
        "actions": [],
        "status": "respondido",
        "usage": {"custo_usd": 0.01, "tokens_entrada": 10, "tokens_saida": 5},
    }
    base.update(over)
    return base


def _client(handler) -> HttpAgentsClient:
    return HttpAgentsClient("https://agents.example.test", "pk_secret_token", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
class TestWireShapes:
    async def test_run_turn_sends_exactly_the_3_1_request_and_parses_the_response(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"], seen["path"] = request.method, request.url.path
            seen["auth"] = request.headers["authorization"]
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=_ok_body(
                actions=[{"type": "handoff", "motivo": "pediu humano"}], status="handoff"))

        result = await _client(handler).run_turn(_req("m1", "m2"))
        assert (seen["method"], seen["path"]) == ("POST", "/api/channels/turns")
        assert seen["auth"] == "Bearer pk_secret_token"
        assert seen["body"] == {
            "agent_key": "lead-imob",
            "channel": "whatsapp",
            "channel_ref": {"connection_id": CONN, "chat_id": "5511999990000@c.us"},
            "contact": {"phone_e164": "+5511999990000", "display_name": "Ana"},
            "messages": [
                {"texto": "oi m1", "provider_message_id": "m1", "at": AT.isoformat()},
                {"texto": "oi m2", "provider_message_id": "m2", "at": AT.isoformat()},
            ],
        }
        assert result.partes == ("Oi!", "Comprar ou alugar?")
        assert result.status == "handoff" and result.handoff.motivo == "pediu humano"
        assert result.conversation_id == "11111111-1111-4111-8111-111111111111"
        assert (result.custo_usd, result.tokens_entrada, result.tokens_saida) == (0.01, 10, 5)

    async def test_agent_status_hits_the_3_2_route(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert (request.method, request.url.path) == ("GET", "/api/channels/agents/lead-imob/status")
            return httpx.Response(200, json={
                "agent_key": "lead-imob", "nome": "Julia", "ativo": True, "versao_ativa": 3,
                "provider": "openai", "model": "gpt-5-mini", "llm_configurado": True,
            })

        st = await _client(handler).agent_status("lead-imob")
        assert (st.nome, st.ativo, st.versao_ativa, st.provider, st.model, st.llm_configurado) == (
            "Julia", True, 3, "openai", "gpt-5-mini", True)

    async def test_empty_partes_means_stay_silent(self):
        client = _client(lambda r: httpx.Response(200, json=_ok_body(reply={"partes": []}, status="silencio")))
        result = await client.run_turn(_req())
        assert result.partes == () and result.status == "silencio"

    @pytest.mark.parametrize("body", [
        {"conversation_id": "x"},                                           # no reply
        _ok_body(status="whatever"),                                        # unknown status
        _ok_body(reply={"partes": [1, 2]}),                                 # non-string bubbles
        _ok_body(reply="oi"),                                               # reply not an object
    ])
    async def test_a_malformed_200_is_an_upstream_fault_never_half_trusted(self, body):
        with pytest.raises(AgentsUpstreamError):
            await _client(lambda r: httpx.Response(200, json=body)).run_turn(_req())

    async def test_non_json_200_is_an_upstream_fault(self):
        with pytest.raises(AgentsUpstreamError):
            await _client(lambda r: httpx.Response(200, content=b"<html>")).run_turn(_req())

    async def test_an_unknown_action_type_is_kept_as_a_lais_action_never_a_handoff(self):
        # Lais contract 2.1(d): unknown != dropped -- the apply service answers it with an
        # `acao_sem_handler` event. It must never be mistaken for the page-0 handoff.
        client = _client(lambda r: httpx.Response(200, json=_ok_body(actions=[{"type": "salvar_slot", "x": 1}])))
        result = await client.run_turn(_req())
        assert result.handoff is None
        assert [(a.type, a.payload) for a in result.lais_actions] == [("salvar_slot", {"x": 1})]

    async def test_motivo_is_capped_at_280(self):
        client = _client(lambda r: httpx.Response(200, json=_ok_body(
            actions=[{"type": "handoff", "motivo": "x" * 900}], status="handoff")))
        assert len((await client.run_turn(_req())).handoff.motivo) == 280


def _err(status: int, code: str | None = None, headers: dict | None = None):
    body = {"detail": {"detail": "msg", "code": code}} if code else {"detail": "msg"}
    return lambda request: httpx.Response(status, json=body, headers=headers or {})


@pytest.mark.asyncio
class TestErrorTable:
    """One test per row of the contract 3.1 error table."""

    @pytest.mark.parametrize("status,code", [
        (401, None), (403, "product_required"), (403, "scope_missing"), (403, "issuer_not_allowed"),
    ])
    async def test_401_403_is_token_invalid(self, status, code):
        with pytest.raises(AgentsTokenInvalid) as ei:
            await _client(_err(status, code)).run_turn(_req())
        assert ei.value.code == code

    async def test_404_agent_not_found(self):
        with pytest.raises(AgentNotFound):
            await _client(_err(404, "agent_not_found")).run_turn(_req())

    async def test_other_404_is_an_upstream_fault(self):
        with pytest.raises(AgentsUpstreamError):
            await _client(_err(404)).run_turn(_req())

    @pytest.mark.parametrize("code", ["agent_inactive", "no_active_version", "prompt_too_large"])
    async def test_409_agent_unavailable(self, code):
        with pytest.raises(AgentUnavailable) as ei:
            await _client(_err(409, code)).run_turn(_req())
        assert ei.value.code == code

    async def test_409_turn_in_progress(self):
        with pytest.raises(TurnInProgress):
            await _client(_err(409, "turn_in_progress")).run_turn(_req())

    async def test_409_idempotency_conflict(self):
        with pytest.raises(IdempotencyConflict):
            await _client(_err(409, "idempotency_conflict")).run_turn(_req())

    async def test_422_invalid_field_is_a_bug(self):
        with pytest.raises(AgentsBadRequest):
            await _client(_err(422, "invalid_field")).run_turn(_req())

    async def test_424_llm_not_configured(self):
        with pytest.raises(LlmNotConfigured):
            await _client(_err(424, "llm_not_configured")).run_turn(_req())

    async def test_429_capacidade_honours_retry_after(self):
        with pytest.raises(CapacityExceeded) as ei:
            await _client(_err(429, "capacidade", {"Retry-After": "17"})).run_turn(_req())
        assert ei.value.retry_after == 17

    async def test_429_without_retry_after_uses_a_default(self):
        with pytest.raises(CapacityExceeded) as ei:
            await _client(_err(429, "capacidade")).run_turn(_req())
        assert ei.value.retry_after == 30

    @pytest.mark.parametrize("status", [500, 502, 503])
    async def test_5xx_is_an_upstream_fault(self, status):
        with pytest.raises(AgentsUpstreamError):
            await _client(_err(status, "llm_upstream")).run_turn(_req())

    async def test_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        with pytest.raises(AgentsTimeout):
            await _client(handler).run_turn(_req())

    async def test_connection_refused_is_unavailable_like_a_timeout(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        with pytest.raises(AgentsTimeout):
            await _client(handler).run_turn(_req())

    async def test_the_status_route_maps_the_same_errors(self):
        with pytest.raises(AgentsTokenInvalid):
            await _client(_err(401)).agent_status("lead-imob")
        with pytest.raises(AgentNotFound):
            await _client(_err(404, "agent_not_found")).agent_status("nope")

    async def test_the_token_never_appears_in_an_error(self):
        with pytest.raises(AgentsTokenInvalid) as ei:
            await _client(_err(401)).run_turn(_req())
        assert "pk_secret_token" not in str(ei.value)


@pytest.mark.asyncio
class TestDeletion:
    async def test_sends_the_shipped_delete_shape_and_a_204_is_success(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"], seen["path"], seen["body"] = request.method, request.url.path, json.loads(request.content)
            return httpx.Response(204)

        res = await _client(handler).delete_conversation_data(
            DeletionRequest(agent_key="lead-imob", connection_id=CONN, chat_id="5511999990000@c.us"))
        assert (seen["method"], seen["path"]) == ("DELETE", "/api/channels/conversations")
        assert seen["body"] == {
            "agent_key": "lead-imob", "channel": "whatsapp",
            "channel_ref": {"connection_id": CONN, "chat_id": "5511999990000@c.us"},
        }
        assert res.deleted is True

    async def test_409_turn_in_progress_is_raised_so_the_caller_can_retry(self):
        with pytest.raises(TurnInProgress):
            await _client(_err(409, "turn_in_progress")).delete_conversation_data(
                DeletionRequest(agent_key="lead-imob", connection_id=CONN, chat_id="x@c.us"))

    async def test_other_errors_propagate(self):
        with pytest.raises(AgentsTokenInvalid):
            await _client(_err(401)).delete_conversation_data(
                DeletionRequest(agent_key="lead-imob", connection_id=CONN, chat_id="x@c.us"))

    async def test_403_agent_not_allowed_is_a_token_problem(self):
        with pytest.raises(AgentsTokenInvalid) as ei:
            await _client(_err(403, "agent_not_allowed")).run_turn(_req())
        assert ei.value.code == "agent_not_allowed"

    async def test_flat_error_bodies_are_read(self):
        def handler(request):
            return httpx.Response(409, json={"detail": "dup", "code": "idempotency_conflict"})

        with pytest.raises(IdempotencyConflict):
            await _client(handler).run_turn(_req())


@pytest.mark.asyncio
class TestFake:
    async def test_satisfies_the_protocol(self):
        assert isinstance(FakeAgentsClient(), AgentsClient)
        assert isinstance(_client(lambda r: httpx.Response(200)), AgentsClient)

    async def test_default_reply_and_call_recording(self):
        fake = FakeAgentsClient()
        res = await fake.run_turn(_req("a"))
        assert res.status == "respondido" and res.partes
        assert fake.turns[0].messages[0].provider_message_id == "a"

    async def test_script_is_consumed_in_order_and_errors_are_raised(self):
        fake = FakeAgentsClient([
            TurnResult(conversation_id="c", partes=("um",), status="respondido"),
            TurnInProgress(code="turn_in_progress"),
        ])
        assert (await fake.run_turn(_req("a"))).partes == ("um",)
        with pytest.raises(TurnInProgress):
            await fake.run_turn(_req("b"))

    async def test_replaying_the_same_ids_returns_the_stored_reply_without_a_new_turn(self):
        fake = FakeAgentsClient([TurnResult(conversation_id="c", partes=("um",), status="respondido")])
        first = await fake.run_turn(_req("a"))
        again = await fake.run_turn(_req("a"))
        assert again is first

    async def test_status_and_deletion_are_recorded(self):
        fake = FakeAgentsClient()
        await fake.run_turn(_req("a"))
        assert (await fake.agent_status("lead-imob")).nome == "Julia"
        res = await fake.delete_conversation_data(DeletionRequest("lead-imob", CONN, "5511999990000@c.us"))
        assert res.deleted is True and fake.deletions


class TestFactory:
    def test_client_needs_url_and_token(self):
        with pytest.raises(ValueError):
            HttpAgentsClient("", "tok")
        with pytest.raises(ValueError):
            HttpAgentsClient("https://x", "")

    def test_token_and_url_give_the_real_client(self):
        assert isinstance(make_agents_client(token="t", base_url="https://a", allow_fake=False), HttpAgentsClient)

    def test_missing_token_in_prod_is_none_never_a_fake(self):
        assert make_agents_client(token=None, base_url="https://a", allow_fake=False) is None

    def test_missing_url_in_prod_is_none(self):
        assert make_agents_client(token="t", base_url=None, allow_fake=False) is None

    def test_missing_config_in_dev_is_the_fake(self):
        assert isinstance(make_agents_client(token=None, base_url=None, allow_fake=True), FakeAgentsClient)
