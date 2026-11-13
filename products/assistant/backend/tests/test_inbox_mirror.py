"""The owner's conversations (migration 022 + `app/services/inbox_mirror.py`): both directions are kept in the seed inbox
store, the intake queue still only ever sees inbound 1:1 text, every inbox route is admin-only (strict 401 / 403), and the
tables are service-role only."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from noctusai_lib.integrations.whatsapp.inbox import FakeWhatsAppChatStore, ingest_waha_event
from noctusai_lib.testing.migrations import migration_sql

from app.services.inbox_mirror import (
    INTAKE_MAX_AGE, MirrorChatStore, build_mirror_store, conversation_should_store, guarded_on_message,
)

ROOT = Path(__file__).resolve().parents[1]
ME = "5511988887777@c.us"
NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
_RECORD = SimpleNamespace(org_id=uuid4(), id=uuid4(), app_enabled=True)


class _IntakeSpy:
    def __init__(self):
        self.messages = []

    def insert_message(self, *, org_id, connection_id, message):
        self.messages.append(message)
        return True


def _event(mid, *, chat=ME, from_me=False, body="oi", source="app", at=None):
    ts = int((at or NOW).timestamp())
    return {"event": "message", "payload": {"id": mid, "from": chat, "to": chat, "fromMe": from_me, "body": body, "timestamp": ts,
                                            "source": source, "hasMedia": False}}


def _stack(excluded=()):
    inbox, intake = FakeWhatsAppChatStore(), _IntakeSpy()
    store = MirrorChatStore(inbox, intake, build_mirror_store(inbox, intake, excluded)._intake_predicate, clock=lambda: NOW)
    return inbox, intake, store


def _ingest(store, body, excluded=()):
    return asyncio.run(ingest_waha_event(
        body, connection=_RECORD, chat_store=store, should_store=conversation_should_store(excluded),
    ))


def test_both_directions_are_kept_but_only_inbound_reaches_the_intake():
    inbox, intake, store = _stack()
    assert _ingest(store, _event("in1")).status == "message"
    assert _ingest(store, _event("out1", from_me=True, body="claro!", source="api")).status == "message"  # the assistant's reply
    page, _more = inbox.list_messages(org_id=_RECORD.org_id, connection_id=_RECORD.id, chat_id=ME)
    assert sorted((m.id, m.from_me) for m in page) == [("in1", False), ("out1", True)]
    assert [m.id for m in intake.messages] == ["in1"]


def test_groups_status_and_the_exclusion_list_are_not_stored_at_all():
    inbox, intake, store = _stack(excluded=["5511999990000"])
    for chat in ("120363000000000000@g.us", "status@broadcast", "5511999990000@c.us"):
        assert _ingest(store, _event("x", chat=chat), excluded=["5511999990000"]).status in {"skipped", "ignored"}
    assert intake.messages == []
    assert inbox.list_chats(org_id=_RECORD.org_id, connection_id=_RECORD.id)[0] == []


def test_history_goes_to_the_inbox_only_never_the_intake():
    inbox, intake, store = _stack()
    _ingest(store, _event("old", at=NOW - INTAKE_MAX_AGE - timedelta(hours=1)))
    assert intake.messages == []
    assert len(inbox.list_messages(org_id=_RECORD.org_id, connection_id=_RECORD.id, chat_id=ME)[0]) == 1


def test_a_failed_intake_append_propagates_so_waha_retries():
    class _Boom:
        def insert_message(self, **_k):
            raise RuntimeError("db down")

    inbox = FakeWhatsAppChatStore()
    store = MirrorChatStore(inbox, _Boom(), build_mirror_store(inbox, _Boom())._intake_predicate, clock=lambda: NOW)
    with pytest.raises(RuntimeError):
        _ingest(store, _event("m1"))


def test_the_live_reply_seam_ignores_the_owners_sends_and_groups():
    seen = []

    async def inner(org_id, connection_id, chat, message):
        seen.append(message.id)

    from noctusai_lib.integrations.whatsapp.inbox import InboxChat, InboxMessage
    from noctusai_lib.integrations.whatsapp.inbox.predicates import inbound_one_to_one_only

    seam = guarded_on_message(inner, inbound_one_to_one_only([]))

    def msg(mid, chat, from_me):
        return InboxMessage(id=mid, chat_id=chat, from_me=from_me, body="oi", type="chat", media_url=None, ack=None,
                            timestamp=NOW.isoformat(), sender_name=None)

    def chat(cid, group=False):
        return InboxChat(chat_id=cid, name="", phone=None, is_group=group, last_message_preview="",
                         last_message_at=None, last_message_from_me=None, unread_count=0)

    asyncio.run(seam(uuid4(), uuid4(), chat(ME), msg("a", ME, False)))
    asyncio.run(seam(uuid4(), uuid4(), chat(ME), msg("b", ME, True)))
    asyncio.run(seam(uuid4(), uuid4(), chat("1@g.us", True), msg("c", "1@g.us", False)))
    assert seen == ["a"]


# ── access: every inbox route is admin-only ─────────────────────────────────────────────────────
CID = "00000000-0000-0000-0000-000000000001"
BASE = f"/api/whatsapp/connections/{CID}"
ROTAS = [
    ("get", f"{BASE}/chats", None), ("get", f"{BASE}/chats/5511988887777@c.us/messages", None),
    ("post", f"{BASE}/chats/5511988887777@c.us/messages", {"text": "oi"}),
    ("post", f"{BASE}/chats/5511988887777@c.us/read", None), ("post", f"{BASE}/backfill", None),
    ("patch", f"{BASE}/chats/5511988887777@c.us/agent-paused", {"paused": True}),
    ("post", f"{BASE}/chats/5511988887777@c.us/apagar-dados", None),
]


@pytest.mark.parametrize("metodo,rota,corpo", ROTAS)
def test_unauthenticated_is_strictly_401(client, metodo, rota, corpo):
    resp = getattr(client.raw(), metodo)(rota, **({"json": corpo} if corpo else {}))
    assert resp.status_code == 401


@pytest.mark.parametrize("metodo,rota,corpo", ROTAS)
def test_a_member_who_is_not_an_org_admin_is_403(client, metodo, rota, corpo):
    resp = getattr(client, metodo)(rota, **({"json": corpo} if corpo else {}))
    assert resp.status_code == 403


# ── the tables (migration 022) ──────────────────────────────────────────────────────────────────
def test_chat_tables_are_tiered_service_only_with_no_browser_policy():
    sql = migration_sql(ROOT, "inbox_conversas")
    for table in ("whatsapp_chats", "whatsapp_messages"):
        assert f"COMMENT ON TABLE assistant.{table} IS 'tier:org';" in sql
        assert f"REVOKE ALL ON assistant.{table} FROM PUBLIC, anon, authenticated;" in sql
        assert f"GRANT ALL ON assistant.{table} TO service_role;" in sql
    assert "TO authenticated" not in sql and "select_own_org" not in sql
    assert "UNIQUE (connection_id, waha_message_id)" in sql  # the dedup guard
    assert "('conversas', 'producao')" in sql  # the nav page is visible


# ── the owner's own messages reach the agent's thread (no turn) ─────────────────────────────────
def _fwd(client, owner="user-1", enabled=True):
    from app.services.humano_para_agente import build_human_forwarder

    return build_human_forwarder(
        agents_factory=lambda: client, owner_user_id=lambda *_: owner, identity_key=lambda: "k", enabled=lambda: enabled,
    )


def _msg(mid="o1", *, from_me=True, source=None, body="te ligo amanha", type_="chat"):
    from noctusai_lib.integrations.whatsapp.inbox import InboxMessage

    return InboxMessage(id=mid, chat_id=ME, from_me=from_me, body=body, type=type_, media_url=None, ack=None,
                        timestamp=NOW.isoformat(), sender_name=None, source=source)


def _agents_with_thread():
    from noctusai_lib.integrations.agents_channel import make_agents_client
    from app.services.intake import chat_ref

    fake = make_agents_client(token="", base_url="", allow_fake=True)
    conn = uuid4()
    tid = fake.thread_id_for(str(conn), chat_ref("k", ME))
    fake.participantes[(tid, "a")] = "ativo"
    return fake, conn


def test_an_owner_message_is_appended_to_the_agents_thread_as_humano():
    fake, conn = _agents_with_thread()
    asyncio.run(_fwd(fake)(uuid4(), conn, None, _msg(source="app")))
    assert len(fake.appended) == 1 and fake.appended[0]["role"] == "humano" and fake.appended[0]["autor_user_id"] == "user-1"
    asyncio.run(_fwd(fake)(uuid4(), conn, None, _msg(source=None)))  # the app's own send (same id: idempotent)
    assert len(fake.appended) == 1


@pytest.mark.parametrize("kw", [{"source": "api"}, {"from_me": False}, {"body": "  "}, {"type_": "image"}])
def test_agent_echoes_inbound_and_non_text_are_never_forwarded(kw):
    fake, conn = _agents_with_thread()
    asyncio.run(_fwd(fake)(uuid4(), conn, None, _msg(**kw)))
    assert fake.appended == []


def test_no_thread_or_switched_off_or_agents_down_forwards_nothing_and_never_raises():
    from noctusai_lib.integrations.agents_channel import make_agents_client

    fake = make_agents_client(token="", base_url="", allow_fake=True)  # no thread for this chat
    asyncio.run(_fwd(fake)(uuid4(), uuid4(), None, _msg()))
    assert fake.appended == []
    fake2, conn = _agents_with_thread()
    asyncio.run(_fwd(fake2, enabled=False)(uuid4(), conn, None, _msg()))
    asyncio.run(_fwd(fake2, owner=None)(uuid4(), conn, None, _msg()))
    assert fake2.appended == []

    class _Down:
        async def buscar_thread(self, **_k):
            raise RuntimeError("down")

    asyncio.run(_fwd(_Down())(uuid4(), uuid4(), None, _msg()))  # no raise


# ── per-chat agent pause: the live reply honours the stored flag ────────────────────────────────
def _pause_seam(paused):
    seen = []

    async def inner(org_id, connection_id, chat, message):
        seen.append(message.id)

    async def is_paused(org_id, connection_id, chat_id):
        if isinstance(paused, Exception):
            raise paused
        return paused

    from noctusai_lib.integrations.whatsapp.inbox.predicates import inbound_one_to_one_only

    return seen, guarded_on_message(inner, inbound_one_to_one_only([]), None, is_paused)


def _chat(cid=ME):
    from noctusai_lib.integrations.whatsapp.inbox import InboxChat

    return InboxChat(chat_id=cid, name="", phone=None, is_group=False, last_message_preview="", last_message_at=None,
                     last_message_from_me=None, unread_count=0)


@pytest.mark.parametrize("paused,expected", [(True, []), (False, ["a"]), (RuntimeError("db"), [])])
def test_a_paused_chat_gets_no_live_reply_unpaused_does_and_an_unverifiable_pause_fails_closed(paused, expected):
    seen, seam = _pause_seam(paused)
    asyncio.run(seam(uuid4(), uuid4(), _chat(), _msg("a", from_me=False)))
    assert seen == expected


def test_the_pause_lookup_reads_the_stored_flag_through_the_store():
    from app.services.inbox_mirror import build_pause_lookup

    inbox = FakeWhatsAppChatStore()
    _ingest(MirrorChatStore(inbox, _IntakeSpy(), build_mirror_store(inbox, _IntakeSpy())._intake_predicate, clock=lambda: NOW),
            _event("m1"))
    is_paused = build_pause_lookup(lambda: inbox)
    args = (_RECORD.org_id, _RECORD.id, ME)
    assert asyncio.run(is_paused(*args)) is False
    inbox.set_agent_paused(org_id=_RECORD.org_id, connection_id=_RECORD.id, chat_id=ME, paused=True, actor="u")
    assert asyncio.run(is_paused(*args)) is True
    assert asyncio.run(is_paused(_RECORD.org_id, _RECORD.id, "other@c.us")) is False


# ── per-chat LGPD erasure ───────────────────────────────────────────────────────────────────────
class _Rpc:
    def __init__(self):
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=3))


def test_delete_purges_the_intake_of_that_chat_only_and_the_agent_thread():
    from noctusai_lib.integrations.agents_channel import make_agents_client
    from app.services.conversa_apagar import build_chat_eraser
    from app.services.intake import chat_ref

    rpc, fake = _Rpc(), make_agents_client(token="", base_url="", allow_fake=True)
    erase = build_chat_eraser(lambda: rpc, lambda: "k", agents_factory=lambda: fake, agent_key=lambda: "assistente")
    org, conn = uuid4(), uuid4()
    asyncio.run(erase(org, conn, ME, "u1"))
    assert rpc.calls == [("apagar_dados_conversa", {"p_org_id": str(org), "p_connection_id": str(conn), "p_chat_ref": chat_ref("k", ME)})]
    assert [(d.agent_key, d.connection_id, d.chat_id) for d in fake.deletions] == [("assistente", str(conn), chat_ref("k", ME))]


def test_delete_without_an_agent_configured_skips_the_agent_and_a_failure_propagates():
    from app.services.conversa_apagar import build_chat_eraser

    def no_agents():
        raise AssertionError("agents must not be called")

    asyncio.run(build_chat_eraser(lambda: _Rpc(), lambda: "k", agents_factory=no_agents, agent_key=lambda: "")(uuid4(), uuid4(), ME, None))

    class _Boom:
        def rpc(self, *_a):
            raise RuntimeError("db down")

    with pytest.raises(RuntimeError):  # the organ answers 502 and erases nothing
        asyncio.run(build_chat_eraser(lambda: _Boom(), lambda: "k", agents_factory=no_agents, agent_key=lambda: "")(uuid4(), uuid4(), ME, None))


def test_migration_carries_the_pause_columns_and_a_chat_scoped_erase_function():
    sql = migration_sql(ROOT, "inbox_conversas")
    assert "agent_paused BOOLEAN NOT NULL DEFAULT false" in sql and "agent_paused_at TIMESTAMPTZ" in sql and "agent_paused_by TEXT" in sql
    assert "chat_ref = p_chat_ref" in sql and "connection_id = p_connection_id" in sql  # scoped to ONE chat
    assert "GRANT EXECUTE ON FUNCTION assistant.apagar_dados_conversa(uuid, uuid, text) TO service_role;" in sql
