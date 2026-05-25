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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (org_id, user_id, label)
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
