"""Tests for the canonical "adopt an existing single-account connection" path.

``adopt_legacy_account`` is the reference onboarding step that graduates a
legacy single-account ``credentials`` row into the multi-account
``integration_accounts`` model. YouTube is pilot #1; the function is
provider-general so calendar/gmail/meta adopt through the SAME path.

Strategy: a REAL SQLite client for the multi-account side + the seed
``FakeCredentialStore`` injected as the legacy side via the DI seam.
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
from app.services.legacy_adoption import adopt_legacy_account, derive_account_label
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
    client_id           TEXT,
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
def svc(tmp_path: Path, fernet_key: str) -> IntegrationAccountService:
    db_path = tmp_path / "adopt.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
    return IntegrationAccountService(SQLiteClient(db_path), fernet=Fernet(fernet_key.encode("utf-8")))


@pytest.fixture
def cfg(fernet_key: str) -> SimpleNamespace:
    return SimpleNamespace(encryption_key=fernet_key)


def _bundle(token: str = "atk") -> dict:
    return {"access_token": token, "refresh_token": "rtk", "scopes": ["s"]}


def _legacy(provider: str, metadata: dict, token: str = "legacy-token") -> FakeCredentialStore:
    legacy = FakeCredentialStore()
    legacy.put(_ORG_STR, provider, _bundle(token), metadata=metadata)
    return legacy


# ─── label derivation ──────────────────────────────────────────────────────
class TestDeriveLabel:
    def test_youtube_uses_channel_title(self):
        rec = SimpleNamespace(metadata={"channel_title": "My Channel"})
        assert derive_account_label("youtube", rec) == "My Channel"

    def test_falls_back_to_generic(self):
        rec = SimpleNamespace(metadata={})
        assert derive_account_label("meta", rec) == "meta (conta existente)"


# ─── adoption (YouTube pilot) ───────────────────────────────────────────────
class TestAdoptYouTube:
    def test_adopts_into_default_account(self, svc, cfg):
        legacy = _legacy("youtube", {"channel_id": "UCxyz", "channel_title": "My Channel"})
        adopted = adopt_legacy_account(None, svc, _ORG, "youtube", cfg, legacy_store=legacy)
        assert adopted is not None
        assert adopted.is_default is True
        assert adopted.account_label == "My Channel"
        assert adopted.metadata.get("channel_id") == "UCxyz"
        assert svc.decrypt_credential(adopted.id, _ORG)["access_token"] == "legacy-token"

    def test_idempotent(self, svc, cfg):
        legacy = _legacy("youtube", {"channel_title": "Chan"})
        first = adopt_legacy_account(None, svc, _ORG, "youtube", cfg, legacy_store=legacy)
        second = adopt_legacy_account(None, svc, _ORG, "youtube", cfg, legacy_store=legacy)
        assert first.id == second.id
        assert len(svc.list_accounts(_ORG, provider="youtube")) == 1

    def test_none_when_no_legacy_record(self, svc, cfg):
        assert adopt_legacy_account(None, svc, _ORG, "youtube", cfg, legacy_store=FakeCredentialStore()) is None


# ─── adoption is provider-general (the "upcoming other ones") ───────────────
class TestAdoptGeneral:
    def test_adopts_meta_through_same_path(self, svc, cfg):
        legacy = _legacy("meta", {"account_name": "Acme Page"})
        adopted = adopt_legacy_account(None, svc, _ORG, "meta", cfg, legacy_store=legacy)
        assert adopted is not None
        assert adopted.provider == "meta"
        assert adopted.is_default is True
        assert adopted.account_label == "Acme Page"

    def test_providers_are_independent(self, svc, cfg):
        adopt_legacy_account(None, svc, _ORG, "youtube", cfg, legacy_store=_legacy("youtube", {"channel_title": "YT"}))
        adopt_legacy_account(None, svc, _ORG, "gmail", cfg, legacy_store=_legacy("gmail", {"account_email": "a@b.com"}))
        assert len(svc.list_accounts(_ORG, provider="youtube")) == 1
        assert len(svc.list_accounts(_ORG, provider="gmail")) == 1
        assert svc.list_accounts(_ORG, provider="gmail")[0].account_label == "a@b.com"
