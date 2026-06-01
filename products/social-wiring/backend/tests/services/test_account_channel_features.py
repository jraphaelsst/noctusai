"""Tests for the channel-object features added in P2-BE.

Covers:
  - IntegrationAccount.client_id / status / channel_info / last_synced_at
    round-trip through service CRUD
  - list_accounts with client_id filter
  - update_channel_info writes the three cols
  - sync_channel_info happy path (validating→validated, channel_info cached)
  - sync_channel_info error path (→status='error')
  - MultiAccountCredentialStore with account_id resolves the specific account
    (the switching proof), NOT the default
  - resolve_account_by_id: None on wrong provider, None on wrong org
  - OAuth callback idempotency test still passes (channel_info + status written)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from app.services.credential_vault import StoredCredential
from app.services.integration_account_service import (
    IntegrationAccount,
    IntegrationAccountService,
    build_integration_account_service,
)
from app.services.account_credentials import (
    MultiAccountCredentialStore,
    resolve_account_by_id,
    resolve_default_account,
)
from app.sqlite_client import SQLiteClient

_ORG_A = UUID("00000000-0000-4000-8000-000000000001")
_ORG_B = UUID("00000000-0000-4000-8000-000000000002")

# SQLite schema mirrors the extended Supabase DDL (migration 008).
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


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sqlite_db(tmp_path: Path) -> SQLiteClient:
    db_path = tmp_path / "ia_channel.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
    return SQLiteClient(db_path)


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def svc(sqlite_db: SQLiteClient, fernet_key: str) -> IntegrationAccountService:
    return IntegrationAccountService(sqlite_db, fernet=Fernet(fernet_key.encode("utf-8")))


def _cred() -> dict:
    return {"access_token": "tok", "refresh_token": "ref"}


def _make(
    svc: IntegrationAccountService,
    *,
    org_id=_ORG_A,
    provider="youtube",
    label="My Channel",
    is_default=False,
    client_id=None,
    status="validated",
) -> IntegrationAccount:
    return svc.create_account(
        org_id=org_id,
        provider=provider,
        account_label=label,
        credential_dict=_cred(),
        metadata={"channel_id": "UC123"},
        is_default=is_default,
        client_id=client_id,
        status=status,
    )


# ─── client_id round-trip ─────────────────────────────────────────────────────

class TestClientIdRoundTrip:
    def test_create_with_client_id(self, svc):
        cid = uuid4()
        acct = _make(svc, client_id=cid)
        assert acct.client_id == cid

    def test_create_without_client_id(self, svc):
        acct = _make(svc)
        assert acct.client_id is None

    def test_status_stored_and_returned(self, svc):
        acct = _make(svc, status="wiring")
        assert acct.status == "wiring"

    def test_default_status_is_validated(self, svc):
        acct = _make(svc)
        assert acct.status == "validated"

    def test_channel_info_empty_by_default(self, svc):
        acct = _make(svc)
        assert acct.channel_info == {}

    def test_last_synced_at_none_by_default(self, svc):
        acct = _make(svc)
        assert acct.last_synced_at is None


# ─── list_accounts with client_id filter ──────────────────────────────────────

class TestClientIdFilter:
    def test_filter_by_client_id_returns_only_matching(self, svc):
        cid = uuid4()
        a1 = _make(svc, label="A", client_id=cid)
        a2 = _make(svc, label="B")  # no client_id
        results = svc.list_accounts(_ORG_A, client_id=cid)
        ids = {r.id for r in results}
        assert a1.id in ids
        assert a2.id not in ids

    def test_filter_by_nonexistent_client_id_returns_empty(self, svc):
        _make(svc, label="A")
        results = svc.list_accounts(_ORG_A, client_id=uuid4())
        assert results == []

    def test_no_client_id_filter_returns_all(self, svc):
        _make(svc, label="A")
        _make(svc, label="B")
        results = svc.list_accounts(_ORG_A)
        assert len(results) == 2


# ─── update_channel_info ──────────────────────────────────────────────────────

class TestUpdateChannelInfo:
    def test_writes_channel_info_and_status(self, svc):
        acct = _make(svc)
        now = datetime.now(timezone.utc)
        info = {"channel_id": "UC999", "title": "Test Channel", "subscriber_count": 100}
        updated = svc.update_channel_info(
            account_id=acct.id,
            org_id=_ORG_A,
            channel_info=info,
            status="validated",
            last_synced_at=now,
        )
        assert updated.channel_info == info
        assert updated.status == "validated"
        assert updated.last_synced_at is not None

    def test_wrong_org_raises(self, svc):
        from app.services.integration_account_service import IntegrationAccountNotFound
        acct = _make(svc, org_id=_ORG_B, label="B account")
        with pytest.raises(IntegrationAccountNotFound):
            svc.update_channel_info(
                account_id=acct.id,
                org_id=_ORG_A,
                channel_info={},
                status="error",
                last_synced_at=datetime.now(timezone.utc),
            )

    def test_sets_error_status(self, svc):
        acct = _make(svc)
        now = datetime.now(timezone.utc)
        updated = svc.update_channel_info(
            account_id=acct.id,
            org_id=_ORG_A,
            channel_info={"error": "API call failed"},
            status="error",
            last_synced_at=now,
        )
        assert updated.status == "error"
        assert updated.channel_info["error"] == "API call failed"


# ─── sync_channel_info ────────────────────────────────────────────────────────

class TestSyncChannelInfo:
    def test_happy_path_sets_validated(self, svc, fernet_key):
        """sync_channel_info fetches channel info → status=validated."""
        from app.services.account_credentials import sync_channel_info
        from app.modules.youtube.services.youtube import ChannelInfo

        acct = _make(svc)

        # Build mock objects (external service — ok to mock)
        mock_cfg = MagicMock()
        mock_cfg.encryption_key = fernet_key
        mock_cfg.youtube_client_id = "cid"
        mock_cfg.youtube_client_secret = "cs"
        mock_cfg.youtube_redirect_uri = "http://localhost/cb"

        fake_channel_info = ChannelInfo(
            channel_id="UC_SYNCED",
            title="Synced Channel",
            subscriber_count=5000,
            video_count=42,
            view_count=100000,
            thumbnail_url="",
        )

        # We patch build_youtube_service_for_org (external YT service boundary)
        from unittest.mock import patch

        mock_yt_svc = MagicMock()
        mock_yt_svc.get_channel_info.return_value = fake_channel_info

        with patch(
            "app.services.account_credentials.build_youtube_service_for_org",
            return_value=mock_yt_svc,
        ):
            updated = sync_channel_info(None, mock_cfg, svc, acct)

        assert updated.status == "validated"
        assert updated.channel_info["channel_id"] == "UC_SYNCED"
        assert updated.channel_info["title"] == "Synced Channel"
        assert updated.channel_info["subscriber_count"] == 5000
        assert updated.last_synced_at is not None

    def test_error_path_sets_error_status(self, svc, fernet_key):
        """sync_channel_info API failure → status=error, no exception raised."""
        from app.services.account_credentials import sync_channel_info
        from unittest.mock import patch

        acct = _make(svc)

        mock_cfg = MagicMock()
        mock_cfg.encryption_key = fernet_key

        mock_yt_svc = MagicMock()
        mock_yt_svc.get_channel_info.side_effect = RuntimeError("API down")

        with patch(
            "app.services.account_credentials.build_youtube_service_for_org",
            return_value=mock_yt_svc,
        ):
            updated = sync_channel_info(None, mock_cfg, svc, acct)

        assert updated.status == "error"
        assert "API down" in updated.channel_info.get("error", "")
        assert updated.last_synced_at is not None


# ─── MultiAccountCredentialStore with account_id (switching proof) ────────────

class TestAccountIdSwitching:
    def test_store_with_account_id_resolves_specific_not_default(self, svc, fernet_key):
        """A store built with account_id=X resolves X's creds, not the default."""
        acct_default = _make(svc, label="Default", is_default=True)
        acct_specific = _make(svc, label="Specific", is_default=False)

        store_specific = MultiAccountCredentialStore(
            svc, "youtube", account_id=acct_specific.id
        )
        store_default = MultiAccountCredentialStore(svc, "youtube")

        # The specific store should resolve the specific account.
        resolved_specific = store_specific._resolve(str(_ORG_A))
        assert resolved_specific is not None
        assert resolved_specific.id == acct_specific.id

        # The default store should resolve the default account.
        resolved_default = store_default._resolve(str(_ORG_A))
        assert resolved_default is not None
        assert resolved_default.id == acct_default.id

    def test_store_with_wrong_account_id_resolves_none(self, svc):
        """account_id that doesn't exist → _resolve returns None."""
        store = MultiAccountCredentialStore(svc, "youtube", account_id=uuid4())
        resolved = store._resolve(str(_ORG_A))
        assert resolved is None


# ─── resolve_account_by_id ────────────────────────────────────────────────────

class TestResolveAccountById:
    def test_returns_account_matching_provider(self, svc):
        acct = _make(svc)
        resolved = resolve_account_by_id(svc, _ORG_A, "youtube", acct.id)
        assert resolved is not None
        assert resolved.id == acct.id

    def test_none_on_wrong_provider(self, svc):
        acct = _make(svc, provider="youtube", label="YT")
        resolved = resolve_account_by_id(svc, _ORG_A, "meta", acct.id)
        assert resolved is None

    def test_none_on_nonexistent_id(self, svc):
        resolved = resolve_account_by_id(svc, _ORG_A, "youtube", uuid4())
        assert resolved is None

    def test_none_on_wrong_org(self, svc):
        acct = _make(svc, org_id=_ORG_B, label="B account")
        resolved = resolve_account_by_id(svc, _ORG_A, "youtube", acct.id)
        assert resolved is None
