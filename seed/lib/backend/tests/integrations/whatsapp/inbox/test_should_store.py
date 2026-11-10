"""Pre-store predicate seam on ingest_waha_event + the ready-made shadow-line predicate."""
from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.integrations.whatsapp.inbox import ingest_waha_event, inbound_one_to_one_only

from .conftest import CONN, ORG, waha_message

CHAT = "5511999990001@c.us"


def ingest(record, store, body, **kw):
    return asyncio.run(ingest_waha_event(body, connection=record, chat_store=store, **kw))


class Spy:
    def __init__(self):
        self.messages, self.new_chats = [], []

    async def on_message(self, *a):
        self.messages.append(a)

    async def on_new_chat(self, *a):
        self.new_chats.append(a)


def test_default_stores_everything_including_from_me(store, record):
    assert ingest(record, store, waha_message(mid="m1", from_me=True)).status == "message"


def test_predicate_false_skips_before_anything_is_stored_or_notified(store, record):
    spy = Spy()
    r = ingest(record, store, waha_message(mid="m1"), should_store=lambda m, c: False,
               on_message=spy.on_message, on_new_chat=spy.on_new_chat)
    assert (r.status, r.reason) == ("skipped", "predicate_false")
    assert store.list_messages(org_id=ORG, connection_id=CONN, chat_id=CHAT)[0] == []
    assert spy.messages == [] and spy.new_chats == []


def test_predicate_reason_is_carried_and_true_stores(store, record):
    r = ingest(record, store, waha_message(mid="m1"), should_store=lambda m, c: "nope")
    assert (r.status, r.reason) == ("skipped", "nope")
    assert ingest(record, store, waha_message(mid="m2"), should_store=lambda m, c: True).status == "message"


def test_a_raising_predicate_propagates_fail_closed(store, record):
    def boom(m, c):
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        ingest(record, store, waha_message(mid="m1"), should_store=boom)
    assert store.list_messages(org_id=ORG, connection_id=CONN, chat_id=CHAT)[0] == []


@pytest.mark.parametrize("kwargs,expected", [
    (dict(mid="a"), "message"),
    (dict(mid="b", from_me=True), "from_me"),
    (dict(mid="c", extra={"source": "api"}), "api_sourced"),
    (dict(mid="d", chat="120363000000000001@g.us", extra={"participant": "5511999990001@c.us"}), "group"),
    (dict(mid="e", chat="5511999990009@c.us"), "excluded"),
])
def test_shadow_predicate(store, record, kwargs, expected):
    pred = inbound_one_to_one_only(excluded=["+55 11 99999-0009"])
    r = ingest(record, store, waha_message(**kwargs), should_store=pred)
    assert (r.reason or r.status) == expected


def test_status_broadcast_never_reaches_the_predicate_and_exclusion_hook_decides(store, record):
    assert ingest(record, store, waha_message(mid="s", chat="status@broadcast"),
                  should_store=inbound_one_to_one_only()).status == "ignored"
    hook = lambda m, c: "vip" if "VIP" in m.body else True  # noqa: E731
    pred = inbound_one_to_one_only(exclusion_hook=hook)
    assert ingest(record, store, waha_message(mid="h1", body="VIP hi"), should_store=pred).reason == "vip"
    assert ingest(record, store, waha_message(mid="h2", body="hi"), should_store=pred).status == "message"
