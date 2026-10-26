"""Store contract - runs against the Fake AND the Supabase-backed Real store."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.whatsapp.inbox import (
    InboxMessage,
    InboxStoreNotConfigured,
    build_whatsapp_chat_store,
    whatsapp_chats_table_ddl,
    whatsapp_messages_table_ddl,
)
from noctusai_lib.integrations.whatsapp.inbox.store import decode_cursor

from .conftest import CONN, ORG, OTHER_ORG

CHAT = "5511999990001@c.us"


def _msg(mid: str, ts: str, *, from_me: bool = False, body: str = "oi", chat: str = CHAT, **kw) -> InboxMessage:
    return InboxMessage(
        id=mid, chat_id=chat, from_me=from_me, body=body, type="chat", media_url=None, ack=kw.pop("ack", None),
        timestamp=ts, sender_name=None, **kw,
    )


def _chat(store, chat_id: str = CHAT, origin: str = "inbound", org=ORG):
    return store.ensure_chat(
        org_id=org, connection_id=CONN, chat_id=chat_id, name="Paciente", phone="+5511999990001",
        is_group=chat_id.endswith("@g.us"), origin=origin,
    )


def _add(store, mid: str, ts: str, **kw):
    m = _msg(mid, ts, **kw)
    inserted = store.insert_message(org_id=ORG, connection_id=CONN, message=m)
    store.refresh_chat_after_message(org_id=ORG, connection_id=CONN, chat_id=m.chat_id, message=m)
    return inserted


def test_ensure_chat_creates_once_then_reports_existing(store):
    first = _chat(store)
    again = _chat(store)
    assert first.created is True and again.created is False
    assert again.origin == "inbound"


def test_insert_message_dedups_on_waha_id(store):
    _chat(store)
    assert store.insert_message(org_id=ORG, connection_id=CONN, message=_msg("m1", "2026-10-26T10:00:00+00:00"))
    assert not store.insert_message(org_id=ORG, connection_id=CONN, message=_msg("m1", "2026-10-26T10:00:00+00:00"))
    items, _ = store.list_messages(org_id=ORG, connection_id=CONN, chat_id=CHAT)
    assert [m.id for m in items] == ["m1"]


def test_unread_is_recomputed_not_incremented(store):
    _chat(store)
    _add(store, "m1", "2026-10-26T10:00:00+00:00")
    _add(store, "m2", "2026-10-26T10:01:00+00:00")
    # refreshing again with the SAME message must not drift the badge
    store.refresh_chat_after_message(
        org_id=ORG, connection_id=CONN, chat_id=CHAT, message=_msg("m2", "2026-10-26T10:01:00+00:00")
    )
    assert store.get_chat(org_id=ORG, connection_id=CONN, chat_id=CHAT).unread_count == 2
    _add(store, "m3", "2026-10-26T10:02:00+00:00", from_me=True)
    assert store.get_chat(org_id=ORG, connection_id=CONN, chat_id=CHAT).unread_count == 2  # outbound never unread


def test_mark_read_zeroes_and_later_inbound_counts_again(store):
    _chat(store)
    _add(store, "m1", "2026-10-26T10:00:00+00:00")
    chat = store.mark_read(org_id=ORG, connection_id=CONN, chat_id=CHAT)
    assert chat.unread_count == 0
    assert store.mark_read(org_id=ORG, connection_id=CONN, chat_id="nope@c.us") is None


def test_preview_only_advances_for_newer_messages(store):
    _chat(store)
    _add(store, "new", "2026-10-26T12:00:00+00:00", body="recente")
    _add(store, "old", "2026-10-26T09:00:00+00:00", body="antiga")  # backfill walking backwards
    chat = store.get_chat(org_id=ORG, connection_id=CONN, chat_id=CHAT)
    assert chat.last_message_preview == "recente"
    assert chat.last_message_at.startswith("2026-10-26T12:00:00")


def test_chat_without_messages_is_not_listed(store):
    _chat(store)
    assert store.list_chats(org_id=ORG, connection_id=CONN) == ([], None)


def test_chat_name_never_nameless_and_not_overwritten(store):
    store.ensure_chat(org_id=ORG, connection_id=CONN, chat_id=CHAT, name=None, phone=None, is_group=False, origin="inbound")
    _add(store, "m1", "2026-10-26T10:00:00+00:00")
    assert store.get_chat(org_id=ORG, connection_id=CONN, chat_id=CHAT).name == "5511999990001"
    store.refresh_chat_after_message(
        org_id=ORG, connection_id=CONN, chat_id=CHAT, message=_msg("m1", "2026-10-26T10:00:00+00:00"),
        name="Fulana", phone="+5511999990001",
    )
    store.refresh_chat_after_message(
        org_id=ORG, connection_id=CONN, chat_id=CHAT, message=_msg("m1", "2026-10-26T10:00:00+00:00"), name="Outro",
    )
    chat = store.get_chat(org_id=ORG, connection_id=CONN, chat_id=CHAT)
    assert (chat.name, chat.phone) == ("Fulana", "+5511999990001")


def test_chats_keyset_pagination_survives_timestamp_ties(store):
    ids = [f"55119999900{n:02d}@c.us" for n in range(5)]
    for chat_id in ids:  # identical last_message_at for ALL chats (WAHA has 1s resolution)
        _chat(store, chat_id)
        _add(store, f"m-{chat_id}", "2026-10-26T10:00:00+00:00", chat=chat_id)
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        items, cursor = store.list_chats(org_id=ORG, connection_id=CONN, limit=2, cursor=cursor)
        seen.extend(c.chat_id for c in items)
        if cursor is None:
            break
    assert sorted(seen) == sorted(ids) and len(seen) == 5


def test_messages_keyset_pagination_chronological_pages_with_ties(store):
    _chat(store)
    for n in range(5):  # five messages in the SAME second
        _add(store, f"m{n}", "2026-10-26T10:00:00+00:00")
    _add(store, "m9", "2026-10-26T10:05:00+00:00")
    page1, more1 = store.list_messages(org_id=ORG, connection_id=CONN, chat_id=CHAT, limit=3)
    assert more1 is True and [m.id for m in page1] == ["m3", "m4", "m9"]  # newest 3, oldest->newest
    oldest = page1[0]
    page2, more2 = store.list_messages(
        org_id=ORG, connection_id=CONN, chat_id=CHAT, limit=3, before=f"{oldest.timestamp}|{oldest.id}"
    )
    assert more2 is False and [m.id for m in page2] == ["m0", "m1", "m2"]


def test_search_filters_by_name_or_phone(store):
    _chat(store, CHAT)
    store.ensure_chat(org_id=ORG, connection_id=CONN, chat_id="5521988880002@c.us", name="Beltrano", phone="+5521988880002", is_group=False, origin="inbound")
    _add(store, "a", "2026-10-26T10:00:00+00:00")
    _add(store, "b", "2026-10-26T10:00:01+00:00", chat="5521988880002@c.us")
    by_name, _ = store.list_chats(org_id=ORG, connection_id=CONN, q="belt")
    by_phone, _ = store.list_chats(org_id=ORG, connection_id=CONN, q="999990001")
    assert [c.name for c in by_name] == ["Beltrano"] and [c.name for c in by_phone] == ["Paciente"]


def test_ack_moves_forward_only(store):
    _chat(store)
    _add(store, "m1", "2026-10-26T10:00:00+00:00", from_me=True, ack=1)
    assert store.apply_ack(org_id=ORG, connection_id=CONN, waha_message_id="m1", ack=3).ack == 3
    assert store.apply_ack(org_id=ORG, connection_id=CONN, waha_message_id="m1", ack=2).ack == 3  # out of order
    assert store.apply_ack(org_id=ORG, connection_id=CONN, waha_message_id="ghost", ack=2) is None


def test_org_isolation_on_every_read(store):
    _chat(store)
    _add(store, "m1", "2026-10-26T10:00:00+00:00")
    assert store.list_chats(org_id=OTHER_ORG, connection_id=CONN) == ([], None)
    assert store.list_messages(org_id=OTHER_ORG, connection_id=CONN, chat_id=CHAT) == ([], False)
    assert store.get_chat(org_id=OTHER_ORG, connection_id=CONN, chat_id=CHAT) is None
    assert store.mark_read(org_id=OTHER_ORG, connection_id=CONN, chat_id=CHAT) is None
    assert store.apply_ack(org_id=OTHER_ORG, connection_id=CONN, waha_message_id="m1", ack=3) is None


def test_claim_is_single_winner_and_release_reopens(store):
    _chat(store)
    claim = lambda: store.claim_new_chat_notification(org_id=ORG, connection_id=CONN, chat_id=CHAT)  # noqa: E731
    assert claim() is True and claim() is False
    store.release_new_chat_notification(org_id=ORG, connection_id=CONN, chat_id=CHAT)
    assert claim() is True


@pytest.mark.parametrize("origin,group", [("outbound", False), ("backfill", False), ("inbound", True)])
def test_claim_refused_for_non_eligible_chats(store, origin, group):
    chat_id = "120363@g.us" if group else CHAT
    _chat(store, chat_id, origin=origin)
    assert store.claim_new_chat_notification(org_id=ORG, connection_id=CONN, chat_id=chat_id) is False


def test_backfill_origin_chat_starts_read(store):
    _chat(store, origin="backfill")
    _add(store, "h1", "2020-01-01T10:00:00+00:00")
    assert store.get_chat(org_id=ORG, connection_id=CONN, chat_id=CHAT).unread_count == 0


def test_synced_through_roundtrip(store):
    _chat(store)
    assert store.get_synced_through(org_id=ORG, connection_id=CONN, chat_id=CHAT) is None
    store.set_synced_through(org_id=ORG, connection_id=CONN, chat_id=CHAT, synced_through="2026-07-01T00:00:00+00:00")
    assert store.get_synced_through(org_id=ORG, connection_id=CONN, chat_id=CHAT).startswith("2026-07-01")


def test_bad_cursor_is_a_value_error():
    with pytest.raises(ValueError):
        decode_cursor("not-a-date|x")


def test_factory_refuses_without_client_unless_fake_opted_in():
    with pytest.raises(InboxStoreNotConfigured):
        build_whatsapp_chat_store(None, schema="monica")
    assert build_whatsapp_chat_store(None, schema="monica", allow_fake=True) is not None


def test_ddl_carries_the_load_bearing_constraints():
    chats = whatsapp_chats_table_ddl("monica")
    messages = whatsapp_messages_table_ddl("monica")
    assert "PRIMARY KEY (connection_id, chat_id)" in chats
    assert "REFERENCES monica.whatsapp_connections(id) ON DELETE CASCADE" in chats
    assert "new_chat_notified_at" in chats and "ENABLE ROW LEVEL SECURITY" in chats
    assert "UNIQUE (connection_id, waha_message_id)" in messages
    assert "service_role_bypass" in messages and "current_org_id()" in messages
