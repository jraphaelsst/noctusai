"""Tests for the multi-account YouTube credential routing seam.

Covers the gap this module closes: YouTube operations now read/refresh the
org's DEFAULT ``integration_accounts`` row (so picking a default actually
swaps which channel a video targets), and a legacy single-account
credential is auto-migrated into ``integration_accounts`` so existing
connections keep working + appear as a card.

Strategy (mirrors test_integration_account_service.py): a REAL SQLite
client for the multi-account side (catches write→read propagation +
Fernet round-trips), and the seed ``FakeCredentialStore`` injected as the
legacy side via the resolver's DI seam.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from noctusai_lib.security.token_store import FakeCredentialStore

from app.services.integration_account_service import IntegrationAccountService
from app.services.youtube_account_resolver import (
    MultiAccountYouTubeStore,
    migrate_legacy_youtube_account,
    resolve_default_youtube_account,
)
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
    UNIQUE (org_id, provider, account_label)
);
"""


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def sqlite_db(tmp_path: Path) -> SQLiteClient:
    db_path = tmp_path / "resolver.sqlite3"
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
    return {
        "access_token": token,
        "refresh_token": "rtk",
        "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
        "expires_at": "2099-01-01T00:00:00+00:00",
    }


# ─── resolve_default_youtube_account ───────────────────────────────────────
class TestResolveDefault:
    def test_none_when_empty_and_no_migration(self, svc, cfg):
        assert (
            resolve_default_youtube_account(None, svc, _ORG, cfg, auto_migrate=False)
            is None
        )

    def test_returns_marked_default_among_many(self, svc, cfg):
        svc.create_account(_ORG, "youtube", "Channel A", _bundle("a"), is_default=False)
        b = svc.create_account(_ORG, "youtube", "Channel B", _bundle("b"), is_default=True)
        resolved = resolve_default_youtube_account(None, svc, _ORG, cfg, auto_migrate=False)
        assert resolved is not None and resolved.id == b.id

    def test_returns_sole_account_when_no_default_flag(self, svc, cfg):
        a = svc.create_account(_ORG, "youtube", "Only", _bundle(), is_default=False)
        resolved = resolve_default_youtube_account(None, svc, _ORG, cfg, auto_migrate=False)
        assert resolved is not None and resolved.id == a.id

    def test_swap_default_changes_resolution(self, svc, cfg):
        a = svc.create_account(_ORG, "youtube", "A", _bundle("a"), is_default=True)
        b = svc.create_account(_ORG, "youtube", "B", _bundle("b"), is_default=False)
        assert resolve_default_youtube_account(None, svc, _ORG, cfg, auto_migrate=False).id == a.id
        svc.set_default(b.id, _ORG)
        assert resolve_default_youtube_account(None, svc, _ORG, cfg, auto_migrate=False).id == b.id


# ─── MultiAccountYouTubeStore (the CredentialStore-shaped adapter) ──────────
class TestStoreAdapter:
    def test_get_returns_decrypted_default_bundle(self, svc, cfg):
        svc.create_account(_ORG, "youtube", "Main", _bundle("the-token"), is_default=True)
        store = MultiAccountYouTubeStore(svc, None, cfg, auto_migrate=False)
        rec = store.get(_ORG_STR, "youtube")
        assert rec is not None
        assert rec.tokens["access_token"] == "the-token"
        assert rec.provider == "youtube"

    def test_get_none_for_other_provider(self, svc, cfg):
        svc.create_account(_ORG, "youtube", "Main", _bundle(), is_default=True)
        store = MultiAccountYouTubeStore(svc, None, cfg, auto_migrate=False)
        assert store.get(_ORG_STR, "google_drive") is None

    def test_get_none_when_no_account(self, svc, cfg):
        store = MultiAccountYouTubeStore(svc, None, cfg, auto_migrate=False)
        assert store.get(_ORG_STR, "youtube") is None

    def test_put_persists_refreshed_bundle_to_resolved_account(self, svc, cfg):
        acct = svc.create_account(_ORG, "youtube", "Main", _bundle("old"), is_default=True)
        store = MultiAccountYouTubeStore(svc, None, cfg, auto_migrate=False)
        store.put(_ORG_STR, "youtube", _bundle("refreshed"), metadata={"channel_id": "UC1"})
        # The SAME account row now holds the refreshed token + merged metadata.
        again = svc.decrypt_credential(acct.id, _ORG)
        assert again["access_token"] == "refreshed"
        reloaded = svc.get_account(acct.id, _ORG)
        assert reloaded.metadata.get("channel_id") == "UC1"

    def test_put_other_provider_raises(self, svc, cfg):
        svc.create_account(_ORG, "youtube", "Main", _bundle(), is_default=True)
        store = MultiAccountYouTubeStore(svc, None, cfg, auto_migrate=False)
        with pytest.raises(ValueError):
            store.put(_ORG_STR, "gmail", _bundle())

    def test_delete_removes_resolved_account(self, svc, cfg):
        svc.create_account(_ORG, "youtube", "Main", _bundle(), is_default=True)
        store = MultiAccountYouTubeStore(svc, None, cfg, auto_migrate=False)
        assert store.delete(_ORG_STR, "youtube") is True
        assert store.get(_ORG_STR, "youtube") is None

    def test_list_providers(self, svc, cfg):
        store = MultiAccountYouTubeStore(svc, None, cfg, auto_migrate=False)
        assert store.list_providers(_ORG_STR) == []
        svc.create_account(_ORG, "youtube", "Main", _bundle(), is_default=True)
        assert store.list_providers(_ORG_STR) == ["youtube"]


# ─── Legacy auto-migration (DI-injected FakeCredentialStore) ────────────────
class TestLegacyMigration:
    def _legacy_with_youtube(self) -> FakeCredentialStore:
        legacy = FakeCredentialStore()
        legacy.put(
            _ORG_STR,
            "youtube",
            _bundle("legacy-token"),
            metadata={"channel_id": "UCxyz", "channel_title": "My Channel"},
        )
        return legacy

    def test_migrates_legacy_into_default_account(self, svc, cfg):
        legacy = self._legacy_with_youtube()
        migrated = migrate_legacy_youtube_account(
            None, svc, _ORG, cfg, legacy_store=legacy
        )
        assert migrated is not None
        assert migrated.is_default is True
        assert migrated.account_label == "My Channel"
        assert migrated.metadata.get("channel_id") == "UCxyz"
        # The credential round-trips.
        assert svc.decrypt_credential(migrated.id, _ORG)["access_token"] == "legacy-token"

    def test_migration_is_idempotent(self, svc, cfg):
        legacy = self._legacy_with_youtube()
        first = migrate_legacy_youtube_account(None, svc, _ORG, cfg, legacy_store=legacy)
        second = migrate_legacy_youtube_account(None, svc, _ORG, cfg, legacy_store=legacy)
        assert first.id == second.id
        assert len(svc.list_accounts(_ORG, provider="youtube")) == 1

    def test_no_migration_when_no_legacy_record(self, svc, cfg):
        empty_legacy = FakeCredentialStore()
        assert (
            migrate_legacy_youtube_account(None, svc, _ORG, cfg, legacy_store=empty_legacy)
            is None
        )

    def test_resolver_auto_migrates_then_resolves(self, svc, cfg):
        legacy = self._legacy_with_youtube()
        store = MultiAccountYouTubeStore(
            svc, None, cfg, auto_migrate=True, legacy_store=legacy
        )
        rec = store.get(_ORG_STR, "youtube")
        assert rec is not None and rec.tokens["access_token"] == "legacy-token"
        # And it now exists as a real (default) integration account.
        accounts = svc.list_accounts(_ORG, provider="youtube")
        assert len(accounts) == 1 and accounts[0].is_default
