"""Tests for IntegrationAccountService — per-org multi-account credentials.

Exercised against a REAL SQLite client so the tests catch actual write→read
propagation, UNIQUE constraints, and Fernet round-trips.

Design goals:
  - Encryption: stored value is NOT plaintext; decryption returns original dict.
  - is_default constraint: only one default per (org, provider) at any time.
  - RLS isolation: org A cannot see org B's accounts.
  - CRUD round-trips: create → list → get → update → delete.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from app.services.credential_vault import CredentialStoreError, EncryptionNotConfigured
from app.services.integration_account_service import (
    IntegrationAccount,
    IntegrationAccountNotFound,
    IntegrationAccountService,
    build_integration_account_service,
)
from app.sqlite_client import SQLiteClient

_ORG_A = UUID("00000000-0000-4000-8000-000000000001")
_ORG_B = UUID("00000000-0000-4000-8000-000000000002")

# SQLite schema mirrors the Supabase DDL (migration 008 extended columns
# — without BYTEA; SQLite uses TEXT/BLOB).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS integration_accounts (
    id                  TEXT PRIMARY KEY,
    org_id              TEXT NOT NULL,
    provider            TEXT NOT NULL CHECK (provider IN ('youtube', 'google_drive', 'gmail', 'meta', 'n8n')),
    account_label       TEXT NOT NULL,
    encrypted_credential TEXT NOT NULL,
    metadata            TEXT NOT NULL DEFAULT '{}',
    is_default          INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    client_id           TEXT,
    status              TEXT NOT NULL DEFAULT 'validated',
    channel_info        TEXT NOT NULL DEFAULT '{}',
    last_synced_at      TEXT,
    UNIQUE (org_id, provider, account_label)
);
"""


@pytest.fixture
def sqlite_db(tmp_path: Path) -> SQLiteClient:
    db_path = tmp_path / "ia.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
    return SQLiteClient(db_path)


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def svc(sqlite_db: SQLiteClient, fernet_key: str) -> IntegrationAccountService:
    return IntegrationAccountService(sqlite_db, fernet=Fernet(fernet_key.encode("utf-8")))


# ─── Helper ──────────────────────────────────────────────────────────────────
def _cred() -> dict:
    return {"access_token": "tok-abc", "refresh_token": "ref-xyz", "scopes": ["youtube.upload"]}


def _make(
    svc: IntegrationAccountService,
    *,
    org_id=_ORG_A,
    provider="youtube",
    label="Personal YouTube",
    credential=None,
    metadata=None,
    is_default=False,
) -> IntegrationAccount:
    return svc.create_account(
        org_id=org_id,
        provider=provider,
        account_label=label,
        credential_dict=credential or _cred(),
        metadata=metadata or {"channel_id": "UC123"},
        is_default=is_default,
    )


# ─── create ──────────────────────────────────────────────────────────────────
class TestCreate:
    def test_returns_integration_account(self, svc):
        acct = _make(svc)
        assert isinstance(acct, IntegrationAccount)
        assert acct.provider == "youtube"
        assert acct.account_label == "Personal YouTube"
        assert acct.org_id == _ORG_A
        assert isinstance(acct.id, UUID)

    def test_credential_not_in_metadata(self, svc):
        """Plaintext credential must never appear in the returned DTO."""
        acct = _make(svc)
        # The DTO has no credential field at all.
        assert not hasattr(acct, "credential")
        assert not hasattr(acct, "encrypted_credential")

    def test_encryption_roundtrip(self, svc):
        """Stored value is Fernet ciphertext; decrypt returns original dict."""
        cred = _cred()
        acct = _make(svc, credential=cred)
        # Direct DB read must show ciphertext, not plaintext JSON.
        raw = svc._table().select("encrypted_credential").eq("id", str(acct.id)).execute()
        stored = raw.data[0]["encrypted_credential"]
        # Must NOT contain the plaintext access_token.
        assert "tok-abc" not in str(stored)
        # Must decrypt back to the original dict.
        decrypted = svc.decrypt_credential(acct.id, _ORG_A)
        assert decrypted == cred

    def test_metadata_stored(self, svc):
        acct = _make(svc, metadata={"channel_id": "UC999", "channel_title": "My Channel"})
        assert acct.metadata["channel_id"] == "UC999"
        assert acct.metadata["channel_title"] == "My Channel"

    def test_is_default_false_by_default(self, svc):
        acct = _make(svc)
        assert acct.is_default is False

    def test_is_default_true(self, svc):
        acct = _make(svc, is_default=True)
        assert acct.is_default is True


# ─── list / get ──────────────────────────────────────────────────────────────
class TestListGet:
    def test_list_all(self, svc):
        _make(svc, label="A")
        _make(svc, label="B", provider="meta")
        accounts = svc.list_accounts(org_id=_ORG_A)
        assert len(accounts) == 2

    def test_list_filtered_by_provider(self, svc):
        _make(svc, label="A", provider="youtube")
        _make(svc, label="B", provider="meta")
        yt = svc.list_accounts(org_id=_ORG_A, provider="youtube")
        assert len(yt) == 1
        assert yt[0].provider == "youtube"

    def test_get_existing(self, svc):
        acct = _make(svc)
        fetched = svc.get_account(acct.id, _ORG_A)
        assert fetched is not None
        assert fetched.id == acct.id

    def test_get_nonexistent_returns_none(self, svc):
        assert svc.get_account(uuid4(), _ORG_A) is None

    def test_org_isolation(self, svc):
        """Org A cannot see Org B's accounts."""
        _make(svc, org_id=_ORG_B, label="B's account")
        a_accounts = svc.list_accounts(org_id=_ORG_A)
        assert len(a_accounts) == 0

    def test_get_wrong_org_returns_none(self, svc):
        acct = _make(svc, org_id=_ORG_B)
        assert svc.get_account(acct.id, _ORG_A) is None


# ─── is_default constraint ────────────────────────────────────────────────────
class TestIsDefault:
    def test_only_one_default_per_provider(self, svc):
        """Setting a second account as default clears the first one."""
        a1 = _make(svc, label="Account 1", is_default=True)
        a2 = _make(svc, label="Account 2", is_default=True)
        # After creating a2 as default, a1 must no longer be default.
        a1_refreshed = svc.get_account(a1.id, _ORG_A)
        assert a1_refreshed.is_default is False
        assert svc.get_account(a2.id, _ORG_A).is_default is True

    def test_set_default_clears_others(self, svc):
        a1 = _make(svc, label="Account 1", is_default=True)
        a2 = _make(svc, label="Account 2", is_default=False)
        result = svc.set_default(a2.id, _ORG_A)
        assert result.is_default is True
        assert svc.get_account(a1.id, _ORG_A).is_default is False

    def test_set_default_wrong_org_raises(self, svc):
        acct = _make(svc, org_id=_ORG_B, label="B account")
        with pytest.raises(IntegrationAccountNotFound):
            svc.set_default(acct.id, _ORG_A)

    def test_different_providers_can_both_have_defaults(self, svc):
        yt = _make(svc, provider="youtube", label="YT", is_default=True)
        meta = _make(svc, provider="meta", label="Meta", is_default=True)
        assert svc.get_account(yt.id, _ORG_A).is_default is True
        assert svc.get_account(meta.id, _ORG_A).is_default is True


# ─── update ──────────────────────────────────────────────────────────────────
class TestUpdate:
    def test_update_label(self, svc):
        acct = _make(svc, label="Old Label")
        updated = svc.update_account(acct.id, _ORG_A, account_label="New Label")
        assert updated.account_label == "New Label"

    def test_update_metadata(self, svc):
        acct = _make(svc, metadata={"a": 1})
        updated = svc.update_account(acct.id, _ORG_A, metadata={"b": 2})
        assert updated.metadata == {"b": 2}

    def test_update_is_default(self, svc):
        acct = _make(svc)
        updated = svc.update_account(acct.id, _ORG_A, is_default=True)
        assert updated.is_default is True

    def test_update_wrong_org_raises(self, svc):
        acct = _make(svc, org_id=_ORG_B, label="B")
        with pytest.raises(IntegrationAccountNotFound):
            svc.update_account(acct.id, _ORG_A, account_label="New")

    def test_no_op_update_returns_current(self, svc):
        acct = _make(svc, label="Stable")
        result = svc.update_account(acct.id, _ORG_A)
        assert result.account_label == "Stable"


# ─── delete ──────────────────────────────────────────────────────────────────
class TestDelete:
    def test_delete_existing(self, svc):
        acct = _make(svc)
        assert svc.delete_account(acct.id, _ORG_A) is True
        assert svc.get_account(acct.id, _ORG_A) is None

    def test_delete_nonexistent_returns_false(self, svc):
        assert svc.delete_account(uuid4(), _ORG_A) is False

    def test_delete_wrong_org_returns_false(self, svc):
        acct = _make(svc, org_id=_ORG_B)
        assert svc.delete_account(acct.id, _ORG_A) is False


# ─── decrypt_credential ──────────────────────────────────────────────────────
class TestDecryptCredential:
    def test_decrypt_returns_original(self, svc):
        cred = {"access_token": "tok", "refresh_token": "ref"}
        acct = _make(svc, credential=cred)
        assert svc.decrypt_credential(acct.id, _ORG_A) == cred

    def test_decrypt_wrong_org_raises(self, svc):
        acct = _make(svc, org_id=_ORG_B, label="B")
        with pytest.raises(IntegrationAccountNotFound):
            svc.decrypt_credential(acct.id, _ORG_A)

    def test_wrong_key_raises_credential_store_error(self, sqlite_db):
        """A key mismatch on decrypt raises CredentialStoreError (503 shape)."""
        key_a = Fernet.generate_key()
        key_b = Fernet.generate_key()
        svc_a = IntegrationAccountService(sqlite_db, fernet=Fernet(key_a))
        svc_b = IntegrationAccountService(sqlite_db, fernet=Fernet(key_b))
        acct = svc_a.create_account(
            org_id=_ORG_A,
            provider="youtube",
            account_label="A account",
            credential_dict={"tok": "secret"},
        )
        with pytest.raises(CredentialStoreError):
            svc_b.decrypt_credential(acct.id, _ORG_A)


# ─── build_integration_account_service ───────────────────────────────────────
class TestBuildService:
    def test_missing_key_raises_encryption_not_configured(self, sqlite_db):
        with pytest.raises(EncryptionNotConfigured):
            build_integration_account_service(sqlite_db, encryption_key="")

    def test_invalid_key_raises_encryption_not_configured(self, sqlite_db):
        with pytest.raises(EncryptionNotConfigured):
            build_integration_account_service(sqlite_db, encryption_key="not-a-fernet-key")

    def test_valid_key_builds_service(self, sqlite_db):
        key = Fernet.generate_key().decode("ascii")
        svc = build_integration_account_service(sqlite_db, encryption_key=key)
        assert isinstance(svc, IntegrationAccountService)
