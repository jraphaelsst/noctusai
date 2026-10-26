"""Backfill: NOWEB trap, single-flight, one-shot watermark, no on_new_chat."""
from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from noctusai_lib.integrations.whatsapp import FakeWahaClient
from noctusai_lib.integrations.whatsapp.inbox import (
    backfill_connection,
    ingest_waha_event,
    is_backfill_running,
    build_inbox_realtime,
    InboxRealtimeNotConfigured,
)
from noctusai_lib.integrations.whatsapp.inbox import backfill as backfill_mod

from .conftest import CONN, ORG, waha_message

CHAT = "5511999990001@c.us"


def run(coro):
    return asyncio.run(coro)


def _history(n: int, *, now: int = 1_790_000_000) -> list[dict]:
    return [
        {"id": {"_serialized": f"h{i}"}, "body": f"msg {i}", "from": CHAT, "to": "5511000000000@c.us",
         "fromMe": i % 2 == 1, "timestamp": now - (n - i) * 60}
        for i in range(n)
    ]


@pytest.fixture
def waha():
    client = FakeWahaClient()
    client.fake_chat_list = [{"id": {"_serialized": CHAT}, "name": "Paciente"}]
    return client


def _backfill(record, store, waha, **kw):
    kw.setdefault("days", 36500)
    return run(backfill_connection(record=record, chat_store=store, waha_client=waha, **kw))


def test_backfill_imports_history_without_firing_or_flagging_unread(store, record, waha):
    waha.fake_chat_messages[CHAT] = _history(5)
    report = _backfill(record, store, waha)
    assert (report.status, report.chats_synced, report.messages_inserted) == ("ok", 1, 5)
    chat = store.get_chat(org_id=ORG, connection_id=CONN, chat_id=CHAT)
    assert chat.unread_count == 0 and chat.name == "Paciente"
    assert store.claim_new_chat_notification(org_id=ORG, connection_id=CONN, chat_id=CHAT) is False


def test_backfilled_chat_never_fires_on_a_later_live_message(store, record, waha):
    waha.fake_chat_messages[CHAT] = _history(3)
    _backfill(record, store, waha)
    calls = []

    async def cb(*a):
        calls.append(a)

    run(ingest_waha_event(
        waha_message(mid="live1", ts=int(time.time()) + 60), connection=record, chat_store=store, on_new_chat=cb,
    ))
    assert calls == []
    assert store.get_chat(org_id=ORG, connection_id=CONN, chat_id=CHAT).unread_count == 1


def test_second_run_skips_synced_chats_unless_forced(store, record, waha):
    waha.fake_chat_messages[CHAT] = _history(3)
    _backfill(record, store, waha)
    again = _backfill(record, store, waha)
    forced = _backfill(record, store, waha, force=True)
    assert again.chats_skipped == 1 and again.messages_inserted == 0
    assert forced.chats_skipped == 0 and forced.messages_inserted == 0  # idempotent: UNIQUE dedup


def test_cutoff_drops_old_history(store, record, waha):
    waha.fake_chat_messages[CHAT] = _history(3, now=1_000_000_000)  # 2001
    report = _backfill(record, store, waha, days=90)
    assert report.messages_inserted == 0


def test_noweb_store_disabled_is_reported_not_swallowed(store, record, waha):
    async def boom(limit=50, offset=0):
        raise httpx.HTTPStatusError("bad", request=httpx.Request("GET", "http://w"), response=httpx.Response(400))

    waha.list_chats = boom
    report = _backfill(record, store, waha)
    assert report.status == "noweb_store_required" and "NOWEB" in report.errors[0]


def test_single_flight_per_process(store, record, waha):
    gate = asyncio.Event()

    async def slow_list(limit=50, offset=0):
        await gate.wait()
        return []

    waha.list_chats = slow_list

    async def scenario():
        first = asyncio.create_task(backfill_connection(record=record, chat_store=store, waha_client=waha))
        await asyncio.sleep(0.05)
        assert is_backfill_running(CONN)
        second = await backfill_connection(record=record, chat_store=store, waha_client=waha)
        gate.set()
        return second, await first

    second, first = run(scenario())
    assert second.status == "already_running" and first.status == "ok"
    assert not is_backfill_running(CONN)
    assert "PER PROCESS" in backfill_mod.__doc__


def test_realtime_factory_refuses_silent_in_process_bus():
    with pytest.raises(InboxRealtimeNotConfigured):
        build_inbox_realtime()
    assert build_inbox_realtime(allow_in_process=True).in_process is True
