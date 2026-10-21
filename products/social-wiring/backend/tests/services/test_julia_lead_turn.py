"""The Julia lead worker (`julia_lead_turn_service.process_lead_batch`).

Covers: contract 3.1's whole error table on the SW side, 11.3 (disclosure bubble first,
only on the first turn), 11.4 (handoff target + notification), 10.1 L3 (post-turn
re-check) / M4 (limits, batch cap) / H3 re-check / M5 (no inbound message deletes anything), and the B2 run
semantics (an inbound that lands during a turn is NOT swallowed).

Every external seam is a Fake: mock DB, `FakeWahaClient`, `FakeRealtimeBus`, fakeredis,
the in-memory buffer, `FakeAgentsClient`.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.clients.agents import (
    AgentNotFound,
    AgentsBadRequest,
    AgentsTimeout,
    AgentsTokenInvalid,
    AgentsUpstreamError,
    AgentUnavailable,
    CapacityExceeded,
    FakeAgentsClient,
    HandoffAction,
    IdempotencyConflict,
    LlmNotConfigured,
    TurnInProgress,
    TurnResult,
)
from app.services import julia_agente_service as julia
from app.services.julia_lead_turn_service import (
    close_run,
    process_lead_batch,
    trim_batch,
    unprocessed_run,
)

from tests.support.julia_world import (
    ADMIN_ID,
    CONNECTION_ID,
    CORRETOR_ID,
    LEAD_CHAT,
    ORG_ID as ORG,
    OWNER_ID,
    World,
    buffer_lead,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    # The disclosure link is `<SW public base URL>/privacidade/<slug>`: resolved from the
    # product-URL env scheme, never a literal.
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    w.seed_chat()
    return w


async def _run(world: World, key: str, **deps_over):
    await process_lead_batch(key, world.buffer.memory_for(key), deps=world.deps(**deps_over))


def _ok(*partes: str, status: str = "respondido", actions=(), cid: str = "11111111-1111-4111-8111-111111111111"):
    return TurnResult(conversation_id=cid, partes=tuple(partes), status=status, actions=tuple(actions))


# ── 11.3: the disclosure bubble ─────────────────────────────────────────────
class TestDisclosure:
    async def test_first_turn_sends_the_disclosure_BEFORE_the_reply_bubbles(self, world):
        world.agents = FakeAgentsClient([_ok("Prazer, Ana!", "Comprar ou alugar?")])
        key = buffer_lead(world, LEAD_CHAT, ["Oi, vi um anúncio"])
        await _run(world, key)
        texts = world.sent_texts()
        assert len(texts) == 3
        assert texts[0].startswith("Oi! Eu sou Julia, assistente virtual da Empresa Exemplo.")
        assert "https://sw.example.test/privacidade/" in texts[0]
        assert "{link}" not in texts[0] and "{empresa}" not in texts[0]
        assert texts[1:] == ["Prazer, Ana!", "Comprar ou alugar?"]

    async def test_later_turns_carry_no_disclosure(self, world):
        world.agents = FakeAgentsClient([_ok("um"), _ok("dois")])
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        await _run(world, k)
        buffer_lead(world, LEAD_CHAT, ["quero comprar"], ids=["m2"])
        await _run(world, k)
        texts = world.sent_texts()
        assert sum("assistente virtual" in t for t in texts) == 1
        assert texts[-1] == "dois"

    async def test_conversation_id_is_stored_once_the_disclosure_and_reply_went_out(self, world):
        world.agents = FakeAgentsClient([_ok("oi!", cid="22222222-2222-4222-8222-222222222222")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.chat_row()["agente_conversation_id"] == "22222222-2222-4222-8222-222222222222"

    async def test_a_silent_first_turn_sends_nothing_and_does_not_burn_the_disclosure(self, world):
        world.agents = FakeAgentsClient([_ok(status="silencio"), _ok("agora sim")])
        k = buffer_lead(world, LEAD_CHAT, ["..."], ids=["m1"])
        await _run(world, k)
        assert world.sent_texts() == []
        assert world.chat_row()["agente_conversation_id"] is None
        buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m2"])
        await _run(world, k)
        assert "assistente virtual" in world.sent_texts()[0]  # the disclosure still goes with the first REAL reply

    async def test_the_disclosure_failing_to_build_sends_no_reply(self, world, monkeypatch):
        monkeypatch.delenv("PRODUCT_URL_SOCIAL_WIRING")
        monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.sent_texts() == []

    async def test_bubbles_are_spaced_by_the_configured_delay(self, world):
        world.cfg = world.cfg.model_copy(update={"whatsapp_paragraph_delay_seconds": 1.5})
        world.agents = FakeAgentsClient([_ok("a", "b")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.slept == [1.5, 1.5]  # disclosure | a | b => two gaps

    async def test_outbound_bubbles_are_recorded_published_and_marked_as_Julias_own(self, world):
        world.agents = FakeAgentsClient([_ok("oi!")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        rows = [m for m in world.messages() if m["direction"] == "outbound"]
        assert [m["body"] for m in rows][-1] == "oi!"
        assert len(rows) == 2
        for msg in world.waha.sent_messages:
            assert world.redis.get(f"julia:julia_out:{msg['id']}")  # her echo will be recognised (L3)
        assert [e for e, _ in world.bus_events()].count("message.new") == 2


# ── 11.4: handoff ───────────────────────────────────────────────────────────
class TestHandoff:
    def _handoff(self, motivo="quer falar com um corretor"):
        return _ok("Vou chamar um corretor.", status="handoff", actions=[HandoffAction(motivo=motivo)])

    async def test_handoff_pauses_the_chat_publishes_chat_upsert_and_notifies_the_owner(self, world):
        world.agents = FakeAgentsClient([self._handoff()])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["quero falar com humano"]))
        assert world.chat_row()["agente_pausado"] is True
        upserts = [p for e, p in world.bus_events() if e == "chat.upsert"]
        assert upserts[-1]["agente_pausado"] is True and upserts[-1]["chat_id"] == LEAD_CHAT
        (n,) = world.notifications()
        assert n["user_id"] == OWNER_ID and n["metadata"]["tipo"] == "julia_handoff"
        assert n["type"] == "system"  # core's CHECK: a product event is type=system, kind in metadata.tipo
        assert "Ana" in n["message"] and "quer falar com um corretor" in n["message"]
        assert n["metadata"]["link"] == f"/julia/conversas?chat={LEAD_CHAT.replace('@', '%40')}"

    async def test_the_reply_bubbles_go_out_before_the_pause(self, world):
        world.agents = FakeAgentsClient([self._handoff()])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        assert "Vou chamar um corretor." in world.sent_texts()

    async def test_the_next_message_after_a_handoff_still_reaches_agents_which_keeps_the_agent_silent(self, world):
        """No local gate: SW asks agents again, and agents (the participant is paused server-side) answers
        `conversa_pausada` -- so nothing is sent, and the message joins the thread."""
        world.agents = FakeAgentsClient([
            self._handoff(),
            TurnResult(conversation_id="11111111-1111-4111-8111-111111111111", thread_id="11111111-1111-4111-8111-111111111111",
                       partes=(), status="conversa_pausada", participante_estado="pausado"),
        ])
        k = buffer_lead(world, LEAD_CHAT, ["humano"], ids=["m1"])
        await _run(world, k)
        enviados = len(world.sent_texts())
        buffer_lead(world, LEAD_CHAT, ["alô?"], ids=["m2"])
        await _run(world, k)
        assert len(world.agents.turns) == 2 and len(world.sent_texts()) == enviados
        assert [m["texto"] for m in world.agents.appended] == ["alô?"]

    async def test_an_admin_target_is_notified_instead_of_the_owner(self, world):
        world.sw.table("whatsapp_connections").update({"agente_handoff_notificar_user_id": ADMIN_ID}).eq("id", CONNECTION_ID).execute()
        world.agents = FakeAgentsClient([self._handoff()])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        assert [n["user_id"] for n in world.notifications()] == [ADMIN_ID]

    async def test_a_demoted_admin_falls_back_to_the_connection_owner_and_logs_an_error(self, world, caplog):
        world.sw.table("whatsapp_connections").update({"agente_handoff_notificar_user_id": ADMIN_ID}).eq("id", CONNECTION_ID).execute()
        world.core.table("noctus_users").update({"org_role": "member"}).eq("id", ADMIN_ID).execute()
        world.agents = FakeAgentsClient([self._handoff()])
        with caplog.at_level("ERROR"):
            await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        assert [n["user_id"] for n in world.notifications()] == [OWNER_ID]
        assert any("no longer owner/admin" in r.message for r in caplog.records)

    async def test_a_corretor_target_is_never_notified(self, world):
        world.sw.table("whatsapp_connections").update({"agente_handoff_notificar_user_id": CORRETOR_ID}).eq("id", CONNECTION_ID).execute()
        world.agents = FakeAgentsClient([self._handoff()])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        assert [n["user_id"] for n in world.notifications()] == [OWNER_ID]

    async def test_a_notification_failure_never_undoes_the_pause(self, world):
        world.agents = FakeAgentsClient([self._handoff()])

        class Boom:
            def table(self, *_a, **_k):
                raise RuntimeError("core down")

        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]), core_client=Boom())
        assert world.chat_row()["agente_pausado"] is True

    async def test_the_motivo_is_escaped_and_capped_in_the_notification(self, world):
        world.agents = FakeAgentsClient([self._handoff("<script>alert(1)</script>" + "x" * 500)])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        msg = world.notifications()[0]["message"]
        assert "<script>" not in msg and "&lt;script&gt;" in msg
        assert len(msg) < 500


# ── 3.1 error table ─────────────────────────────────────────────────────────
class TestErrorTable:
    async def _lead_sees_nothing(self, world, error, **kw):
        world.agents = FakeAgentsClient([error])
        key = buffer_lead(world, LEAD_CHAT, ["oi"])
        await _run(world, key, **kw)
        assert world.sent_texts() == [], "L2: a lead never gets an error (or anything) on a failed turn"
        return key

    async def test_401_marks_the_link_token_invalido_and_stays_silent(self, world):
        await self._lead_sees_nothing(world, AgentsTokenInvalid(code=None))
        assert julia.ler_erro_link(ORG, cfg=world.cfg) == julia.LINK_ERROR_MESSAGES["token_invalido"]

    async def test_403_marks_the_link_token_invalido(self, world):
        await self._lead_sees_nothing(world, AgentsTokenInvalid(code="issuer_not_allowed"))
        assert julia.ler_erro_link(ORG, cfg=world.cfg)

    async def test_404_agent_not_found_is_surfaced(self, world):
        await self._lead_sees_nothing(world, AgentNotFound(code="agent_not_found"))
        assert julia.ler_erro_link(ORG, cfg=world.cfg) == julia.LINK_ERROR_MESSAGES["agent_not_found"]

    @pytest.mark.parametrize("code", ["agent_inactive", "no_active_version", "prompt_too_large"])
    async def test_409_unavailable_is_surfaced(self, world, code):
        await self._lead_sees_nothing(world, AgentUnavailable(code, code=code))
        assert julia.ler_erro_link(ORG, cfg=world.cfg) == julia.LINK_ERROR_MESSAGES["agent_unavailable"]

    async def test_424_llm_not_configured_is_surfaced(self, world):
        await self._lead_sees_nothing(world, LlmNotConfigured(code="llm_not_configured"))
        assert julia.ler_erro_link(ORG, cfg=world.cfg) == julia.LINK_ERROR_MESSAGES["llm_not_configured"]

    @pytest.mark.parametrize("error", [
        AgentsBadRequest(code="invalid_field"), IdempotencyConflict(code="x"),
        AgentsUpstreamError(code="llm_upstream"), AgentsTimeout("slow"),
    ])
    async def test_422_409conflict_502_timeout_log_and_stay_silent(self, world, error, caplog):
        with caplog.at_level("ERROR"):
            await self._lead_sees_nothing(world, error)
        assert caplog.records, "bugs and upstream faults are error-logged"

    async def test_a_successful_turn_clears_a_stale_link_error(self, world):
        julia.registrar_erro_link(ORG, "token_invalido", cfg=world.cfg)
        world.agents = FakeAgentsClient([_ok("oi")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert julia.ler_erro_link(ORG, cfg=world.cfg) is None

    async def test_409_turn_in_progress_requeues_the_batch_ONCE_after_5s(self, world):
        world.agents = FakeAgentsClient([TurnInProgress(code="turn_in_progress"), TurnInProgress(code="turn_in_progress")])
        key = buffer_lead(world, LEAD_CHAT, ["oi"])
        await _run(world, key)
        due = world.buffer.redis.zscore(world.buffer.due_set_key, key)
        assert due is not None and 3 < due - __import__("time").time() <= 5.5
        assert world.sent_texts() == []
        # the batch is NOT closed: still unprocessed
        assert unprocessed_run(world.buffer.memory_for(key))
        # second failure: gives up (no endless loop) and closes the run
        world.buffer.redis.zrem(world.buffer.due_set_key, key)
        await _run(world, key)
        assert world.buffer.redis.zscore(world.buffer.due_set_key, key) is None
        assert unprocessed_run(world.buffer.memory_for(key)) == []

    async def test_429_capacidade_requeues_after_retry_after_max_3_times(self, world):
        errs = [CapacityExceeded(code="capacidade", retry_after=40) for _ in range(4)]
        world.agents = FakeAgentsClient(errs)
        key = buffer_lead(world, LEAD_CHAT, ["oi"])
        import time

        for attempt in range(3):
            await _run(world, key)
            due = world.buffer.redis.zscore(world.buffer.due_set_key, key)
            assert due is not None and 35 < due - time.time() <= 40.5, f"attempt {attempt}"
            world.buffer.redis.zrem(world.buffer.due_set_key, key)
        await _run(world, key)  # the 4th failure: dropped, not re-queued
        assert world.buffer.redis.zscore(world.buffer.due_set_key, key) is None
        assert unprocessed_run(world.buffer.memory_for(key)) == []
        assert world.sent_texts() == []

    async def test_no_agents_client_in_prod_means_no_reply_and_a_nao_configurado_link(self, world):
        key = buffer_lead(world, LEAD_CHAT, ["oi"])
        await _run(world, key, agents_client_factory=lambda org: None)
        assert world.sent_texts() == []
        assert julia.ler_erro_link(ORG, cfg=world.cfg) == julia.LINK_ERROR_MESSAGES["nao_configurado"]

    async def test_a_hung_agents_call_is_cut_at_the_outer_guard(self, world):
        import asyncio

        class Hang(FakeAgentsClient):
            async def run_turn(self, req):
                await asyncio.sleep(5)

        world.agents = Hang()
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]), turn_timeout_s=0.05)
        assert world.sent_texts() == []


@pytest.fixture(autouse=True)
def _one_fake_redis(world, monkeypatch):
    """Every `redis.Redis.from_url` in the module under test resolves to the World's
    single fakeredis -- the EXTERNAL seam, exactly like the router tests' hermetic fixture."""
    monkeypatch.setattr("redis.Redis.from_url", lambda *_a, **_kw: world.redis)


# ── L3 / pause / H3 / switch-off ────────────────────────────────────────────
class TestGuards:
    async def test_the_mirror_saying_paused_is_not_a_gate_agents_decides(self, world):
        world.sw.table("whatsapp_chats").update({"agente_pausado": True}).eq("chat_id", LEAD_CHAT).execute()
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert len(world.agents.turns) == 1 and world.sent_texts() != []

    async def test_L3_a_human_pausing_the_agent_DURING_the_turn_discards_the_reply(self, world):
        """The re-check is LIVE (`GET thread`, never the mirror): a pause that landed after the turn decided wins."""
        cid = "11111111-1111-4111-8111-111111111111"

        def human_steps_in(req):
            world.agents.participantes[(cid, "julia")] = "pausado"  # agents' pause, set by the human's PATCH
            return _ok("resposta tardia")

        world.agents = FakeAgentsClient([human_steps_in])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.sent_texts() == [], "agents' state is re-read after the turn returns and BEFORE sending"

    async def test_a_timed_pause_that_already_ran_out_does_not_discard_the_reply(self, world):
        from datetime import datetime, timedelta, timezone
        from app.clients.agents import ParticipanteInfo, ThreadInfo

        cid = "11111111-1111-4111-8111-111111111111"
        world.agents = FakeAgentsClient([_ok("voltei")])
        passado = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

        async def obter(thread_id):
            return ThreadInfo(thread_id=thread_id, participantes=(ParticipanteInfo(agent_key="julia", estado="pausado", pausado_ate=passado),))

        world.agents.obter_thread = obter
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert "voltei" in world.sent_texts() and cid

    async def test_an_unreadable_thread_at_the_pre_send_check_sends_on_agents_decision(self, world):
        from app.clients.agents import AgentsTimeout

        world.agents = FakeAgentsClient([_ok("oi!")], errors={"obter_thread": AgentsTimeout()})
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert "oi!" in world.sent_texts()

    async def test_H3_empty_authorized_numbers_at_worker_time_fails_closed(self, world):
        world.sw.table("whatsapp_connections").update({"authorized_numbers": []}).eq("id", CONNECTION_ID).execute()
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.agents.turns == [] and world.sent_texts() == []

    async def test_julia_switched_off_means_no_turn(self, world):
        world.sw.table("whatsapp_connections").update({"agente_leads_ativo": False}).eq("id", CONNECTION_ID).execute()
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.agents.turns == []

    async def test_an_unknown_connection_means_no_turn(self, world):
        key = julia.lead_key("00000000-0000-4000-8000-0000000000ff", LEAD_CHAT)
        from noctusai_lib.domain.chatbot import QueuedConversationMessage

        world.buffer.buffer_inbound(QueuedConversationMessage(conversation_id=key, text="oi", direction="inbound", provider_message_id="m1"))
        await process_lead_batch(key, world.buffer.memory_for(key), deps=world.deps())
        assert world.agents.turns == []

    async def test_a_foreign_key_is_ignored(self, world):
        await process_lead_batch("5511988887777", [{"direction": "inbound", "text": "x"}], deps=world.deps())
        assert world.agents.turns == []


# ── M4: limits + batch cap ──────────────────────────────────────────────────
class TestLimits:
    async def test_per_chat_limit_is_10_turns_an_hour_and_the_11th_is_dropped_before_agents(self, world):
        key = julia.lead_key(CONNECTION_ID, LEAD_CHAT)
        for i in range(10):
            buffer_lead(world, LEAD_CHAT, [f"msg {i}"], ids=[f"m{i}"])
            await _run(world, key)
        assert len(world.agents.turns) == 10
        buffer_lead(world, LEAD_CHAT, ["msg 11"], ids=["m11"])
        await _run(world, key)
        assert len(world.agents.turns) == 10, "the 11th never reached agents"

    async def test_per_connection_limit_applies_across_chats(self, world):
        world.cfg = world.cfg.model_copy(update={"julia_agente_max_turns_per_connection_minute": 2})
        for n in range(3):
            chat = f"55119888800{n:02d}@c.us"
            world.seed_chat(chat)
            await _run(world, buffer_lead(world, chat, ["oi"], ids=[f"c{n}"]))
        assert len(world.agents.turns) == 2

    async def test_batch_is_capped_at_20_messages_and_16k_chars_dropping_the_OLDEST(self, world):
        texts = [f"{i:02d}" + "x" * 998 for i in range(25)]  # 25 x 1000 chars
        await _run(world, buffer_lead(world, LEAD_CHAT, texts))
        sent = world.agents.turns[0].messages
        assert len(sent) == 16 and sum(len(m.texto) for m in sent) <= 16000
        assert sent[-1].texto.startswith("24") and sent[0].texto.startswith("09")

    async def test_a_single_huge_message_is_cut_to_8000_chars(self, world):
        await _run(world, buffer_lead(world, LEAD_CHAT, ["y" * 20000]))
        assert len(world.agents.turns[0].messages[0].texto) == 8000

    async def test_more_than_20_short_messages_keep_the_newest_20_in_order(self, world):
        await _run(world, buffer_lead(world, LEAD_CHAT, [str(i) for i in range(30)]))
        assert [m.texto for m in world.agents.turns[0].messages] == [str(i) for i in range(10, 30)]

    def test_trim_batch_is_pure_and_keeps_provider_ids(self):
        run = [{"text": "a" * 9000, "provider_message_id": "1"}, {"text": "b", "provider_message_id": "2"}]
        out = trim_batch(run, max_chars=16000)
        assert [i["provider_message_id"] for i in out] == ["1", "2"] and len(out[0]["text"]) == 8000


# ── B2: run semantics ───────────────────────────────────────────────────────
class TestRunSemantics:
    async def test_every_provider_message_id_rides_the_request(self, world):
        await _run(world, buffer_lead(world, LEAD_CHAT, ["a", "b", "c"], ids=["w1", "w2", "w3"]))
        assert [m.provider_message_id for m in world.agents.turns[0].messages] == ["w1", "w2", "w3"]

    async def test_request_carries_the_channel_identity_phone_and_push_name(self, world):
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        req = world.agents.turns[0]
        assert (req.agent_key, req.channel, req.connection_id, req.chat_id) == ("julia", "whatsapp", CONNECTION_ID, LEAD_CHAT)
        assert (req.phone_e164, req.display_name) == ("+5511988887777", "Ana")

    async def test_the_agent_key_is_the_connections_not_a_constant(self, world):
        world.sw.table("whatsapp_connections").update({"agente_leads_key": "outro-agente"}).eq("id", CONNECTION_ID).execute()
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.agents.turns[0].agent_key == "outro-agente"

    async def test_an_inbound_landing_after_the_turn_started_is_not_swallowed(self, world):
        key = buffer_lead(world, LEAD_CHAT, ["primeira"], ids=["m1"])

        def late_arrival(req):
            buffer_lead(world, LEAD_CHAT, ["chegou durante o turno"], ids=["m2"])
            return _ok("resposta")

        world.agents = FakeAgentsClient([late_arrival])
        await _run(world, key)
        pending = unprocessed_run(world.buffer.memory_for(key))
        assert [i["provider_message_id"] for i in pending] == ["m2"]

    def test_unprocessed_run_ignores_claimed_ids_and_outbound_noise(self):
        mem = [
            {"direction": "inbound", "text": "a", "provider_message_id": "1"},
            {"direction": "outbound", "text": "[processado]", "metadata": {"processed_ids": ["1"]}},
            {"direction": "inbound", "text": "b", "provider_message_id": "2"},
            {"direction": "inbound", "text": "   ", "provider_message_id": "3"},
        ]
        assert [i["provider_message_id"] for i in unprocessed_run(mem)] == ["2"]

    async def test_lid_chats_resolve_the_phone_through_waha(self, world):
        lid = "99887766@lid"
        world.seed_chat(lid)
        world.waha.fake_lid_phones[lid] = "5511977776666@c.us"
        await _run(world, buffer_lead(world, lid, ["oi"]))
        assert world.agents.turns[0].phone_e164 == "+5511977776666"


# ── no inbound message can delete anything (owner 2026-10-21) ───────────────
class TestLeadMessageNeverDeletes:
    """A lead cannot trigger a destructive action on a public number. The old keyword path ("apagar meus dados") is gone:
    the phrase is an ordinary message Julia answers; she registers a data request through her tool, an admin decides."""

    @pytest.mark.parametrize("texto", ["apagar meus dados", "Por favor, APAGAR os dados", "não vou apagar os dados"])
    async def test_the_phrase_deletes_nothing_and_the_turn_goes_on(self, world, texto):
        world.agents = FakeAgentsClient()
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        await _run(world, k)
        contato_id = world.contato()["id"]
        turnos = len(world.agents.turns)
        buffer_lead(world, LEAD_CHAT, [texto], ids=["m9"])
        await _run(world, k)
        assert len(world.agents.turns) == turnos + 1
        assert world.agents.turns[-1].messages[-1].texto == texto
        assert world.agents.leads_apagados == [] and world.agents.deletions == []
        assert world.contato() is not None and world.contato()["id"] == contato_id
        assert world.messages() and world.chat_row() is not None
        assert world.sent_texts()[-1] in world.agents.DEFAULT_PARTES  # agents' partes: no reply text from code
        assert world.rows("julia_solicitacoes_titular") == []  # no keyword creates a request

    def test_the_keyword_path_and_its_hardcoded_confirmations_are_gone(self):
        for nome in ("is_deletion_request", "MENSAGEM_APAGADO", "MENSAGEM_APAGADO_PARCIAL"):
            assert not hasattr(julia, nome)


# ── static guard: the lead path never touches the operator stack ────────────
class TestOperatorIsolation:
    @pytest.mark.parametrize("module", ["julia_lead_turn_service", "julia_agente_service"])
    def test_lead_modules_never_import_the_operator_stack(self, module):
        path = Path(__file__).resolve().parents[2] / "app" / "services" / f"{module}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        forbidden = ("chatbot_service", "whatsapp_chatbot_service", "whatsapp_intake_service")
        assert not [i for i in imported if any(f in i for f in forbidden)], imported
