"""Tests for MailchimpConnectionStore.

Real SQLite + real Fernet — exercises CRUD + encryption round-trip.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from app.modules.mailchimp.store import MailchimpConnectionStore, build_mailchimp_connection_store
from app.services.credential_vault import EncryptionNotConfigured
from app.sqlite_client import SQLiteClient

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mailchimp_connections (
    id            TEXT PRIMARY KEY,
    org_id        TEXT NOT NULL,
    client_id     TEXT,
    encrypted_api_key TEXT NOT NULL,
    server_prefix TEXT NOT NULL,
    audience_id   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Mirror migration 019: at-most-one-per-scope via two partial unique indexes.
CREATE UNIQUE INDEX IF NOT EXISTS ux_mc_conn_org_default
    ON mailchimp_connections (org_id) WHERE client_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_mc_conn_org_client
    ON mailchimp_connections (org_id, client_id) WHERE client_id IS NOT NULL;
"""


@pytest.fixture
def store_and_db(tmp_path: Path):
    db_path = tmp_path / "mc_store.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
    key = Fernet.generate_key()
    store = MailchimpConnectionStore(SQLiteClient(db_path), fernet=Fernet(key))
    return store, db_path


class TestStoreEncryption:
    def test_fernet_round_trip(self, store_and_db):
        """Stored ciphertext != plaintext; decryption returns original key."""
        store, db_path = store_and_db
        org_id = uuid4()
        store.upsert_connection(org_id=org_id, api_key="mykey-us6", server_prefix="us6")

        # Read raw ciphertext from SQLite to confirm it is not plaintext
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT encrypted_api_key FROM mailchimp_connections WHERE org_id = ?",
                [str(org_id)],
            ).fetchone()
        assert row is not None
        assert "mykey-us6" not in row[0], "API key must not be stored as plaintext"

        # Decrypt via the store
        record = store.get_connection(org_id, decrypt=True)
        assert record is not None
        assert record.api_key == "mykey-us6"

    def test_api_key_absent_by_default(self, store_and_db):
        """get_connection without decrypt=True returns api_key=None."""
        store, _ = store_and_db
        org_id = uuid4()
        store.upsert_connection(org_id=org_id, api_key="secret-us6", server_prefix="us6")
        record = store.get_connection(org_id)
        assert record is not None
        assert record.api_key is None


class TestStoreCrud:
    def test_upsert_then_get(self, store_and_db):
        store, _ = store_and_db
        org_id = uuid4()
        record = store.upsert_connection(
            org_id=org_id,
            api_key="k-us6",
            server_prefix="us6",
            audience_id="aud1",
        )
        assert record.server_prefix == "us6"
        assert record.audience_id == "aud1"
        assert record.api_key is None  # not decrypted by upsert

        got = store.get_connection(org_id)
        assert got is not None
        assert got.server_prefix == "us6"
        assert got.audience_id == "aud1"

    def test_upsert_replaces_existing(self, store_and_db):
        """Second upsert with the same org_id replaces the row."""
        store, _ = store_and_db
        org_id = uuid4()
        store.upsert_connection(org_id=org_id, api_key="k1-us6", server_prefix="us6")
        store.upsert_connection(org_id=org_id, api_key="k2-eu1", server_prefix="eu1")

        record = store.get_connection(org_id, decrypt=True)
        assert record.server_prefix == "eu1"
        assert record.api_key == "k2-eu1"

    def test_set_audience(self, store_and_db):
        store, _ = store_and_db
        org_id = uuid4()
        store.upsert_connection(org_id=org_id, api_key="k-us6", server_prefix="us6")
        updated = store.set_audience(org_id, "aud-new")
        assert updated is not None
        assert updated.audience_id == "aud-new"

    def test_delete(self, store_and_db):
        store, _ = store_and_db
        org_id = uuid4()
        store.upsert_connection(org_id=org_id, api_key="k-us6", server_prefix="us6")
        deleted = store.delete_connection(org_id)
        assert deleted is True
        assert store.get_connection(org_id) is None

    def test_delete_missing_returns_false(self, store_and_db):
        store, _ = store_and_db
        assert store.delete_connection(uuid4()) is False

    def test_get_missing_returns_none(self, store_and_db):
        store, _ = store_and_db
        assert store.get_connection(uuid4()) is None


class TestPerClienteScope:
    """Migration 019 — scope = (org_id, client_id)."""

    def test_org_default_and_cliente_are_distinct_rows(self, store_and_db):
        """An org-default (client_id NULL) and a per-cliente connection coexist."""
        store, _ = store_and_db
        org_id = uuid4()
        client_id = uuid4()
        store.upsert_connection(
            org_id=org_id, api_key="org-us6", server_prefix="us6", audience_id="aud-org"
        )
        store.upsert_connection(
            org_id=org_id,
            api_key="cli-eu1",
            server_prefix="eu1",
            audience_id="aud-cli",
            client_id=client_id,
        )
        default = store.get_connection(org_id)
        scoped = store.get_connection(org_id, client_id=client_id)
        assert default is not None and default.client_id is None
        assert default.server_prefix == "us6"
        assert default.audience_id == "aud-org"
        assert scoped is not None and scoped.client_id == client_id
        assert scoped.server_prefix == "eu1"
        assert scoped.audience_id == "aud-cli"

    def test_downstream_get_connection_resolves_org_default(self, store_and_db):
        """(e) The no-client_id path (deps/require_mailchimp_client) resolves the
        org-default even when a per-cliente connection also exists."""
        store, _ = store_and_db
        org_id = uuid4()
        client_id = uuid4()
        store.upsert_connection(
            org_id=org_id, api_key="org-us6", server_prefix="us6", audience_id="aud-org"
        )
        store.upsert_connection(
            org_id=org_id, api_key="cli-eu1", server_prefix="eu1", client_id=client_id
        )
        # Mirrors deps.require_mailchimp_client: get_connection(org_id, decrypt=True).
        record = store.get_connection(org_id, decrypt=True)
        assert record is not None
        assert record.client_id is None
        assert record.api_key == "org-us6"
        assert record.server_prefix == "us6"

    def test_upsert_idempotent_per_scope(self, store_and_db):
        """(d) Re-upserting the same (org, client_id) replaces the row in place."""
        store, _ = store_and_db
        org_id = uuid4()
        client_id = uuid4()
        first = store.upsert_connection(
            org_id=org_id, api_key="k1-us6", server_prefix="us6", client_id=client_id
        )
        second = store.upsert_connection(
            org_id=org_id, api_key="k2-eu1", server_prefix="eu1", client_id=client_id
        )
        assert first.id == second.id  # same row, not a duplicate
        got = store.get_connection(org_id, client_id=client_id, decrypt=True)
        assert got.server_prefix == "eu1"
        assert got.api_key == "k2-eu1"

    def test_scoped_get_missing_returns_none(self, store_and_db):
        """A cliente scope with no row returns None even if an org-default exists."""
        store, _ = store_and_db
        org_id = uuid4()
        store.upsert_connection(org_id=org_id, api_key="org-us6", server_prefix="us6")
        assert store.get_connection(org_id, client_id=uuid4()) is None

    def test_set_audience_scoped(self, store_and_db):
        """set_audience targets the scoped row, leaving the org-default untouched."""
        store, _ = store_and_db
        org_id = uuid4()
        client_id = uuid4()
        store.upsert_connection(
            org_id=org_id, api_key="org-us6", server_prefix="us6", audience_id="aud-org"
        )
        store.upsert_connection(
            org_id=org_id, api_key="cli-us6", server_prefix="us6", client_id=client_id
        )
        updated = store.set_audience(org_id, "aud-cli-new", client_id=client_id)
        assert updated is not None and updated.audience_id == "aud-cli-new"
        # Org-default unchanged.
        assert store.get_connection(org_id).audience_id == "aud-org"

    def test_delete_scoped_leaves_org_default(self, store_and_db):
        """delete_connection scoped to a cliente leaves the org-default alive."""
        store, _ = store_and_db
        org_id = uuid4()
        client_id = uuid4()
        store.upsert_connection(org_id=org_id, api_key="org-us6", server_prefix="us6")
        store.upsert_connection(
            org_id=org_id, api_key="cli-us6", server_prefix="us6", client_id=client_id
        )
        assert store.delete_connection(org_id, client_id=client_id) is True
        assert store.get_connection(org_id, client_id=client_id) is None
        assert store.get_connection(org_id) is not None  # org-default survives


class TestBuildStoreValidation:
    def test_missing_key_raises_503_friendly(self):
        """build_mailchimp_connection_store raises EncryptionNotConfigured on empty key."""
        from unittest.mock import MagicMock
        with pytest.raises(EncryptionNotConfigured):
            build_mailchimp_connection_store(MagicMock(), encryption_key="")

    def test_invalid_key_raises_503_friendly(self):
        from unittest.mock import MagicMock
        with pytest.raises(EncryptionNotConfigured):
            build_mailchimp_connection_store(MagicMock(), encryption_key="notafernetkey")
