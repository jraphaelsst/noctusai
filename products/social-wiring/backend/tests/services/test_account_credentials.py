"""Tests for the canonical multi-account credential + service factory.

Covers the GENERIC provider-parametrized store (so picking a default
account swaps which account a provider's operations target), the per-
provider service-factory registry (YouTube wired; others raise
ProviderNotWired honestly), and the YouTube convenience wrapper.

Strategy (mirrors test_integration_account_service.py): a REAL SQLite
client (catches write→read propagation + Fernet round-trips).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from cryptography.fernet import Fernet

from app.services.account_credentials import (
    MultiAccountCredentialStore,
    ProviderNotWired,
    build_credential_store,
    build_service_for_org,
    build_youtube_service_for_org,
    register_service_factory,
    resolve_default_account,
)
from app.services.integration_account_service import IntegrationAccountService
from app.sqlite_client import SQLiteClient

_ORG = UUID("00000000-0000-4000-8000-000000000001")
_ORG_STR = str(_ORG)

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
    marca_id           TEXT,
    status              TEXT NOT NULL DEFAULT 'validated',
    channel_info        TEXT NOT NULL DEFAULT '{}',
    last_synced_at      TEXT,
    UNIQUE (org_id, provider, account_label)
);
"""


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def sqlite_db(tmp_path: Path) -> SQLiteClient:
    db_path = tmp_path / "ac.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
    return SQLiteClient(db_path)


@pytest.fixture
def svc(sqlite_db: SQLiteClient, fernet_key: str) -> IntegrationAccountService:
    return IntegrationAccountService(sqlite_db, fernet=Fernet(fernet_key.encode("utf-8")))


@pytest.fixture
def cfg(fernet_key: str) -> SimpleNamespace:
    return SimpleNamespace(
        encryption_key=fernet_key,
        youtube_client_id="cid",
        youtube_client_secret="secret",
        youtube_redirect_uri="http://localhost:8011/api/youtube/oauth/callback",
    )


def _bundle(token: str = "atk") -> dict:
    return {"access_token": token, "refresh_token": "rtk", "scopes": ["s"]}


# ─── resolve_default_account (generic over provider) ────────────────────────
class TestResolveDefault:
    def test_none_when_empty(self, svc):
        assert resolve_default_account(svc, _ORG, "youtube") is None

    def test_returns_marked_default(self, svc):
        svc.create_account(_ORG, "youtube", "A", _bundle("a"), is_default=False)
        b = svc.create_account(_ORG, "youtube", "B", _bundle("b"), is_default=True)
        assert resolve_default_account(svc, _ORG, "youtube").id == b.id

    def test_swap_changes_resolution(self, svc):
        a = svc.create_account(_ORG, "youtube", "A", _bundle("a"), is_default=True)
        b = svc.create_account(_ORG, "youtube", "B", _bundle("b"), is_default=False)
        assert resolve_default_account(svc, _ORG, "youtube").id == a.id
        svc.set_default(b.id, _ORG)
        assert resolve_default_account(svc, _ORG, "youtube").id == b.id

    def test_provider_scoped(self, svc):
        svc.create_account(_ORG, "youtube", "YT", _bundle(), is_default=True)
        assert resolve_default_account(svc, _ORG, "gmail") is None


# ─── MultiAccountCredentialStore (provider-parametrized adapter) ────────────
class TestStore:
    def test_get_decrypts_default(self, svc):
        svc.create_account(_ORG, "youtube", "Main", _bundle("tok"), is_default=True)
        rec = MultiAccountCredentialStore(svc, "youtube").get(_ORG_STR, "youtube")
        assert rec is not None and rec.tokens["access_token"] == "tok"

    def test_get_none_for_mismatched_provider(self, svc):
        svc.create_account(_ORG, "youtube", "Main", _bundle(), is_default=True)
        # Store bound to youtube must not answer a gmail get.
        assert MultiAccountCredentialStore(svc, "youtube").get(_ORG_STR, "gmail") is None

    def test_store_is_provider_scoped(self, svc):
        # A gmail-bound store sees gmail accounts, not youtube ones.
        svc.create_account(_ORG, "youtube", "YT", _bundle(), is_default=True)
        gmail_store = MultiAccountCredentialStore(svc, "gmail")
        assert gmail_store.get(_ORG_STR, "gmail") is None
        svc.create_account(_ORG, "gmail", "G", _bundle("g"), is_default=True)
        assert gmail_store.get(_ORG_STR, "gmail").tokens["access_token"] == "g"

    def test_put_persists_refresh(self, svc):
        acct = svc.create_account(_ORG, "youtube", "Main", _bundle("old"), is_default=True)
        MultiAccountCredentialStore(svc, "youtube").put(
            _ORG_STR, "youtube", _bundle("new"), metadata={"channel_id": "UC1"}
        )
        assert svc.decrypt_credential(acct.id, _ORG)["access_token"] == "new"
        assert svc.get_account(acct.id, _ORG).metadata.get("channel_id") == "UC1"

    def test_put_mismatched_provider_raises(self, svc):
        svc.create_account(_ORG, "youtube", "Main", _bundle(), is_default=True)
        with pytest.raises(ValueError):
            MultiAccountCredentialStore(svc, "youtube").put(_ORG_STR, "gmail", _bundle())

    def test_delete_removes_default(self, svc):
        svc.create_account(_ORG, "youtube", "Main", _bundle(), is_default=True)
        store = MultiAccountCredentialStore(svc, "youtube")
        assert store.delete(_ORG_STR, "youtube") is True
        assert store.get(_ORG_STR, "youtube") is None


# ─── Service factory registry ───────────────────────────────────────────────
class TestServiceFactory:
    def test_build_credential_store_is_provider_bound(self, sqlite_db, cfg):
        store = build_credential_store(sqlite_db, cfg, "gmail")
        assert isinstance(store, MultiAccountCredentialStore)
        assert store.list_providers(_ORG_STR) == []  # no gmail accounts yet

    def test_youtube_service_wired(self, sqlite_db, cfg):
        service = build_service_for_org(sqlite_db, cfg, "youtube")
        assert service._store.__class__.__name__ == "MultiAccountCredentialStore"

    def test_youtube_convenience_wrapper(self, sqlite_db, cfg):
        service = build_youtube_service_for_org(sqlite_db, cfg)
        assert service.__class__.__name__ == "YouTubeService"

    def test_unwired_provider_raises_provider_not_wired(self, sqlite_db, cfg):
        with pytest.raises(ProviderNotWired):
            build_service_for_org(sqlite_db, cfg, "gmail")

    def test_register_service_factory_extends_registry(self, sqlite_db, cfg):
        sentinel = object()
        register_service_factory("n8n", lambda admin, c, store: sentinel)
        try:
            assert build_service_for_org(sqlite_db, cfg, "n8n") is sentinel
        finally:
            # Keep the module-level registry clean for other tests.
            from app.services import account_credentials as _ac
            _ac._SERVICE_FACTORIES.pop("n8n", None)
