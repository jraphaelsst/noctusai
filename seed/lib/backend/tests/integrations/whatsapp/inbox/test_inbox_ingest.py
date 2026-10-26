"""ingest_waha_event: parse -> persist -> publish -> on_new_chat exactly once."""
from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.integrations.whatsapp import FakeWahaClient
from noctusai_lib.integrations.whatsapp.inbox import (
    build_inbox_realtime,
    ingest_waha_event,
    inbox_scope,
)
from noctusai_lib.integrations.whatsapp.lid_auth import InMemoryLidPhoneCache

from .conftest import CONN, ORG, waha_message

CHAT = "5511999990001@c.us"


class Recorder:
    def __init__(self, *, fail_times: int = 0):
        self.calls: list = []
        self._fail = fail_times

    async def __call__(self, org_id, connection_id, chat):
        self.calls.append((org_id, connection_id, chat))
        if self._fail:
            self._fail -= 1
            raise RuntimeError("downstream lead creation exploded")


def run(coro):
    return asyncio.run(coro)


def ingest(record, store, body, rec=None, **kw):
    return run(ingest_waha_event(body, connection=record, chat_store=store, on_new_chat=rec, **kw))


def test_first_inbound_message_creates_chat_and_fires_on_new_chat_once(store, record):
    rec = Recorder()
    result = ingest(record, store, waha_message(mid="m1"), rec)
    assert result.status == "message" and result.new_chat_fired is True
    assert len(rec.calls) == 1
    org_id, connection_id, chat = rec.calls[0]
    assert (org_id, connection_id) == (ORG, CONN)
    assert (chat.chat_id, chat.phone, chat.name, chat.is_group) == (CHAT, "+5511999990001", "Paciente", False)
    assert chat.last_message_preview == "oi" and chat.unread_count == 1


def test_message_and_message_any_pair_creates_one_message_and_one_notification(store, record):
    rec = Recorder()
    first = ingest(record, store, waha_message(mid="m1", event="message"), rec)
    second = ingest(record, store, waha_message(mid="m1", event="message.any"), rec)
    assert (first.status, second.status) == ("message", "duplicate")
    assert len(rec.calls) == 1
    items, _ = store.list_messages(org_id=ORG, connection_id=CONN, chat_id=CHAT)
    assert len(items) == 1


def test_replayed_webhook_never_refires(store, record):
    rec = Recorder()
    for _ in range(3):
        ingest(record, store, waha_message(mid="m1"), rec)
    ingest(record, store, waha_message(mid="m2", ts=1_790_000_100), rec)  # a later message, same chat
    assert len(rec.calls) == 1


def test_concurrent_duplicates_fire_exactly_once(store, record):
    rec = Recorder()

    async def burst():
        await asyncio.gather(*[
            ingest_waha_event(waha_message(mid="m1", event=e), connection=record, chat_store=store, on_new_chat=rec)
            for e in ("message", "message.any", "message", "message.any")
        ])

    run(burst())
    assert len(rec.calls) == 1
    items, _ = store.list_messages(org_id=ORG, connection_id=CONN, chat_id=CHAT)
    assert len(items) == 1


def test_downstream_deletion_cannot_refire_because_the_chat_row_persists(store, record):
    rec = Recorder()
    ingest(record, store, waha_message(mid="m1"), rec)
    # the product deletes the lead the callback created -> nothing touches the chat row
    ingest(record, store, waha_message(mid="m2", ts=1_790_000_050), rec)
    assert len(rec.calls) == 1


def test_group_chat_never_fires(store, record):
    rec = Recorder()
    body = waha_message(mid="g1", chat="120363000000000001@g.us", extra={"participant": "5511999990001@c.us"})
    result = ingest(record, store, body, rec)
    assert result.status == "message" and rec.calls == []
    chat = store.get_chat(org_id=ORG, connection_id=CONN, chat_id="120363000000000001@g.us")
    assert chat.is_group is True and chat.phone is None


def test_chat_started_by_an_outbound_message_never_fires(store, record):
    rec = Recorder()
    ingest(record, store, waha_message(mid="o1", from_me=True, event="message.any"), rec)
    ingest(record, store, waha_message(mid="i1", ts=1_790_000_200), rec)  # patient finally answers
    assert rec.calls == []


def test_failing_callback_releases_claim_and_next_inbound_retries(store, record):
    rec = Recorder(fail_times=1)
    first = ingest(record, store, waha_message(mid="m1"), rec)
    assert first.new_chat_fired is False and len(rec.calls) == 1  # no exception to WAHA
    second = ingest(record, store, waha_message(mid="m2", ts=1_790_000_100), rec)
    assert second.new_chat_fired is True and len(rec.calls) == 2
    third = ingest(record, store, waha_message(mid="m3", ts=1_790_000_200), rec)
    assert third.new_chat_fired is False and len(rec.calls) == 2


def test_no_callback_does_not_burn_the_claim(store, record):
    ingest(record, store, waha_message(mid="m1"), None)
    rec = Recorder()
    ingest(record, store, waha_message(mid="m2", ts=1_790_000_100), rec)
    assert len(rec.calls) == 1


def test_lid_chat_is_canonicalised_through_the_seed_lid_cache(store, record):
    cache = InMemoryLidPhoneCache()
    cache.bind("33613018058989@lid", "5511999990001")
    rec = Recorder()
    body = waha_message(mid="l1", chat="33613018058989@lid")
    ingest(record, store, body, rec, lid_cache=cache)
    assert rec.calls[0][2].chat_id == CHAT and rec.calls[0][2].phone == "+5511999990001"
    # the same human arriving on the phone jid lands in the SAME chat, no new notification
    ingest(record, store, waha_message(mid="l2", ts=1_790_000_100), rec, lid_cache=cache)
    assert len(rec.calls) == 1
    assert [c.chat_id for c in store.list_chats(org_id=ORG, connection_id=CONN)[0]] == [CHAT]


def test_unknown_lid_is_resolved_over_waha_and_bound(store, record):
    waha = FakeWahaClient()
    waha.fake_lid_phones["33613018058989@lid"] = "5511999990001@c.us"
    cache = InMemoryLidPhoneCache()
    ingest(
        record, store, waha_message(mid="l1", chat="33613018058989@lid"), Recorder(),
        lid_cache=cache, waha_client_factory=lambda rec: waha,
    )
    assert cache.get_phone_for_lid("33613018058989@lid") == "5511999990001"
    assert store.get_chat(org_id=ORG, connection_id=CONN, chat_id=CHAT) is not None


def test_unresolvable_lid_keeps_the_lid_id_and_no_phone(store, record):
    rec = Recorder()
    ingest(record, store, waha_message(mid="l1", chat="99999@lid"), rec, lid_cache=InMemoryLidPhoneCache())
    chat = rec.calls[0][2]
    assert chat.chat_id == "99999@lid" and chat.phone is None


def test_sender_never_rebuilds_the_chat_id_for_own_messages(store, record):
    """fromMe: `from` is OUR number; the chat is `to`."""
    ingest(record, store, waha_message(mid="o1", from_me=True, event="message.any"), None)
    assert store.get_chat(org_id=ORG, connection_id=CONN, chat_id=CHAT) is not None
    assert store.get_chat(org_id=ORG, connection_id=CONN, chat_id="5511000000000@c.us") is None


def test_ack_updates_message_and_publishes(store, record):
    realtime = build_inbox_realtime(allow_in_process=True)
    ingest(record, store, waha_message(mid="o1", from_me=True, event="message.any"), None, realtime=realtime)
    ack = {"event": "message.ack", "payload": {"id": "o1", "ack": 3}}
    result = ingest(record, store, ack, None, realtime=realtime)
    assert result.status == "ack"
    items, _ = store.list_messages(org_id=ORG, connection_id=CONN, chat_id=CHAT)
    assert items[0].ack == 3
    unknown = ingest(record, store, {"event": "message.ack", "payload": {"id": "ghost", "ack": 2}}, None)
    assert unknown.status == "ignored"


def test_events_are_published_on_the_connection_scope(store, record):
    realtime = build_inbox_realtime(allow_in_process=True)
    ingest(record, store, waha_message(mid="m1"), None, realtime=realtime)
    ingest(record, store, {"event": "session.status", "payload": {"status": "WORKING"}}, None, realtime=realtime)

    async def drain():
        events = []
        sub = realtime.bus.subscribe(inbox_scope(CONN), last_event_id="0-0")
        async for event in sub:
            events.append(event.event)
            if len(events) == 3:
                break
        return events

    assert run(asyncio.wait_for(drain(), 2)) == ["message.new", "chat.upsert", "session.status"]


@pytest.mark.parametrize("payload", [
    {"id": "x", "from": "status@broadcast", "body": "story", "timestamp": 1},
    {"id": "x", "from": CHAT, "body": "", "hasMedia": False, "timestamp": 1},  # protocol stub
    {"from": CHAT, "body": "no id", "timestamp": 1},
])
def test_non_messages_are_ignored_not_errors(store, record, payload):
    result = ingest(record, store, {"event": "message", "payload": payload}, Recorder())
    assert result.status == "ignored"
    assert store.list_chats(org_id=ORG, connection_id=CONN) == ([], None)


def test_media_message_keeps_type_url_and_media_preview(store, record):
    body = waha_message(
        mid="p1", body="", extra={"hasMedia": True, "media": {"url": "http://waha/f.jpg", "mimetype": "image/jpeg"}},
    )
    ingest(record, store, body, None)
    msg = store.list_messages(org_id=ORG, connection_id=CONN, chat_id=CHAT)[0][0]
    assert (msg.type, msg.media_url) == ("image", "http://waha/f.jpg")
    assert store.get_chat(org_id=ORG, connection_id=CONN, chat_id=CHAT).last_message_preview == "[mídia]"


def test_sao_paulo_ms_timestamps_are_normalised(store, record):
    ingest(record, store, waha_message(mid="m1", ts=1_790_000_000_000), None)
    msg = store.list_messages(org_id=ORG, connection_id=CONN, chat_id=CHAT)[0][0]
    assert msg.timestamp.startswith("2026-")
