"""Tests for the channel-object fields on the integration_accounts_router.

Extends the existing router tests with:
  - client_id round-trip in create + list filter
  - PATCH updates status + client_id
  - /sync endpoint (happy + error)
  - OAuth callback writes channel_info + status='validated'
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.services.integration_account_service import (
    IntegrationAccountService,
)
from app.sqlite_client import SQLiteClient

_ORG_A = "00000000-0000-4000-8000-000000000001"

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
def fernet_key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def sqlite_db(tmp_path: Path) -> SQLiteClient:
    db_path = tmp_path / "ia_ch.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
    return SQLiteClient(db_path)


@pytest.fixture
def ia_service(sqlite_db, fernet_key):
    return IntegrationAccountService(sqlite_db, fernet=Fernet(fernet_key.encode("utf-8")))


@pytest.fixture
def client(ia_service):
    from noctusai_lib.testing import MockSupabaseClient, MockUser, MockUserResponse, bind_consent_module_to_mock
    from app.routers.integration_accounts_router import get_account_service

    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=_ORG_A))
    )

    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)

        app.dependency_overrides[get_account_service] = lambda: ia_service
        tc = TestClient(app, raise_server_exceptions=True)
        yield tc
        app.dependency_overrides.pop(get_account_service, None)


def _auth():
    return {"Authorization": "Bearer test-token"}


def _make_account(client, *, label="My Channel", provider="youtube", client_id=None, status="validated"):
    body = {
        "provider": provider,
        "account_label": label,
        "credential": {"access_token": "tok", "refresh_token": "ref"},
        "metadata": {"channel_id": "UC1"},
        "is_default": False,
    }
    if client_id is not None:
        body["client_id"] = str(client_id)
    resp = client.post("/api/integrations/accounts", json=body, headers=_auth())
    assert resp.status_code == 201, resp.text
    return resp.json()


# ─── client_id create + list filter ───────────────────────────────────────────

class TestClientIdCreateAndFilter:
    def test_create_with_client_id_round_trips(self, client):
        cid = uuid4()
        data = _make_account(client, client_id=cid)
        assert data["client_id"] == str(cid)

    def test_create_without_client_id_returns_null(self, client):
        data = _make_account(client)
        assert data["client_id"] is None

    def test_list_filter_by_client_id(self, client):
        cid = uuid4()
        a_with = _make_account(client, label="With", client_id=cid)
        a_without = _make_account(client, label="Without")
        resp = client.get(
            f"/api/integrations/accounts?client_id={cid}", headers=_auth()
        )
        assert resp.status_code == 200
        ids = {a["id"] for a in resp.json()}
        assert a_with["id"] in ids
        assert a_without["id"] not in ids

    def test_status_and_channel_info_in_response(self, client):
        data = _make_account(client)
        assert "status" in data
        assert "channel_info" in data
        assert "last_synced_at" in data


# ─── PATCH status + client_id ─────────────────────────────────────────────────

class TestPatchChannelFields:
    def test_patch_status(self, client):
        data = _make_account(client)
        resp = client.patch(
            f"/api/integrations/accounts/{data['id']}",
            json={"status": "error"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_patch_client_id(self, client):
        data = _make_account(client)
        cid = uuid4()
        resp = client.patch(
            f"/api/integrations/accounts/{data['id']}",
            json={"client_id": str(cid)},
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert resp.json()["client_id"] == str(cid)


# ─── /sync endpoint ───────────────────────────────────────────────────────────

class TestSyncEndpoint:
    def test_sync_happy_path(self, client, ia_service):
        """POST /sync calls sync_channel_info and returns updated account."""
        from app.modules.youtube.services.youtube import ChannelInfo

        data = _make_account(client)
        account_id = data["id"]

        fake_channel = ChannelInfo(
            channel_id="UC_LIVE",
            title="Live Channel",
            subscriber_count=1234,
            video_count=10,
            view_count=99000,
            thumbnail_url="",
        )

        mock_yt_svc = MagicMock()
        mock_yt_svc.get_channel_info.return_value = fake_channel

        with patch(
            "app.services.account_credentials.build_youtube_service_for_org",
            return_value=mock_yt_svc,
        ):
            resp = client.post(
                f"/api/integrations/accounts/{account_id}/sync",
                headers=_auth(),
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "validated"
        assert body["channel_info"]["channel_id"] == "UC_LIVE"
        assert body["last_synced_at"] is not None

    def test_sync_error_path_returns_error_status(self, client, ia_service):
        """If the YT service fails, the account is set to status=error."""
        data = _make_account(client)
        account_id = data["id"]

        mock_yt_svc = MagicMock()
        mock_yt_svc.get_channel_info.side_effect = RuntimeError("quota exceeded")

        with patch(
            "app.services.account_credentials.build_youtube_service_for_org",
            return_value=mock_yt_svc,
        ):
            resp = client.post(
                f"/api/integrations/accounts/{account_id}/sync",
                headers=_auth(),
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "error"
        assert "quota exceeded" in body["channel_info"].get("error", "")

    def test_sync_nonexistent_404(self, client):
        resp = client.post(
            f"/api/integrations/accounts/{uuid4()}/sync",
            headers=_auth(),
        )
        assert resp.status_code == 404

    def test_sync_requires_auth(self, client):
        resp = client.post(f"/api/integrations/accounts/{uuid4()}/sync")
        assert resp.status_code == 401


# ─── OAuth callback writes channel_info + status ─────────────────────────────

class TestOAuthCallbackChannelInfo:
    def test_callback_writes_channel_info_and_status(self, client, ia_service):
        """OAuth callback must write channel_info + status=validated."""
        from app.dependencies import get_settings
        from app.config import settings as _settings
        from app.main import app
        from app.routers.integration_accounts_router import (
            get_yt_oauth_provider,
            get_yt_pkce_redis,
            get_yt_client_factory,
            get_account_service,
        )
        from noctusai_lib.security.oauth.fake import FakeOAuthProvider
        from noctusai_lib.integrations.youtube import ChannelInfo
        from noctusai_lib.integrations.youtube.fake import FakeYoutubeClient

        fake_cfg = _settings.model_copy(
            update={
                "youtube_client_id": "fake-cid",
                "youtube_client_secret": "fake-cs",
                "frontend_base_url": "",
            }
        )
        owned = ChannelInfo(
            channel_id="UC_CHAN_INFO",
            title="Chan Info Channel",
            subscriber_count=0,
            video_count=0,
            view_count=0,
        )
        overrides = {
            get_settings: lambda: fake_cfg,
            get_yt_oauth_provider: lambda: FakeOAuthProvider(use_pkce=False),
            get_yt_pkce_redis: lambda: None,
            get_yt_client_factory: lambda: (
                lambda **kw: FakeYoutubeClient(owned_channel_info=owned)
            ),
            get_account_service: lambda: ia_service,
        }
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce-chaninfo"
            resp = client.get(
                "/api/integrations/accounts/youtube/oauth/callback"
                f"?code=auth-code&state={state}",
                follow_redirects=False,
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code in (302, 303), resp.text

        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="youtube")
        assert len(accounts) == 1
        acct = accounts[0]
        # The callback should have written channel_info (at least channel_id).
        assert acct.channel_info.get("channel_id") == "UC_CHAN_INFO"
        assert acct.status == "validated"
        assert acct.last_synced_at is not None
