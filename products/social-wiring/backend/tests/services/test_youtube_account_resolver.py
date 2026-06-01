"""Tests for the multi-account YouTube credential routing seam.

Covers the gap this module closes: YouTube operations now read/refresh the
org's DEFAULT ``integration_accounts`` row (so picking a default actually
swaps which channel a video targets). Legacy adoption is a SEPARATE,
explicit step — see ``test_legacy_adoption.py``; this consume path never
adopts implicitly.

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

from app.services.integration_account_service import IntegrationAccountService
from app.services.youtube_account_resolver import (
    MultiAccountYouTubeStore,
    build_youtube_service_for_org,
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
    def test_none_when_empty(self, svc):
        assert resolve_default_youtube_account(svc, _ORG) is None

    def test_returns_marked_default_among_many(self, svc):
        svc.create_account(_ORG, "youtube", "Channel A", _bundle("a"), is_default=False)
        b = svc.create_account(_ORG, "youtube", "Channel B", _bundle("b"), is_default=True)
        assert resolve_default_youtube_account(svc, _ORG).id == b.id

    def test_returns_sole_account_when_no_default_flag(self, svc):
        a = svc.create_account(_ORG, "youtube", "Only", _bundle(), is_default=False)
        assert resolve_default_youtube_account(svc, _ORG).id == a.id

    def test_swap_default_changes_resolution(self, svc):
        a = svc.create_account(_ORG, "youtube", "A", _bundle("a"), is_default=True)
        b = svc.create_account(_ORG, "youtube", "B", _bundle("b"), is_default=False)
        assert resolve_default_youtube_account(svc, _ORG).id == a.id
        svc.set_default(b.id, _ORG)
        assert resolve_default_youtube_account(svc, _ORG).id == b.id


# ─── MultiAccountYouTubeStore (the CredentialStore-shaped adapter) ──────────
class TestStoreAdapter:
    def test_get_returns_decrypted_default_bundle(self, svc):
        svc.create_account(_ORG, "youtube", "Main", _bundle("the-token"), is_default=True)
        store = MultiAccountYouTubeStore(svc)
        rec = store.get(_ORG_STR, "youtube")
        assert rec is not None
        assert rec.tokens["access_token"] == "the-token"
        assert rec.provider == "youtube"

    def test_get_none_for_other_provider(self, svc):
        svc.create_account(_ORG, "youtube", "Main", _bundle(), is_default=True)
        assert MultiAccountYouTubeStore(svc).get(_ORG_STR, "google_drive") is None

    def test_get_none_when_no_account(self, svc):
        assert MultiAccountYouTubeStore(svc).get(_ORG_STR, "youtube") is None

    def test_put_persists_refreshed_bundle_to_resolved_account(self, svc):
        acct = svc.create_account(_ORG, "youtube", "Main", _bundle("old"), is_default=True)
        store = MultiAccountYouTubeStore(svc)
        store.put(_ORG_STR, "youtube", _bundle("refreshed"), metadata={"channel_id": "UC1"})
        assert svc.decrypt_credential(acct.id, _ORG)["access_token"] == "refreshed"
        assert svc.get_account(acct.id, _ORG).metadata.get("channel_id") == "UC1"

    def test_put_other_provider_raises(self, svc):
        svc.create_account(_ORG, "youtube", "Main", _bundle(), is_default=True)
        with pytest.raises(ValueError):
            MultiAccountYouTubeStore(svc).put(_ORG_STR, "gmail", _bundle())

    def test_delete_removes_resolved_account(self, svc):
        svc.create_account(_ORG, "youtube", "Main", _bundle(), is_default=True)
        store = MultiAccountYouTubeStore(svc)
        assert store.delete(_ORG_STR, "youtube") is True
        assert store.get(_ORG_STR, "youtube") is None

    def test_list_providers(self, svc):
        store = MultiAccountYouTubeStore(svc)
        assert store.list_providers(_ORG_STR) == []
        svc.create_account(_ORG, "youtube", "Main", _bundle(), is_default=True)
        assert store.list_providers(_ORG_STR) == ["youtube"]


# ─── build_youtube_service_for_org (the absorbed N=4 builder) ──────────────
class TestBuilder:
    def test_builds_service_backed_by_multi_account_store(self, sqlite_db, cfg):
        service = build_youtube_service_for_org(sqlite_db, cfg)
        # The service is wired to the multi-account store (not the legacy one).
        assert service._store.__class__.__name__ == "MultiAccountYouTubeStore"
