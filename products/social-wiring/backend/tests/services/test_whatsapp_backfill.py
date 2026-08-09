"""Tests for whatsapp_backfill.py — the scheduled WAHA history backfill.

Exercised against a real SQLite-backed client (mirrors
``test_message_store.py``'s convention) so ``MessageStore.record`` +
``WhatsAppChatStore.record_message`` round-trip for real — unlike
``MockSupabaseClient``, whose ``upsert()`` does not propagate writes (see
``test_whatsapp_router.py``'s module docstring for that discovery).

Coverage:
  - ``_extract_waha_id`` / ``_epoch_to_datetime`` — the tiny WAHA-shape
    parsers, unit-tested in isolation.
  - ``_backfill_chat`` — persists within the day cutoff, skips older
    messages, sets the ``synced_through`` watermark correctly for both
    "under the message cap" and "cap hit" cases, degrades (never raises)
    on a WAHA fetch failure, and is idempotent across two runs.
  - ``run_backfill`` — the enable/admin/encryption/no-connections guard
    clauses, the "already-synced chat is skipped" resume gate, and one
    full connection→chats→messages orchestration run via a fake WAHA
    client (monkeypatched ``get_whatsapp_client`` — the standard
    collaborator-substitution shape this suite already uses for
    ``get_whatsapp_bus``).
  - ``configure()`` registers the job on the shared seed scheduler.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from cryptography.fernet import Fernet

from app.services import whatsapp_backfill as backfill
from app.services.message_store import MessageStore
from app.services.whatsapp_chat_store import WhatsAppChatStore
from app.sqlite_client import SQLiteClient
from noctusai_lib.api import scheduler as seed_scheduler

_ORG_ID = UUID("00000000-0000-4000-8000-000000000f01")
_USER_ID = UUID("00000000-0000-4000-8000-000000000f02")
_CONNECTION_ID = UUID("00000000-0000-4000-8000-000000000f03")
_CHAT_ID = "chat-1@c.us"


@pytest.fixture
def sqlite_db(tmp_path: Path) -> SQLiteClient:
    """A fresh SQLite DB carrying whatsapp_connections + conversation_messages
    (incl. the 042_whatsapp_inbox_realtime_schema additions) + whatsapp_chats,
    so MessageStore AND WhatsAppChatStore both round-trip for real. ``id`` on
    whatsapp_chats is a test-only accommodation for SQLiteClient's
    unconditional auto-id-on-insert behavior — the real Postgres table's PK
    is the composite ``(connection_id, chat_id)``, unchanged here."""
    db_path = tmp_path / "backfill_test.sqlite3"
    schema = """
    CREATE TABLE whatsapp_connections (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        label TEXT NOT NULL,
        base_url TEXT NOT NULL,
        session_name TEXT NOT NULL DEFAULT 'default',
        encrypted_api_key TEXT NOT NULL,
        webhook_url TEXT,
        webhook_token TEXT,
        auto_reply_enabled INTEGER NOT NULL DEFAULT 0,
        authorized_numbers TEXT,
        bound_chats TEXT,
        marca_id TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
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
        ack INTEGER,
        acked_at TEXT,
        chat_id TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE whatsapp_chats (
        id TEXT,
        connection_id TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        org_id TEXT NOT NULL,
        title TEXT,
        last_message_at TEXT,
        last_message_preview TEXT,
        last_direction TEXT,
        unread_count INTEGER NOT NULL DEFAULT 0,
        last_read_at TEXT,
        last_read_message_id TEXT,
        archived INTEGER NOT NULL DEFAULT 0,
        pinned INTEGER NOT NULL DEFAULT 0,
        synced_through TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (connection_id, chat_id)
    );
    """
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema)
    return SQLiteClient(db_path)


class _Cfg:
    """Settings stand-in — mirrors meta_ads/test_scheduler.py's ``_Cfg``
    shape (only the fields whatsapp_backfill reads)."""

    def __init__(self, **overrides: Any) -> None:
        self.whatsapp_backfill_enabled = True
        self.whatsapp_backfill_days = 90
        self.whatsapp_backfill_max_messages_per_chat = 500
        self.whatsapp_backfill_chat_limit = 50
        self.encryption_key = Fernet.generate_key().decode()
        self.__dict__.update(overrides)


class _FakeWaha:
    """Duck-typed stand-in for WahaClient/FakeWahaClient — only the two
    methods whatsapp_backfill calls."""

    def __init__(
        self,
        *,
        chats: list[dict[str, Any]] | None = None,
        messages_by_chat: dict[str, list[dict[str, Any]]] | None = None,
        list_chats_error: Exception | None = None,
        fetch_errors: dict[str, Exception] | None = None,
    ) -> None:
        self._chats = chats or []
        self._messages_by_chat = messages_by_chat or {}
        self._list_chats_error = list_chats_error
        self._fetch_errors = fetch_errors or {}
        self.fetch_calls: list[tuple[str, int]] = []

    async def list_chats(self, limit: int = 50) -> list[dict[str, Any]]:
        if self._list_chats_error:
            raise self._list_chats_error
        return self._chats[:limit]

    async def fetch_chat_messages(self, chat_id: str, limit: int = 50) -> list[dict[str, Any]]:
        self.fetch_calls.append((chat_id, limit))
        if chat_id in self._fetch_errors:
            raise self._fetch_errors[chat_id]
        return self._messages_by_chat.get(chat_id, [])[:limit]


def _seed_connection(
    db: SQLiteClient,
    *,
    connection_id: UUID = _CONNECTION_ID,
    org_id: UUID = _ORG_ID,
    user_id: UUID = _USER_ID,
    encryption_key: str,
    base_url: str = "https://waha.example.com",
) -> None:
    fernet = Fernet(encryption_key.encode("utf-8"))
    db.schema("social_wiring").table("whatsapp_connections").insert(
        {
            "id": str(connection_id),
            "org_id": str(org_id),
            "user_id": str(user_id),
            "label": "Test line",
            "base_url": base_url,
            "session_name": "default",
            "encrypted_api_key": fernet.encrypt(b"fake-waha-api-key").decode("ascii"),
            "webhook_token": "tok",
        }
    ).execute()


def _epoch(days_ago: float) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days_ago)).timestamp())


def _waha_message(*, msg_id: str, days_ago: float, body: str = "oi", from_me: bool = False) -> dict[str, Any]:
    return {
        "id": {"_serialized": msg_id, "id": msg_id},
        "body": body,
        "timestamp": _epoch(days_ago),
        "fromMe": from_me,
    }


# ── _extract_waha_id ────────────────────────────────────────────────────

class TestExtractWahaId:
    def test_flat_string(self):
        assert backfill._extract_waha_id("abc123") == "abc123"

    def test_empty_string_is_none(self):
        assert backfill._extract_waha_id("") is None

    def test_dict_with_serialized(self):
        assert backfill._extract_waha_id({"_serialized": "abc", "id": "xyz"}) == "abc"

    def test_dict_with_only_id(self):
        assert backfill._extract_waha_id({"id": "xyz"}) == "xyz"

    def test_none_returns_none(self):
        assert backfill._extract_waha_id(None) is None

    def test_empty_dict_returns_none(self):
        assert backfill._extract_waha_id({}) is None


# ── _epoch_to_datetime ──────────────────────────────────────────────────

class TestEpochToDatetime:
    def test_converts_epoch_seconds(self):
        dt = backfill._epoch_to_datetime(1722700000)
        assert dt is not None
        assert dt.tzinfo is not None

    def test_zero_returns_none(self):
        assert backfill._epoch_to_datetime(0) is None

    def test_none_returns_none(self):
        assert backfill._epoch_to_datetime(None) is None

    def test_garbage_returns_none(self):
        assert backfill._epoch_to_datetime("not-a-number") is None


# ── _backfill_chat ───────────────────────────────────────────────────────

class TestBackfillChat:
    @pytest.mark.asyncio
    async def test_persists_only_messages_within_cutoff(self, sqlite_db):
        message_store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        chat_store = WhatsAppChatStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        waha = _FakeWaha(
            messages_by_chat={
                _CHAT_ID: [
                    _waha_message(msg_id="m-recent", days_ago=1),
                    _waha_message(msg_id="m-old", days_ago=200),  # outside 90d
                ]
            }
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        await backfill._backfill_chat(
            waha_client=waha,
            message_store=message_store,
            chat_store=chat_store,
            connection_id=_CONNECTION_ID,
            chat_id=_CHAT_ID,
            title="Alice",
            cutoff=cutoff,
            max_messages=500,
        )

        rows = message_store.list_for_session(session_id=_CHAT_ID)
        assert {r["provider_message_id"] for r in rows} == {"m-recent"}
        assert rows[0]["chat_id"] == _CHAT_ID
        assert rows[0]["connection_id"] == str(_CONNECTION_ID)

        chat = chat_store.get_chat(connection_id=_CONNECTION_ID, chat_id=_CHAT_ID)
        assert chat is not None
        assert chat.title == "Alice"

    @pytest.mark.asyncio
    async def test_synced_through_is_cutoff_when_under_the_cap(self, sqlite_db):
        message_store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        chat_store = WhatsAppChatStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        waha = _FakeWaha(messages_by_chat={_CHAT_ID: [_waha_message(msg_id="m1", days_ago=1)]})
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        await backfill._backfill_chat(
            waha_client=waha, message_store=message_store, chat_store=chat_store,
            connection_id=_CONNECTION_ID, chat_id=_CHAT_ID, title=None,
            cutoff=cutoff, max_messages=500,
        )

        synced = backfill._get_synced_through(sqlite_db, connection_id=_CONNECTION_ID, chat_id=_CHAT_ID)
        assert synced == cutoff.isoformat()

    @pytest.mark.asyncio
    async def test_synced_through_is_oldest_kept_when_cap_hit(self, sqlite_db):
        """WAHA returned a FULL batch (== max_messages) — there may be
        older history beyond it, so the honest watermark is the oldest
        message actually fetched, not the full day-cutoff."""
        message_store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        chat_store = WhatsAppChatStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        waha = _FakeWaha(
            messages_by_chat={
                _CHAT_ID: [
                    _waha_message(msg_id="cap-1", days_ago=1),
                    _waha_message(msg_id="cap-2", days_ago=2),
                ]
            }
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        await backfill._backfill_chat(
            waha_client=waha, message_store=message_store, chat_store=chat_store,
            connection_id=_CONNECTION_ID, chat_id=_CHAT_ID, title=None,
            cutoff=cutoff, max_messages=2,  # == len(messages) -> cap hit
        )

        synced = backfill._get_synced_through(sqlite_db, connection_id=_CONNECTION_ID, chat_id=_CHAT_ID)
        assert synced != cutoff.isoformat()
        # The oldest of the two persisted messages (days_ago=2).
        oldest_expected = _epoch_to_iso_floor(days_ago=2)
        assert synced.startswith(oldest_expected[:10])  # same calendar day

    @pytest.mark.asyncio
    async def test_waha_fetch_failure_degrades_without_raising(self, sqlite_db):
        message_store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        chat_store = WhatsAppChatStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        waha = _FakeWaha(fetch_errors={_CHAT_ID: RuntimeError("WAHA is down")})
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        # Must not raise.
        await backfill._backfill_chat(
            waha_client=waha, message_store=message_store, chat_store=chat_store,
            connection_id=_CONNECTION_ID, chat_id=_CHAT_ID, title=None,
            cutoff=cutoff, max_messages=500,
        )

        assert message_store.list_for_session(session_id=_CHAT_ID) == []
        # No watermark either — the fetch never succeeded, so there is
        # nothing honest to record as "synced through."
        assert backfill._get_synced_through(sqlite_db, connection_id=_CONNECTION_ID, chat_id=_CHAT_ID) is None

    @pytest.mark.asyncio
    async def test_idempotent_across_two_runs(self, sqlite_db):
        """Re-running a chat's backfill (e.g. a restarted process before
        synced_through was gated at the run_backfill layer) must not
        duplicate rows — DuplicateMessage is caught and skipped."""
        message_store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        chat_store = WhatsAppChatStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        waha = _FakeWaha(messages_by_chat={_CHAT_ID: [_waha_message(msg_id="dup-1", days_ago=1)]})
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        for _ in range(2):
            await backfill._backfill_chat(
                waha_client=waha, message_store=message_store, chat_store=chat_store,
                connection_id=_CONNECTION_ID, chat_id=_CHAT_ID, title=None,
                cutoff=cutoff, max_messages=500,
            )

        rows = message_store.list_for_session(session_id=_CHAT_ID)
        assert len(rows) == 1


def _epoch_to_iso_floor(*, days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


# ── run_backfill ─────────────────────────────────────────────────────────

class TestRunBackfillGuards:
    @pytest.mark.asyncio
    async def test_disabled_never_touches_admin_client(self):
        admin = MagicMock()
        await backfill.run_backfill(cfg=_Cfg(whatsapp_backfill_enabled=False), admin_client=admin)
        admin.schema.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_admin_client_skips(self, monkeypatch):
        monkeypatch.setattr(backfill, "get_admin_client", lambda: None)
        # Must not raise even though admin_client=None forces the
        # get_admin_client() fallback.
        await backfill.run_backfill(cfg=_Cfg(), admin_client=None)

    @pytest.mark.asyncio
    async def test_encryption_not_configured_skips_gracefully(self, sqlite_db):
        # No connections needed — the store can't even be built.
        await backfill.run_backfill(cfg=_Cfg(encryption_key=""), admin_client=sqlite_db)

    @pytest.mark.asyncio
    async def test_no_connections_never_calls_waha(self, sqlite_db, monkeypatch):
        def _boom(**_kwargs):
            raise AssertionError("get_whatsapp_client must not be called with zero connections")

        monkeypatch.setattr(backfill, "get_whatsapp_client", _boom)
        await backfill.run_backfill(cfg=_Cfg(), admin_client=sqlite_db)


class TestRunBackfillOrchestration:
    @pytest.mark.asyncio
    async def test_full_run_persists_and_stamps_watermark(self, sqlite_db, monkeypatch):
        cfg = _Cfg()
        _seed_connection(sqlite_db, encryption_key=cfg.encryption_key)
        waha = _FakeWaha(
            chats=[{"id": {"_serialized": _CHAT_ID}, "name": "Alice"}],
            messages_by_chat={_CHAT_ID: [_waha_message(msg_id="orc-1", days_ago=1)]},
        )
        monkeypatch.setattr(backfill, "get_whatsapp_client", lambda **_kwargs: waha)

        await backfill.run_backfill(cfg=cfg, admin_client=sqlite_db)

        message_store = MessageStore(admin_supabase=sqlite_db, org_id=_ORG_ID)
        rows = message_store.list_for_session(session_id=_CHAT_ID)
        assert {r["provider_message_id"] for r in rows} == {"orc-1"}
        assert waha.fetch_calls == [(_CHAT_ID, cfg.whatsapp_backfill_max_messages_per_chat)]

        synced = backfill._get_synced_through(sqlite_db, connection_id=_CONNECTION_ID, chat_id=_CHAT_ID)
        assert synced is not None

    @pytest.mark.asyncio
    async def test_already_synced_chat_is_skipped_on_the_next_run(self, sqlite_db, monkeypatch):
        cfg = _Cfg()
        _seed_connection(sqlite_db, encryption_key=cfg.encryption_key)
        waha = _FakeWaha(
            chats=[{"id": {"_serialized": _CHAT_ID}, "name": "Alice"}],
            messages_by_chat={_CHAT_ID: [_waha_message(msg_id="resume-1", days_ago=1)]},
        )
        monkeypatch.setattr(backfill, "get_whatsapp_client", lambda **_kwargs: waha)

        await backfill.run_backfill(cfg=cfg, admin_client=sqlite_db)
        assert len(waha.fetch_calls) == 1

        # Second run: the chat now has synced_through set — list_chats still
        # returns it (WAHA doesn't know about our watermark), but
        # fetch_chat_messages must NOT be called again for it.
        await backfill.run_backfill(cfg=cfg, admin_client=sqlite_db)
        assert len(waha.fetch_calls) == 1  # unchanged

    @pytest.mark.asyncio
    async def test_list_chats_failure_for_one_connection_does_not_crash_the_run(
        self, sqlite_db, monkeypatch
    ):
        cfg = _Cfg()
        _seed_connection(sqlite_db, encryption_key=cfg.encryption_key)
        waha = _FakeWaha(list_chats_error=RuntimeError("WAHA session down"))
        monkeypatch.setattr(backfill, "get_whatsapp_client", lambda **_kwargs: waha)

        # Must not raise.
        await backfill.run_backfill(cfg=cfg, admin_client=sqlite_db)


class TestConfigure:
    def test_registers_job_on_seed_scheduler(self):
        seed_scheduler.reset_for_testing()
        try:
            backfill.configure()
            job_names = [j.id for j in seed_scheduler.scheduler.get_jobs()]
            assert "whatsapp_backfill" in job_names
        finally:
            seed_scheduler.reset_for_testing()
