"""message_store — durable persistence + UNIQUE-driven dedup oracle.

Covers the seam contract Engineer WHATSAPP (W1.E2) consumes:
``record(...)`` raising :class:`DuplicateMessage` on a repeated
``provider_message_id``. Both the Fake (in-memory dedup) and the Real
(Supabase IntegrityError sniffing) are exercised, plus the factory's
Fake-by-default behaviour.
"""

from uuid import UUID

import pytest

from noctusai_lib.domain.chatbot.message_store import (
    DuplicateMessage,
    FakeMessageStore,
    MessageStore,
    StoredMessage,
    SupabaseMessageStore,
    make_message_store,
)

_ORG = UUID("00000000-0000-4000-8000-000000000001")


# ── Fake ────────────────────────────────────────────────────────────────


def test_fake_records_and_returns_stored_message() -> None:
    store = FakeMessageStore(org_id=_ORG)
    msg = store.record(
        session_id="web:abc",
        direction="inbound",
        body="ola",
        provider_message_id="wamid-1",
    )
    assert isinstance(msg, StoredMessage)
    assert msg.session_id == "web:abc"
    assert msg.direction == "inbound"
    assert msg.provider_message_id == "wamid-1"


def test_fake_duplicate_provider_id_raises() -> None:
    store = FakeMessageStore()
    store.record(
        session_id="s1",
        direction="inbound",
        body="first",
        provider_message_id="wamid-dup",
    )
    with pytest.raises(DuplicateMessage):
        store.record(
            session_id="s1",
            direction="inbound",
            body="second (WAHA message.any race)",
            provider_message_id="wamid-dup",
        )


def test_fake_null_provider_id_never_dedupes() -> None:
    store = FakeMessageStore()
    store.record(session_id="s1", direction="outbound", body="a")
    store.record(session_id="s1", direction="outbound", body="b")
    assert len(store.list_for_session(session_id="s1")) == 2


def test_fake_invalid_direction_rejected() -> None:
    store = FakeMessageStore()
    with pytest.raises(ValueError):
        store.record(session_id="s1", direction="sideways", body="x")


def test_fake_list_for_session_filters_and_limits() -> None:
    store = FakeMessageStore()
    store.record(session_id="s1", direction="inbound", body="1")
    store.record(session_id="s2", direction="inbound", body="2")
    store.record(session_id="s1", direction="outbound", body="3")
    rows = store.list_for_session(session_id="s1")
    assert [r["body"] for r in rows] == ["1", "3"]
    assert store.list_for_session(session_id="s1", limit=1) == [rows[0]]


def test_fake_satisfies_protocol() -> None:
    assert isinstance(FakeMessageStore(), MessageStore)


# ── Real (Supabase) ─────────────────────────────────────────────────────


class _RaisingInsertClient:
    """Minimal Supabase-shaped client whose insert raises a SQLite-style
    IntegrityError so the duplicate-sniffing path is exercised without a
    live DB. Mirrors the cross-backend message the Real adapter sniffs."""

    def __init__(self, *, raise_on_insert: bool) -> None:
        self._raise = raise_on_insert
        self._payload: dict | None = None
        self._mode = "select"

    def schema(self, _name):
        return self

    def table(self, _name):
        return self

    def insert(self, payload):
        self._payload = payload
        self._mode = "insert"
        return self

    def select(self, *_a, **_k):
        self._mode = "select"
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        if self._mode == "insert" and self._raise:
            raise Exception(
                "UNIQUE constraint failed: "
                "conversation_messages.provider_message_id"
            )

        class _R:
            pass

        r = _R()
        # insert → echo payload; select existence-check → empty (so the
        # message-sniff branch is what triggers DuplicateMessage).
        r.data = [self._payload] if self._mode == "insert" else []
        return r


def test_supabase_record_happy_path() -> None:
    store = SupabaseMessageStore(
        admin_supabase=_RaisingInsertClient(raise_on_insert=False),
        org_id=_ORG,
        schema="social_wiring",
    )
    msg = store.record(
        session_id="5511999@c.us",
        direction="outbound",
        body="reply",
        provider_message_id="wamid-x",
    )
    assert msg.session_id == "5511999@c.us"
    assert msg.direction == "outbound"


def test_supabase_unique_violation_raises_duplicate_message() -> None:
    store = SupabaseMessageStore(
        admin_supabase=_RaisingInsertClient(raise_on_insert=True),
        org_id=_ORG,
        schema="social_wiring",
    )
    with pytest.raises(DuplicateMessage):
        store.record(
            session_id="s1",
            direction="inbound",
            body="dup",
            provider_message_id="wamid-dup",
        )


def test_supabase_satisfies_protocol() -> None:
    store = SupabaseMessageStore(
        admin_supabase=_RaisingInsertClient(raise_on_insert=False),
        org_id=_ORG,
        schema="s",
    )
    assert isinstance(store, MessageStore)


# ── Factory ─────────────────────────────────────────────────────────────


def test_factory_returns_fake_by_default() -> None:
    assert isinstance(make_message_store(use_fake=True), FakeMessageStore)
    # No admin/schema → Fake.
    assert isinstance(make_message_store(), FakeMessageStore)


def test_factory_returns_real_when_wired() -> None:
    store = make_message_store(
        admin_supabase=_RaisingInsertClient(raise_on_insert=False),
        org_id=_ORG,
        schema="social_wiring",
    )
    assert isinstance(store, SupabaseMessageStore)
