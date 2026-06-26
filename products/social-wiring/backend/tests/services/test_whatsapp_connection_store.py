"""Tests for WhatsAppConnectionStore — per-user WAHA connection "lines".

Exercised against a REAL SQLite client (mirrors test_message_store.py) so the
test catches the actual write→read propagation + UNIQUE constraint, plus a
REAL Fernet round-trip so the at-rest encryption is genuinely verified (the
api_key is never stored in cleartext, and a key mismatch fails loud).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from app.services.credential_vault import (
    CredentialStoreError,
    EncryptionNotConfigured,
)
from app.services.whatsapp_connection_store import (
    WhatsAppConnectionStore,
    build_whatsapp_connection_store,
)
from app.sqlite_client import SQLiteClient

_ORG = UUID("00000000-0000-4000-8000-000000000001")
_USER = UUID("00000000-0000-4000-8000-0000000000aa")
_OTHER_USER = UUID("00000000-0000-4000-8000-0000000000bb")

_SCHEMA = """
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
    authorized_numbers TEXT NOT NULL DEFAULT '[]',
    bound_chats TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (org_id, user_id, label),
    UNIQUE (webhook_token)
);
"""


@pytest.fixture
def sqlite_db(tmp_path: Path) -> SQLiteClient:
    db_path = tmp_path / "conn.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
    return SQLiteClient(db_path)


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def store(sqlite_db: SQLiteClient, fernet_key: str) -> WhatsAppConnectionStore:
    return WhatsAppConnectionStore(sqlite_db, fernet=Fernet(fernet_key.encode("utf-8")))


def _make(store: WhatsAppConnectionStore, *, label="Atendimento SP", api_key="waha-secret", **kw):
    return store.create_connection(
        org_id=_ORG, user_id=_USER, label=label, base_url=kw.pop("base_url", "https://waha.example.com/"),
        api_key=api_key, **kw,
    )


class TestCreate:
    def test_returns_record_with_normalized_fields(self, store):
        rec = _make(store, base_url="https://waha.example.com/")
        assert isinstance(rec.id, UUID)
        assert rec.label == "Atendimento SP"
        assert rec.base_url == "https://waha.example.com"  # trailing slash stripped
        assert rec.session_name == "default"
        # The plaintext key never rides the create response.
        assert rec.api_key is None

    def test_api_key_encrypted_at_rest(self, store, sqlite_db):
        _make(store, api_key="super-secret-key")
        row = sqlite_db.table("whatsapp_connections").select("*").execute().data[0]
        assert "super-secret-key" not in row["encrypted_api_key"]
        assert row["encrypted_api_key"]  # something IS stored


class TestGetAndDecrypt:
    def test_get_without_decrypt_hides_key(self, store):
        rec = _make(store)
        got = store.get_connection(connection_id=rec.id, org_id=_ORG, user_id=_USER)
        assert got is not None and got.api_key is None

    def test_get_with_decrypt_round_trips_key(self, store):
        rec = _make(store, api_key="round-trip-me")
        got = store.get_connection(
            connection_id=rec.id, org_id=_ORG, user_id=_USER, decrypt=True
        )
        assert got is not None and got.api_key == "round-trip-me"

    def test_key_mismatch_fails_loud(self, sqlite_db, store):
        rec = _make(store, api_key="k")
        other = WhatsAppConnectionStore(sqlite_db, fernet=Fernet(Fernet.generate_key()))
        with pytest.raises(CredentialStoreError):
            other.get_connection(
                connection_id=rec.id, org_id=_ORG, user_id=_USER, decrypt=True
            )


class TestOwnerIsolation:
    def test_other_user_cannot_see_or_get(self, store):
        rec = _make(store)
        assert store.list_connections(org_id=_ORG, user_id=_OTHER_USER) == []
        assert store.get_connection(
            connection_id=rec.id, org_id=_ORG, user_id=_OTHER_USER
        ) is None

    def test_other_user_cannot_delete(self, store):
        rec = _make(store)
        assert store.delete_connection(
            connection_id=rec.id, org_id=_ORG, user_id=_OTHER_USER
        ) is False
        # Still there for the owner.
        assert store.get_connection(connection_id=rec.id, org_id=_ORG, user_id=_USER)


class TestListUpdateDelete:
    def test_list_returns_owner_rows(self, store):
        _make(store, label="A")
        _make(store, label="B")
        rows = store.list_connections(org_id=_ORG, user_id=_USER)
        assert {r.label for r in rows} == {"A", "B"}
        assert all(r.api_key is None for r in rows)

    def test_update_rotates_key_and_label(self, store):
        rec = _make(store, label="Old", api_key="old-key")
        updated = store.update_connection(
            connection_id=rec.id, org_id=_ORG, user_id=_USER,
            label="New", api_key="new-key",
        )
        assert updated is not None and updated.label == "New"
        got = store.get_connection(
            connection_id=rec.id, org_id=_ORG, user_id=_USER, decrypt=True
        )
        assert got.api_key == "new-key"

    def test_update_can_set_webhook(self, store):
        rec = _make(store)
        store.update_connection(
            connection_id=rec.id, org_id=_ORG, user_id=_USER,
            webhook_url="https://app/webhook",
        )
        got = store.get_connection(connection_id=rec.id, org_id=_ORG, user_id=_USER)
        assert got.webhook_url == "https://app/webhook"

    def test_delete_is_idempotent(self, store):
        rec = _make(store)
        assert store.delete_connection(
            connection_id=rec.id, org_id=_ORG, user_id=_USER
        ) is True
        assert store.delete_connection(
            connection_id=rec.id, org_id=_ORG, user_id=_USER
        ) is False
        assert store.get_connection(
            connection_id=rec.id, org_id=_ORG, user_id=_USER
        ) is None

    def test_update_unknown_returns_none(self, store):
        assert store.update_connection(
            connection_id=uuid4(), org_id=_ORG, user_id=_USER, label="x"
        ) is None


class TestWebhookToken:
    def test_create_stores_webhook_token(self, store):
        rec = _make(store, webhook_token="tok-abc123")
        got = store.get_connection(connection_id=rec.id, org_id=_ORG, user_id=_USER)
        assert got is not None
        assert got.webhook_token == "tok-abc123"

    def test_get_by_webhook_token_found(self, store):
        rec = _make(store, webhook_token="tok-xyz789")
        found = store.get_by_webhook_token("tok-xyz789")
        assert found is not None
        assert found.id == rec.id
        assert found.label == rec.label

    def test_get_by_webhook_token_unknown(self, store):
        _make(store, webhook_token="tok-known")
        assert store.get_by_webhook_token("tok-unknown") is None

    def test_get_by_webhook_token_no_api_key_exposed(self, store):
        """Token lookup never decrypts the API key (service-role path)."""
        _make(store, api_key="secret-key", webhook_token="tok-safe")
        found = store.get_by_webhook_token("tok-safe")
        assert found is not None
        assert found.api_key is None


class TestFactory:
    def test_empty_key_raises(self, sqlite_db):
        with pytest.raises(EncryptionNotConfigured):
            build_whatsapp_connection_store(sqlite_db, encryption_key="")

    def test_malformed_key_raises(self, sqlite_db):
        with pytest.raises(EncryptionNotConfigured):
            build_whatsapp_connection_store(sqlite_db, encryption_key="not-a-fernet-key")

    def test_valid_key_builds(self, sqlite_db, fernet_key):
        store = build_whatsapp_connection_store(sqlite_db, encryption_key=fernet_key)
        assert isinstance(store, WhatsAppConnectionStore)


class TestConnectionSettings:
    """Migration 016 — authorized_numbers + bound_chats per-connection config."""

    def test_defaults_are_empty_lists(self, store):
        rec = _make(store)
        assert rec.authorized_numbers == []
        assert rec.bound_chats == []

    def test_update_authorized_numbers_stores_and_round_trips(self, store):
        rec = _make(store)
        updated = store.update_connection(
            connection_id=rec.id,
            org_id=_ORG,
            user_id=_USER,
            authorized_numbers=["+5511999887766", "+5521988776655"],
        )
        assert updated is not None
        assert updated.authorized_numbers == ["+5511999887766", "+5521988776655"]
        # Verify persistence round-trip via fresh get.
        got = store.get_connection(connection_id=rec.id, org_id=_ORG, user_id=_USER)
        assert got is not None
        assert got.authorized_numbers == ["+5511999887766", "+5521988776655"]

    def test_update_bound_chats_stores_and_round_trips(self, store):
        rec = _make(store)
        chats = [
            {"chat_id": "5511999887766@c.us", "label": "Vendas"},
            {"chat_id": "5521988776655@c.us", "label": ""},
        ]
        updated = store.update_connection(
            connection_id=rec.id,
            org_id=_ORG,
            user_id=_USER,
            bound_chats=chats,
        )
        assert updated is not None
        assert updated.bound_chats == chats
        got = store.get_connection(connection_id=rec.id, org_id=_ORG, user_id=_USER)
        assert got is not None
        assert got.bound_chats == chats

    def test_clear_authorized_numbers_with_empty_list(self, store):
        """Empty list = 'allow all', NOT disabled. Must persist as []."""
        rec = _make(store)
        store.update_connection(
            connection_id=rec.id,
            org_id=_ORG,
            user_id=_USER,
            authorized_numbers=["+5511999887766"],
        )
        # Now clear with explicit [].
        updated = store.update_connection(
            connection_id=rec.id,
            org_id=_ORG,
            user_id=_USER,
            authorized_numbers=[],
        )
        assert updated is not None
        assert updated.authorized_numbers == []

    def test_omitting_field_does_not_overwrite_existing(self, store):
        """_UNSET sentinel: update with no authorized_numbers kwarg keeps current value."""
        rec = _make(store)
        store.update_connection(
            connection_id=rec.id,
            org_id=_ORG,
            user_id=_USER,
            authorized_numbers=["+5511999887766"],
        )
        # Patch only the label — authorized_numbers must stay.
        store.update_connection(
            connection_id=rec.id,
            org_id=_ORG,
            user_id=_USER,
            label="Updated Label",
        )
        got = store.get_connection(connection_id=rec.id, org_id=_ORG, user_id=_USER)
        assert got is not None
        assert got.authorized_numbers == ["+5511999887766"]
        assert got.label == "Updated Label"

    def test_record_with_missing_columns_degrades_gracefully(self, sqlite_db, fernet_key):
        """Un-migrated DB rows (no authorized_numbers / bound_chats column)
        must produce empty lists, not KeyError / AttributeError."""
        from cryptography.fernet import Fernet as _Fernet
        store = WhatsAppConnectionStore(sqlite_db, fernet=_Fernet(fernet_key.encode("utf-8")))
        # Simulate a row that pre-dates migration 016 (lacks the new columns).
        row = {
            "id": str(__import__("uuid").uuid4()),
            "org_id": str(_ORG),
            "user_id": str(_USER),
            "label": "Legacy",
            "base_url": "https://waha.example.com",
            "session_name": "default",
            "encrypted_api_key": "ignored",
            "webhook_url": None,
            "webhook_token": None,
            "auto_reply_enabled": False,
            "created_at": None,
            "updated_at": None,
            # authorized_numbers and bound_chats are intentionally absent.
        }
        rec = WhatsAppConnectionStore._record(row)
        assert rec.authorized_numbers == []
        assert rec.bound_chats == []
