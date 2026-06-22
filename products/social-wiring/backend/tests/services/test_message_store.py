"""Tests for MessageStore — the durable audit log + idempotency oracle.

The most important behavior is DuplicateMessage on a second insert with
the same provider_message_id, since that's what WhatsApp's
message + message.any race relies on. We exercise it against the real
SQLite client so the test catches both the schema constraint AND the
service's exception detection.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.services.message_store import (
    DuplicateMessage,
    MessageStore,
    StoredMessage,
)
from app.sqlite_client import SQLiteClient


_ORG_ID = UUID("00000000-0000-4000-8000-000000000001")


@pytest.fixture
def sqlite_db(tmp_path: Path) -> SQLiteClient:
    """Build a fresh SQLite DB with the conversation_messages schema for
    each test. We replay the actual schema fragment from
    apply_sqlite_migrations.py to keep the test honest about the live
    UNIQUE constraint shape."""
    import sqlite3

    db_path = tmp_path / "test.sqlite3"
    schema = """
    CREATE TABLE conversation_messages (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        raw_sender TEXT,
        direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
        provider_message_id TEXT UNIQUE,
        body TEXT NOT NULL,
        authorized INTEGER NOT NULL DEFAULT 0,
        structured_payload TEXT,
        connection_id TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_session ON conversation_messages(session_id, created_at DESC);
    """
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema)
    return SQLiteClient(db_path)


class TestRecord:
    def test_inserts_inbound(self, sqlite_db):
        store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        msg = store.record(
            session_id="+5511974693365",
            direction="inbound",
            body="oi",
            provider_message_id="false_xyz_001",
            raw_sender="33613018058989@lid",
            authorized=True,
        )
        assert isinstance(msg, StoredMessage)
        assert msg.session_id == "+5511974693365"
        assert msg.direction == "inbound"
        assert msg.body == "oi"
        assert msg.provider_message_id == "false_xyz_001"
        assert msg.authorized is True

    def test_inserts_outbound(self, sqlite_db):
        store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        msg = store.record(
            session_id="+5511974693365",
            direction="outbound",
            body="oi de volta!",
            provider_message_id="true_xyz_002",
        )
        assert msg.direction == "outbound"
        assert msg.body == "oi de volta!"

    def test_invalid_direction_rejected(self, sqlite_db):
        store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        with pytest.raises(ValueError):
            store.record(
                session_id="+5511974693365",
                direction="sideways",
                body="huh",
            )


class TestDedup:
    def test_duplicate_provider_message_id_raises(self, sqlite_db):
        """The whole point: same provider_message_id twice → DuplicateMessage.

        Mirrors the message + message.any race WAHA puts us through.
        Both events carry the same id; the second insert trips the
        UNIQUE constraint."""
        store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        store.record(
            session_id="+5511974693365",
            direction="inbound",
            body="oi",
            provider_message_id="false_DUPLICATE_001",
        )
        with pytest.raises(DuplicateMessage):
            store.record(
                session_id="+5511974693365",
                direction="inbound",
                body="oi",
                provider_message_id="false_DUPLICATE_001",
            )

    def test_null_provider_message_id_does_not_dedup(self, sqlite_db):
        """SQL treats multiple NULLs as distinct, so outbound surfaces
        without an id can stack. Important: don't accidentally dedup
        outbound test sends that have no id."""
        store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        msg_a = store.record(
            session_id="+5511974693365",
            direction="outbound",
            body="first",
            provider_message_id=None,
        )
        msg_b = store.record(
            session_id="+5511974693365",
            direction="outbound",
            body="second",
            provider_message_id=None,
        )
        assert msg_a.id != msg_b.id

    def test_different_provider_message_ids_both_insert(self, sqlite_db):
        store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        store.record(
            session_id="+5511974693365",
            direction="inbound",
            body="a",
            provider_message_id="ID_A",
        )
        store.record(
            session_id="+5511974693365",
            direction="inbound",
            body="b",
            provider_message_id="ID_B",
        )
        rows = store.list_for_session(session_id="+5511974693365")
        assert len(rows) == 2


class TestListForSession:
    def test_returns_all_messages_for_session(self, sqlite_db):
        # In production, real messages are spaced out by seconds so
        # ``created_at`` orders cleanly. In a fast test loop, multiple
        # inserts can land within the same second-precision timestamp,
        # making the relative order non-deterministic. Assert
        # set-equality rather than sequence — the relevant property is
        # "all session messages are returned", and order is a property
        # of the real-world cadence.
        store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        store.record(session_id="s1", direction="inbound", body="first", provider_message_id="A")
        store.record(session_id="s1", direction="outbound", body="second", provider_message_id="B")
        store.record(session_id="s1", direction="inbound", body="third", provider_message_id="C")
        rows = store.list_for_session(session_id="s1")
        assert {r["body"] for r in rows} == {"first", "second", "third"}

    def test_filters_by_session(self, sqlite_db):
        store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        store.record(session_id="s1", direction="inbound", body="from-s1", provider_message_id="A")
        store.record(session_id="s2", direction="inbound", body="from-s2", provider_message_id="B")
        s1_rows = store.list_for_session(session_id="s1")
        s2_rows = store.list_for_session(session_id="s2")
        assert len(s1_rows) == 1
        assert s1_rows[0]["body"] == "from-s1"
        assert len(s2_rows) == 1
        assert s2_rows[0]["body"] == "from-s2"

    def test_respects_limit(self, sqlite_db):
        store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        for i in range(5):
            store.record(
                session_id="s1",
                direction="inbound",
                body=f"msg-{i}",
                provider_message_id=f"id-{i}",
            )
        rows = store.list_for_session(session_id="s1", limit=2)
        assert len(rows) == 2
