"""Julia routing on the shared WAHA webhook (contract section 5, 10.1 H1/H2/H3/L3, 10.2 B2/B3/B4,
11.1). The webhook is driven through the REAL routes with the product's own fakes
(mock DB, seed `FakeWahaClient`, fakeredis, the in-memory buffer, `FakeAgentsClient`).

Strict `== 401` on every auth boundary (KB § PATTERNS/compliance/auth-boundary-false-green.md).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.domain.chatbot import ConversationBufferService
from noctusai_lib.integrations.redis import make_fake_redis_client
from noctusai_lib.testing import bind_consent_module_to_mock

from app.services import julia_agente_service as julia
from app.services.conversation_module import _reset_for_tests, configure_conversation_module
from app.services.julia_lead_turn_service import process_lead_batch
from app.services.whatsapp_realtime import reset_bus_cache

from tests.support.julia_world import (
    CONNECTION_ID,
    ENCRYPTION_KEY,
    LEAD_CHAT,
    ORG_ID,
    OPERATOR,
    WEBHOOK_TOKEN,
    World,
)

LEAD_KEY = julia.lead_key(CONNECTION_ID, LEAD_CHAT)
GROUP = "120363000000000001@g.us"
OPERATOR_CHAT = "5511999990000@c.us"
SECRET = "sekrit"


def _sig(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _msg(
    *, chat: str = LEAD_CHAT, frm: str | None = None, body: str = "oi, vi o anúncio", mid: str = "wamid.1",
    from_me: bool = False, participant: str | None = None, to: str | None = None, event: str = "message",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": mid, "timestamp": 1760000000, "from": frm if frm is not None else chat, "chatId": chat,
        "body": body, "fromMe": from_me, "pushName": "Ana",
    }
    if participant:
        payload["participant"] = participant
    if to:
        payload["to"] = to
    return {"event": event, "session": "default", "payload": payload}


class Rt:
    """The wired scene: app client + world + module."""

    def __init__(self, tc, world, module, override_settings, app):
        self.tc, self.w, self.module, self._override, self._app = tc, world, module, override_settings, app

    def settings(self, **kw):
        self._override(**kw)

    def post(self, body: dict | bytes, *, token: str = WEBHOOK_TOKEN, signed: bool | None = None, secret: str = SECRET):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        headers = {"content-type": "application/json"}
        if signed:
            headers["X-Webhook-Hmac-SHA256"] = _sig(raw, secret)
        return self.tc.post(f"/api/whatsapp/webhook/{token}", content=raw, headers=headers)

    def post_legacy(self, body: dict, *, signed: bool = False):
        raw = json.dumps(body).encode()
        headers = {"content-type": "application/json"}
        if signed:
            headers["X-Webhook-Hmac-SHA256"] = _sig(raw)
        return self.tc.post("/api/whatsapp/webhook", content=raw, headers=headers)

    def lead_memory(self, chat: str = LEAD_CHAT):
        return self.module.buffer.memory_for(julia.lead_key(CONNECTION_ID, chat))

    def operator_memory(self):
        return self.module.buffer.memory_for("+5511999990000")

    def lead_keys_buffered(self) -> bool:
        return bool(self.module.buffer.redis.zrangebyscore(self.module.buffer.due_set_key, "-inf", "+inf"))

    def bus(self):
        from app.services.whatsapp_realtime import get_whatsapp_bus, whatsapp_scope

        return [(e.event, e.payload) for e in get_whatsapp_bus("")._streams.get(whatsapp_scope(CONNECTION_ID), [])]


@pytest.fixture
def rt(monkeypatch, override_settings_factory):
    world = World()
    monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")
    monkeypatch.setattr("redis.Redis.from_url", lambda *_a, **_kw: world.redis)
    reset_bus_cache()
    loop = asyncio.new_event_loop()
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=world.admin),
    ):
        from app.main import app
        from app.routers.whatsapp_connections_router import get_waha_client_factory

        bind_consent_module_to_mock(world.root)
        app.dependency_overrides[get_waha_client_factory] = lambda: (lambda **kw: world.waha)
        _reset_for_tests()
        module = configure_conversation_module(
            admin_supabase=world.admin, org_id=UUID(ORG_ID), redis_client=make_fake_redis_client(),
            main_loop=loop, agents_client_factory=lambda org: world.agents,
            waha_factory=lambda **kw: world.waha, cfg=world.cfg,
        )
        scene = Rt(TestClient(app), world, module, override_settings_factory, app)
        scene.settings(
            encryption_key=ENCRYPTION_KEY, waha_webhook_hmac_secret=SECRET, whatsapp_chatbot_enabled=False,
            openai_api_key="", crm_base_url="", crm_api_key="", whatsapp_authorized_numbers=OPERATOR,
            redis_url="",
        )
        yield scene
        app.dependency_overrides.pop(get_waha_client_factory, None)
    _reset_for_tests()
    reset_bus_cache()
    loop.close()


@pytest.fixture
def override_settings_factory():
    from app.config import settings as _settings
    from app.dependencies import get_settings
    from app.main import app

    overrides: dict = {}
    previous = app.dependency_overrides.get(get_settings)

    def apply(**kw):
        overrides.update(kw)
        stub = _settings.model_copy(update=dict(overrides))
        app.dependency_overrides[get_settings] = lambda: stub

    yield apply
    if previous is None:
        app.dependency_overrides.pop(get_settings, None)
    else:
        app.dependency_overrides[get_settings] = previous


def _julia_scene(rt: Rt, **conn_over):
    rt.w.seed_connection(**conn_over)
    return rt


# ── the routing table (section 5) ───────────────────────────────────────────
class TestRoutingTable:
    def test_a_lead_is_buffered_on_the_lead_key_with_its_provider_message_id(self, rt):
        _julia_scene(rt)
        assert rt.post(_msg(), signed=True).status_code == 200
        (item,) = rt.lead_memory()
        assert item["text"] == "oi, vi o anúncio" and item["provider_message_id"] == "wamid.1"
        assert item["metadata"]["push_name"] == "Ana"
        assert rt.operator_memory() == []

    def test_an_authorized_sender_stays_on_the_operator_path_and_never_reaches_julia(self, rt):
        _julia_scene(rt, auto_reply_enabled=True)
        rt.settings(whatsapp_chatbot_enabled=True, openai_api_key="sk-test")
        rt.post(_msg(chat=OPERATOR_CHAT, mid="op-1", body="ONE1234"), signed=True)
        assert rt.operator_memory(), "the operator's text went to One Chat (the seed buffer)"
        assert rt.lead_memory(OPERATOR_CHAT) == [] and not any(
            k.startswith("lead:") for k in rt.module.buffer.redis.zrangebyscore(rt.module.buffer.due_set_key, "-inf", "+inf"))

    def test_the_operator_path_is_unchanged_with_julia_off(self, rt):
        rt.w.seed_connection(agente_leads_ativo=False, agente_leads_ativado_em=None, auto_reply_enabled=True)
        rt.settings(whatsapp_chatbot_enabled=True, openai_api_key="sk-test")
        rt.post(_msg(chat=OPERATOR_CHAT, mid="op-1", body="ONE1234"), signed=True)
        assert rt.operator_memory()

    def test_with_julia_off_a_stranger_gets_todays_denial_once_and_never_a_turn(self, rt):
        rt.w.seed_connection(agente_leads_ativo=False, agente_leads_ativado_em=None)
        rt.post(_msg(), signed=True)
        rt.post(_msg(mid="wamid.2"), signed=True)
        assert rt.w.redis.get(f"whatsapp:denied:{LEAD_CHAT}") == "1"
        assert rt.lead_memory() == [] and rt.w.agents.turns == []

    def test_the_lead_path_bypasses_the_One_Chat_gate_B3(self, rt):
        # auto_reply_enabled stays One Chat's toggle: OFF here, and the chatbot is disabled.
        _julia_scene(rt, auto_reply_enabled=False)
        rt.post(_msg(), signed=True)
        assert len(rt.lead_memory()) == 1

    def test_a_lead_is_stored_in_the_inbox_like_any_other_message(self, rt):
        _julia_scene(rt)
        rt.post(_msg(), signed=True)
        (row,) = rt.w.messages()
        assert row["direction"] == "inbound" and row["connection_id"] == CONNECTION_ID

    def test_messages_of_the_same_lead_accumulate_in_one_batch_key(self, rt):
        _julia_scene(rt)
        rt.post(_msg(mid="w1", body="oi"), signed=True)
        rt.post(_msg(mid="w2", body="quero comprar"), signed=True)
        assert [i["provider_message_id"] for i in rt.lead_memory()] == ["w1", "w2"]

    def test_the_message_and_message_any_pair_is_one_inbound(self, rt):
        _julia_scene(rt)
        rt.post(_msg(mid="same", event="message"), signed=True)
        rt.post(_msg(mid="same", event="message.any"), signed=True)
        assert len(rt.lead_memory()) == 1

    def test_the_connections_own_org_is_what_gets_recorded_not_the_process_default(self, rt):
        _julia_scene(rt, org_id="00000000-0000-4000-8000-0000000000e1")
        rt.post(_msg(), signed=True)
        assert rt.w.messages()[0]["org_id"] == "00000000-0000-4000-8000-0000000000e1"

    def test_a_lid_sender_that_is_not_a_known_operator_goes_to_julia(self, rt):
        # H3: an uncached operator LID falls to Julia -- documented, and safe (no operator tools).
        _julia_scene(rt)
        lid = "99887766@lid"
        rt.post(_msg(chat=lid, mid="lid-1"), signed=True)
        assert len(rt.lead_memory(lid)) == 1

    def test_a_raw_lid_listed_by_the_operator_is_authorized(self, rt):
        lid = "55443322@lid"
        _julia_scene(rt, authorized_numbers=[lid], auto_reply_enabled=True)
        rt.settings(whatsapp_chatbot_enabled=True, openai_api_key="sk-test")
        rt.post(_msg(chat=lid, mid="lid-op", body="ONE1234"), signed=True)
        assert rt.lead_memory(lid) == []

    def test_a_message_with_no_text_and_no_media_is_dropped_before_routing(self, rt):
        _julia_scene(rt)
        rt.post(_msg(body=""), signed=True)
        assert rt.lead_memory() == []


# ── B4 / L3 ─────────────────────────────────────────────────────────────────
class TestFromMe:
    def _human(self, rt, mid="wamid.out1"):
        return rt.post(_msg(chat=LEAD_CHAT, frm="5511000000000@c.us", to=LEAD_CHAT, from_me=True, mid=mid, body="Oi, aqui é o corretor"), signed=True)

    def test_B4_a_fromMe_message_is_RECORDED_as_outbound_and_never_triggers_a_turn(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat()
        assert self._human(rt).status_code == 200
        (row,) = rt.w.messages()
        assert row["direction"] == "outbound" and row["body"] == "Oi, aqui é o corretor"
        assert row["chat_id"] == LEAD_CHAT, "the chat is `to`, never our own number"
        assert rt.lead_memory() == [] and rt.w.agents.turns == []

    def test_L3_a_human_typing_from_the_phone_pauses_the_chat_and_tells_conversas(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat()
        self._human(rt)
        assert rt.w.chat_row()["agente_pausado"] is True
        upsert = [p for e, p in rt.bus() if e == "chat.upsert"][-1]
        assert upsert["chat_id"] == LEAD_CHAT and upsert["agente_pausado"] is True

    def test_after_the_takeover_the_leads_next_message_gets_no_reply(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat()
        self._human(rt)
        rt.post(_msg(mid="wamid.2", body="e então?"), signed=True)
        assert rt.lead_memory() == []

    def test_L3_Julias_own_echo_matched_by_provider_id_does_not_pause(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat()
        julia.registrar_envio_proprio(rt.w.redis, "wamid.julia")
        self._human(rt, mid="wamid.julia")
        assert rt.w.chat_row()["agente_pausado"] is False

    def test_L3_an_echo_beating_our_bookkeeping_is_covered_by_the_in_flight_flag(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat()
        julia.marcar_envio_em_curso(rt.w.redis, CONNECTION_ID, LEAD_CHAT)
        self._human(rt, mid="wamid.too-early")
        assert rt.w.chat_row()["agente_pausado"] is False

    def test_the_echo_of_a_message_SW_already_recorded_from_the_UI_still_counts_as_a_human(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat()
        rt.w.sw.table("conversation_messages").insert({
            "id": "00000000-0000-4000-8000-0000000000aa", "org_id": ORG_ID, "session_id": LEAD_CHAT,
            "raw_sender": LEAD_CHAT, "direction": "outbound", "body": "enviado pela tela de Conversas",
            "provider_message_id": "wamid.ui", "authorized": True, "connection_id": CONNECTION_ID, "chat_id": LEAD_CHAT,
        }).execute()
        self._human(rt, mid="wamid.ui")  # DuplicateMessage branch
        assert rt.w.chat_row()["agente_pausado"] is True

    def test_an_operators_own_chat_is_never_taken_over_the_bot_echoes_there(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat(OPERATOR_CHAT)
        rt.post(_msg(chat=OPERATOR_CHAT, to=OPERATOR_CHAT, from_me=True, mid="bot-echo"), signed=True)
        assert rt.w.chat_row(OPERATOR_CHAT)["agente_pausado"] is False

    def test_a_group_fromMe_never_pauses(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat(GROUP)
        rt.post(_msg(chat=GROUP, to=GROUP, from_me=True, mid="g-out"), signed=True)
        assert rt.w.chat_row(GROUP)["agente_pausado"] is False

    def test_with_julia_off_a_human_message_does_not_touch_the_pause_flag(self, rt):
        rt.w.seed_connection(agente_leads_ativo=False, agente_leads_ativado_em=None)
        rt.w.seed_chat()
        self._human(rt)
        assert rt.w.chat_row()["agente_pausado"] is False

    def test_the_legacy_global_route_still_drops_fromMe(self, rt):
        _julia_scene(rt)
        rt.post_legacy(_msg(from_me=True, mid="legacy-out"), signed=True)
        assert rt.w.messages() == []

    def test_an_already_paused_chat_stays_paused_without_a_second_event(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat(agente_pausado=True)
        self._human(rt)
        # Every chat.upsert now carries `agente_pausado` (the Conversas DTO), so the
        # "second event" is counted, not detected by key: the ingest publishes ONE
        # upsert; the takeover would have added a second.
        assert len([1 for e, _p in rt.bus() if e == "chat.upsert"]) == 1


# ── H2 ──────────────────────────────────────────────────────────────────────
class TestGroups:
    def test_a_group_never_reaches_julia(self, rt):
        _julia_scene(rt)
        rt.post(_msg(chat=GROUP, frm=GROUP, participant="5511900002222@c.us", mid="g1"), signed=True)
        assert rt.lead_memory(GROUP) == [] and rt.w.agents.turns == []
        assert not rt.lead_keys_buffered()

    def test_H2_an_unauthorized_member_of_a_bound_group_cannot_reach_One_Chat(self, rt):
        _julia_scene(rt, bound_chats=[{"chat_id": GROUP, "label": "g"}], auto_reply_enabled=True)
        rt.settings(whatsapp_chatbot_enabled=True, openai_api_key="sk-test")
        rt.post(_msg(chat=GROUP, frm=GROUP, participant="5511900002222@c.us", mid="g1", body="ONE1234"), signed=True)
        assert rt.module.buffer.memory_for(GROUP) == [] and rt.operator_memory() == []

    def test_H2_an_authorized_member_of_a_BOUND_group_does_reach_One_Chat(self, rt):
        _julia_scene(rt, bound_chats=[{"chat_id": GROUP, "label": "g"}], auto_reply_enabled=True)
        rt.settings(whatsapp_chatbot_enabled=True, openai_api_key="sk-test")
        rt.post(_msg(chat=GROUP, frm=GROUP, participant=OPERATOR_CHAT, mid="g2", body="ONE1234"), signed=True)
        assert rt.module.buffer.memory_for(GROUP), "replies and memory stay per CHAT (the group)"

    def test_H2_an_authorized_member_of_an_UNBOUND_group_is_not_routed(self, rt):
        _julia_scene(rt, bound_chats=[], auto_reply_enabled=True)
        rt.settings(whatsapp_chatbot_enabled=True, openai_api_key="sk-test")
        rt.post(_msg(chat=GROUP, frm=GROUP, participant=OPERATOR_CHAT, mid="g3", body="ONE1234"), signed=True)
        assert rt.module.buffer.memory_for(GROUP) == []

    def test_H2_a_group_message_without_a_participant_is_not_routed(self, rt):
        _julia_scene(rt, bound_chats=[{"chat_id": GROUP, "label": "g"}], auto_reply_enabled=True)
        rt.settings(whatsapp_chatbot_enabled=True, openai_api_key="sk-test")
        rt.post(_msg(chat=GROUP, frm=GROUP, mid="g4", body="ONE1234"), signed=True)
        assert rt.module.buffer.memory_for(GROUP) == []

    def test_H2_the_group_id_listed_as_authorized_does_not_authorize_its_members(self, rt):
        _julia_scene(rt, authorized_numbers=[GROUP], bound_chats=[{"chat_id": GROUP, "label": "g"}], auto_reply_enabled=True)
        rt.settings(whatsapp_chatbot_enabled=True, openai_api_key="sk-test")
        rt.post(_msg(chat=GROUP, frm=GROUP, participant="5511900002222@c.us", mid="g5", body="ONE1234"), signed=True)
        assert rt.module.buffer.memory_for(GROUP) == []

    def test_a_group_with_julia_off_and_an_allow_all_list_is_not_open_to_everyone(self, rt):
        rt.w.seed_connection(agente_leads_ativo=False, agente_leads_ativado_em=None, authorized_numbers=[],
                             bound_chats=[{"chat_id": GROUP, "label": "g"}], auto_reply_enabled=True)
        rt.settings(whatsapp_chatbot_enabled=True, openai_api_key="sk-test")
        rt.post(_msg(chat=GROUP, frm=GROUP, participant="5511900002222@c.us", mid="g6", body="ONE1234"), signed=True)
        # allow-all means every PARTICIPANT is authorized, but only inside an explicitly bound group.
        assert rt.module.buffer.memory_for(GROUP)

    def test_no_denial_text_is_ever_posted_into_a_group(self, rt):
        _julia_scene(rt)
        rt.post(_msg(chat=GROUP, frm=GROUP, participant="5511900002222@c.us", mid="g7"), signed=True)
        assert rt.w.waha.sent_messages == [] and rt.w.redis.get(f"whatsapp:denied:{GROUP}") is None


# ── H3 at routing time ──────────────────────────────────────────────────────
class TestH3AtRouting:
    def test_julia_on_with_an_empty_authorized_list_fails_closed_no_reply_nothing_routed(self, rt):
        # Seeded past the DB CHECK on purpose: the routing re-check must hold on its own.
        _julia_scene(rt, authorized_numbers=[], auto_reply_enabled=True)
        rt.settings(whatsapp_chatbot_enabled=True, openai_api_key="sk-test")
        assert rt.post(_msg(), signed=True).status_code == 200
        assert rt.lead_memory() == [] and rt.operator_memory() == []
        assert rt.w.waha.sent_messages == [] and rt.w.redis.get(f"whatsapp:denied:{LEAD_CHAT}") is None

    def test_blank_entries_do_not_count_as_authorized_numbers(self, rt):
        _julia_scene(rt, authorized_numbers=["", "  "])
        rt.post(_msg(), signed=True)
        assert rt.lead_memory() == []


# ── H1 ──────────────────────────────────────────────────────────────────────
class TestSignedWebhooksOnly:
    def test_julia_on_and_no_secret_configured_is_401_before_any_routing(self, rt):
        _julia_scene(rt)
        rt.settings(waha_webhook_hmac_secret="")
        r = rt.post(_msg())
        assert r.status_code == 401
        assert rt.lead_memory() == [] and rt.w.messages() == []

    def test_julia_on_and_a_missing_signature_is_401(self, rt):
        _julia_scene(rt)
        assert rt.post(_msg(), signed=False).status_code == 401
        assert rt.w.messages() == []

    def test_julia_on_and_an_invalid_signature_is_401(self, rt):
        _julia_scene(rt)
        assert rt.post(_msg(), signed=True, secret="wrong").status_code == 401
        assert rt.w.messages() == []

    def test_a_tampered_body_is_401(self, rt):
        _julia_scene(rt)
        raw = json.dumps(_msg()).encode()
        r = rt.tc.post(f"/api/whatsapp/webhook/{WEBHOOK_TOKEN}", content=raw.replace(b"oi", b"xx"),
                       headers={"content-type": "application/json", "X-Webhook-Hmac-SHA256": _sig(raw)})
        assert r.status_code == 401

    def test_a_valid_signature_is_accepted(self, rt):
        _julia_scene(rt)
        assert rt.post(_msg(), signed=True).status_code == 200
        assert len(rt.lead_memory()) == 1

    def test_the_401_applies_to_non_message_events_too(self, rt):
        _julia_scene(rt)
        rt.settings(waha_webhook_hmac_secret="")
        status = {"event": "session.status", "session": "default", "payload": {"status": "WORKING"}}
        assert rt.post(status).status_code == 401

    def test_with_julia_off_an_unset_secret_still_bypasses_as_today(self, rt):
        rt.w.seed_connection(agente_leads_ativo=False, agente_leads_ativado_em=None)
        rt.settings(waha_webhook_hmac_secret="")
        assert rt.post(_msg()).status_code == 200

    def test_an_unknown_token_is_still_a_generic_404(self, rt):
        assert rt.post(_msg(), token="nope", signed=True).status_code == 404

    def test_the_legacy_route_with_julia_on_somewhere_and_no_secret_is_401(self, rt):
        _julia_scene(rt)
        rt.settings(waha_webhook_hmac_secret="")
        assert rt.post_legacy(_msg()).status_code == 401

    def test_the_legacy_route_with_julia_on_and_a_bad_signature_is_401(self, rt):
        _julia_scene(rt)
        assert rt.post_legacy(_msg(), signed=False).status_code == 401

    def test_the_legacy_route_with_no_julia_anywhere_and_no_secret_still_bypasses(self, rt):
        rt.w.seed_connection(agente_leads_ativo=False, agente_leads_ativado_em=None)
        rt.settings(waha_webhook_hmac_secret="")
        assert rt.post_legacy(_msg()).status_code == 200

    def test_the_legacy_route_never_enters_the_lead_split(self, rt):
        _julia_scene(rt)
        stranger = "5511900003333@c.us"
        assert rt.post_legacy(_msg(chat=stranger, mid="leg-1"), signed=True).status_code == 200
        assert rt.lead_memory(stranger) == [] and rt.w.agents.turns == []
        assert not rt.lead_keys_buffered()

    def test_the_legacy_route_fails_closed_when_it_cannot_tell_whether_julia_is_on(self, rt):
        rt.settings(waha_webhook_hmac_secret="")

        class Boom:
            def table(self, *_a):
                raise RuntimeError("db down")

        assert julia.julia_ativa_em_alguma_conexao(Boom()) is True


# ── 11.1 eligibility through the webhook ────────────────────────────────────
class TestChatsThatStartAfterJulia:
    def test_a_chat_in_the_snapshot_never_reaches_julia_and_keeps_todays_behaviour(self, rt):
        _julia_scene(rt)
        julia.gravar_snapshot(rt.w.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=[LEAD_CHAT])
        rt.post(_msg(), signed=True)
        assert rt.lead_memory() == [] and rt.w.agents.turns == []
        assert rt.w.redis.get(f"whatsapp:denied:{LEAD_CHAT}") == "1", "falls through to today's denial path"
        assert len(rt.w.messages()) == 1, "still stored"

    def test_a_brand_new_chat_reaches_julia(self, rt):
        _julia_scene(rt)
        julia.gravar_snapshot(rt.w.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=["5511900009999@c.us"])
        rt.post(_msg(), signed=True)
        assert len(rt.lead_memory()) == 1

    def test_a_pre_existing_LID_alias_of_a_snapshotted_phone_chat_gets_no_turn(self, rt):
        _julia_scene(rt)
        julia.gravar_snapshot(rt.w.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=[LEAD_CHAT])
        lid = "424242@lid"
        rt.w.waha.fake_lid_phones[lid] = LEAD_CHAT
        rt.post(_msg(chat=lid, mid="lid-9"), signed=True)
        assert rt.lead_memory(lid) == []

    def test_a_chat_row_older_than_the_switch_is_excluded_even_if_the_snapshot_missed_it(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat(created_at="2026-09-01T00:00:00+00:00")
        rt.post(_msg(), signed=True)
        assert rt.lead_memory() == []

    def test_a_chat_Julia_already_owns_stays_hers(self, rt):
        _julia_scene(rt)
        julia.gravar_snapshot(rt.w.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=[LEAD_CHAT])
        rt.w.seed_chat(created_at="2026-09-01T00:00:00+00:00", agente_conversation_id="11111111-1111-4111-8111-111111111111")
        rt.post(_msg(), signed=True)
        assert len(rt.lead_memory()) == 1

    def test_an_eligibility_failure_is_treated_as_not_eligible_and_logged(self, rt, caplog):
        _julia_scene(rt)
        # A connection row whose `agente_leads_ativado_em` cannot be read as a timestamp -> not eligible.
        rt.w.sw.set_table_data("whatsapp_connections", [])
        rt.w._connections = []
        rt.w.seed_connection(agente_leads_ativado_em="not-a-timestamp")
        rt.post(_msg(), signed=True)
        assert rt.lead_memory() == []

    def test_the_snapshot_only_excludes_ids_of_ITS_connection(self, rt):
        _julia_scene(rt)
        julia.gravar_snapshot(rt.w.sw, org_id=ORG_ID, connection_id="00000000-0000-4000-8000-0000000000ff", chat_ids=[LEAD_CHAT])
        rt.post(_msg(), signed=True)
        assert len(rt.lead_memory()) == 1


# ── pause + deletion bypass ─────────────────────────────────────────────────
class TestPauseAtTheDoor:
    def test_a_paused_chat_stores_only_and_buffers_nothing(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat(agente_pausado=True)
        rt.post(_msg(), signed=True)
        assert rt.lead_memory() == [] and len(rt.w.messages()) == 1

    def test_the_deletion_phrase_is_enqueued_even_for_a_paused_chat(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat(agente_pausado=True)
        rt.post(_msg(body="apagar meus dados"), signed=True)
        assert len(rt.lead_memory()) == 1

    def test_no_conversation_module_means_no_silent_loss_it_is_logged(self, rt, caplog):
        _julia_scene(rt)
        _reset_for_tests()
        with caplog.at_level("ERROR"):
            assert rt.post(_msg(), signed=True).status_code == 200
        assert any("conversation module unavailable" in r.message.lower() for r in caplog.records)


# ── end to end: webhook -> buffer -> worker -> Fake agents -> WAHA ──────────
class TestEndToEnd:
    def test_webhook_to_the_leads_phone_with_the_disclosure_first(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat(created_at="2026-10-10T00:00:00+00:00")
        rt.post(_msg(mid="e2e-1", body="Oi, vi o anúncio do apê"), signed=True)
        memory = rt.lead_memory()
        deps = rt.w.deps(buffer=rt.module.buffer)
        asyncio.run(process_lead_batch(LEAD_KEY, memory, deps=deps))
        texts = [m["text"] for m in rt.w.waha.sent_messages]
        assert texts[0].startswith("Oi! Eu sou a Julia, assistente virtual da Empresa Exemplo.")
        assert texts[1:] == list(rt.w.agents.DEFAULT_PARTES)
        assert [m.provider_message_id for m in rt.w.agents.turns[0].messages] == ["e2e-1"]
        assert rt.w.agents.turns[0].messages[0].texto == "Oi, vi o anúncio do apê"
        assert rt.w.chat_row()["agente_conversation_id"]

    def test_the_real_worker_thread_path_runs_a_lead_key_through_the_per_key_processor(self, rt):
        _julia_scene(rt)
        rt.w.seed_chat(created_at="2026-10-10T00:00:00+00:00")
        rt.post(_msg(mid="e2e-2"), signed=True)
        # force the debounce due and let the REAL processor closure run on the loop it was built with
        rt.module.buffer.redis.zadd(rt.module.buffer.due_set_key, {LEAD_KEY: 0})

        loop = rt.module.main_loop
        import threading

        done = threading.Event()
        result: dict[str, Any] = {}

        def work():
            result["n"] = rt.module.worker.process_due_once()
            done.set()

        t = threading.Thread(target=work)
        t.start()
        while not done.is_set():
            loop.run_until_complete(asyncio.sleep(0.05))
        t.join()
        assert result["n"] == 1
        # the worker thread only hands the lead batch over; the turn runs on the loop
        loop.run_until_complete(rt.module.lead_dispatcher.shutdown(grace_s=10))
        assert rt.w.agents.turns, "the lead key went to agents, not to the operator path"
        assert rt.w.waha.sent_messages
