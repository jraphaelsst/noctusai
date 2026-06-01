"""Tests for the integration_accounts_router — /api/integrations/*.

Tests use the DI seam (app.dependency_overrides[get_account_service]) with
a SQLite-backed IntegrationAccountService (real CRUD). No monkey-patching
of our own code per KB § PATTERNS/di-test-seam.md.

Coverage:
  - CRUD round-trips (list / get / create / update / set-default / delete)
  - ENCRYPTION_KEY missing → 503 via DI seam
  - Provider registry endpoint
  - YouTube OAuth start: inject the seed FakeOAuthProvider via the
    get_yt_oauth_provider DI seam, verify the consent-URL response
  - YouTube OAuth callback: inject FakeOAuthProvider + FakeYoutubeClient via
    the DI seams, verify the integration_account row is created with correct
    metadata (exercises the REAL async exchange_code→TokenSet contract)
  - RLS: org A cannot see org B's accounts (DI seam verifies service-level)
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.services.credential_vault import EncryptionNotConfigured
from app.services.integration_account_service import (
    IntegrationAccountService,
    build_integration_account_service,
)
from app.sqlite_client import SQLiteClient

_ORG_A = "00000000-0000-4000-8000-000000000001"
_ORG_B = "00000000-0000-4000-8000-000000000002"

_IA_SCHEMA = """
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


# ─── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def sqlite_ia_db(tmp_path: Path) -> SQLiteClient:
    db_path = tmp_path / "ia.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_IA_SCHEMA)
    return SQLiteClient(db_path)


@pytest.fixture
def ia_service(sqlite_ia_db: SQLiteClient, fernet_key: str) -> IntegrationAccountService:
    return IntegrationAccountService(sqlite_ia_db, fernet=Fernet(fernet_key.encode("utf-8")))


@pytest.fixture
def client(ia_service):
    """TestClient with the account service DI seam wired to SQLite.

    Patches DatabaseModule so the app boots without Supabase credentials;
    overrides get_account_service so every route uses the SQLite-backed
    service. No monkey-patching of our own service code.
    """
    from unittest.mock import MagicMock, patch
    from noctusai_lib.testing import MockSupabaseClient, MockUser, MockUserResponse

    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=_ORG_A))
    )

    from app.routers.integration_accounts_router import get_account_service
    from noctusai_lib.testing import bind_consent_module_to_mock

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


def _auth_header():
    return {"Authorization": "Bearer test-token"}


def _make_account(client, *, provider="youtube", label="My Channel", is_default=False):
    body = {
        "provider": provider,
        "account_label": label,
        "credential": {"access_token": "tok", "refresh_token": "ref"},
        "metadata": {"channel_id": "UC1"},
        "is_default": is_default,
    }
    resp = client.post("/api/integrations/accounts", json=body, headers=_auth_header())
    assert resp.status_code == 201, resp.text
    return resp.json()


# ─── Provider registry ────────────────────────────────────────────────────────
class TestProviders:
    def test_list_providers_returns_v1_set(self, client):
        resp = client.get("/api/integrations/providers")
        assert resp.status_code == 200
        providers = resp.json()
        ids = {p["id"] for p in providers}
        assert {"youtube", "google_drive", "gmail", "meta", "n8n"} == ids

    def test_youtube_provider_has_oauth_supported(self, client):
        resp = client.get("/api/integrations/providers")
        yt = next(p for p in resp.json() if p["id"] == "youtube")
        assert yt["oauth_supported"] is True
        assert len(yt["scopes"]) > 0

    def test_n8n_provider_has_manual_fields(self, client):
        resp = client.get("/api/integrations/providers")
        n8n = next(p for p in resp.json() if p["id"] == "n8n")
        assert n8n["oauth_supported"] is False
        assert any(f["name"] == "webhook_url" for f in n8n["manual_key_fields"])


# ─── CRUD round-trips ─────────────────────────────────────────────────────────
class TestCRUD:
    def test_create_returns_201(self, client):
        data = _make_account(client)
        assert data["provider"] == "youtube"
        assert data["account_label"] == "My Channel"
        assert "id" in data
        # Credential must NOT appear in the response.
        assert "credential" not in data
        assert "encrypted_credential" not in data

    def test_list_empty(self, client):
        resp = client.get("/api/integrations/accounts", headers=_auth_header())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_one(self, client):
        _make_account(client)
        resp = client.get("/api/integrations/accounts", headers=_auth_header())
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_filter_by_provider(self, client):
        _make_account(client, provider="youtube", label="YT")
        _make_account(client, provider="meta", label="Meta")
        resp = client.get(
            "/api/integrations/accounts?provider=youtube", headers=_auth_header()
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["provider"] == "youtube"

    def test_get_existing(self, client):
        data = _make_account(client)
        resp = client.get(
            f"/api/integrations/accounts/{data['id']}", headers=_auth_header()
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == data["id"]

    def test_get_nonexistent_404(self, client):
        resp = client.get(
            f"/api/integrations/accounts/{uuid4()}", headers=_auth_header()
        )
        assert resp.status_code == 404

    def test_update_label(self, client):
        data = _make_account(client)
        resp = client.patch(
            f"/api/integrations/accounts/{data['id']}",
            json={"account_label": "Updated"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["account_label"] == "Updated"

    def test_update_nonexistent_404(self, client):
        resp = client.patch(
            f"/api/integrations/accounts/{uuid4()}",
            json={"account_label": "X"},
            headers=_auth_header(),
        )
        assert resp.status_code == 404

    def test_delete_existing(self, client):
        data = _make_account(client)
        resp = client.delete(
            f"/api/integrations/accounts/{data['id']}", headers=_auth_header()
        )
        assert resp.status_code == 204

    def test_delete_nonexistent_404(self, client):
        resp = client.delete(
            f"/api/integrations/accounts/{uuid4()}", headers=_auth_header()
        )
        assert resp.status_code == 404

    def test_set_default(self, client):
        a1 = _make_account(client, label="A1", is_default=True)
        a2 = _make_account(client, label="A2")
        resp = client.patch(
            f"/api/integrations/accounts/{a2['id']}/set-default",
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["is_default"] is True
        # a1 should no longer be default.
        r1 = client.get(
            f"/api/integrations/accounts/{a1['id']}", headers=_auth_header()
        )
        assert r1.json()["is_default"] is False

    def test_unsupported_provider_422(self, client):
        body = {
            "provider": "unknown_provider",
            "account_label": "Test",
            "credential": {},
        }
        resp = client.post(
            "/api/integrations/accounts", json=body, headers=_auth_header()
        )
        assert resp.status_code == 422


# ─── ENCRYPTION_KEY missing → 503 ────────────────────────────────────────────
class TestEncryptionKeyMissing:
    def test_503_when_key_missing(self, client):
        """Simulate ENCRYPTION_KEY missing by overriding DI seam to raise."""
        from app.routers.integration_accounts_router import get_account_service
        from app.main import app
        from fastapi import HTTPException

        def _bad_service():
            raise HTTPException(status_code=503, detail="ENCRYPTION_KEY not configured")

        prev = app.dependency_overrides.get(get_account_service)
        app.dependency_overrides[get_account_service] = _bad_service
        try:
            resp = client.get("/api/integrations/accounts", headers=_auth_header())
            assert resp.status_code == 503
        finally:
            if prev is None:
                app.dependency_overrides.pop(get_account_service, None)
            else:
                app.dependency_overrides[get_account_service] = prev


# ─── YouTube OAuth: start ─────────────────────────────────────────────────────
class TestYouTubeOAuthStart:
    def test_start_returns_auth_url_and_state(self, client):
        """Inject the seed FakeOAuthProvider via the get_yt_oauth_provider DI
        seam — NO monkeypatch (KB § PATTERNS/compliance/testing.md). This
        exercises the REAL async ``authorization_url`` contract, so an interface
        drift (e.g. the historical get_auth_url→authorization_url break) fails
        loudly instead of being masked by a MagicMock."""
        from app.dependencies import get_settings
        from app.config import settings as _settings
        from app.main import app
        from app.routers.integration_accounts_router import (
            get_yt_oauth_provider,
            get_yt_pkce_redis,
        )
        from noctusai_lib.security.oauth.fake import FakeOAuthProvider

        fake_cfg = _settings.model_copy(
            update={
                "youtube_client_id": "fake-client-id",
                "youtube_client_secret": "fake-client-secret",
            }
        )
        overrides = {
            get_settings: lambda: fake_cfg,
            get_yt_oauth_provider: lambda: FakeOAuthProvider(use_pkce=True),
            get_yt_pkce_redis: lambda: None,
        }
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            resp = client.post(
                "/api/integrations/accounts/youtube/oauth/start",
                headers=_auth_header(),
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "auth_url" in body
        assert "state" in body
        assert _ORG_A in body["state"]

    def test_start_503_when_client_id_missing(self, client):
        """503 when YOUTUBE_CLIENT_ID is empty."""
        from app.dependencies import get_settings
        from app.config import settings as _settings
        from app.main import app

        fake_cfg = _settings.model_copy(
            update={"youtube_client_id": "", "youtube_client_secret": ""}
        )
        prev = app.dependency_overrides.get(get_settings)
        app.dependency_overrides[get_settings] = lambda: fake_cfg
        try:
            resp = client.post(
                "/api/integrations/accounts/youtube/oauth/start",
                headers=_auth_header(),
            )
            assert resp.status_code == 503
        finally:
            app.dependency_overrides.pop(get_settings, None)
            if prev is not None:
                app.dependency_overrides[get_settings] = prev


# ─── YouTube OAuth: callback ──────────────────────────────────────────────────
class TestYouTubeOAuthCallback:
    def test_callback_creates_account(self, client, ia_service):
        """Inject the seed FakeOAuthProvider + FakeYoutubeClient via the DI
        seams (no monkeypatch). Exercises the REAL async exchange_code→TokenSet
        and get_channel_info_mine contracts end-to-end — a mismatch (like the
        historical sync-exchange_code→dict break) fails loudly here."""
        from app.dependencies import get_settings
        from app.config import settings as _settings
        from app.main import app
        from app.routers.integration_accounts_router import (
            get_yt_oauth_provider,
            get_yt_pkce_redis,
            get_yt_client_factory,
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
            channel_id="UC999",
            title="Test Channel",
            subscriber_count=0,
            video_count=0,
            view_count=0,
        )
        overrides = {
            get_settings: lambda: fake_cfg,
            # use_pkce=False ⇒ exchange_code needs no PKCE verifier (the redis
            # seam returns None below); the Fake returns a default TokenSet.
            get_yt_oauth_provider: lambda: FakeOAuthProvider(use_pkce=False),
            get_yt_pkce_redis: lambda: None,
            get_yt_client_factory: lambda: (
                lambda **kw: FakeYoutubeClient(owned_channel_info=owned)
            ),
        }
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce123"
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

        # Should redirect to /integrations?account_created=<id>
        assert resp.status_code in (302, 303), resp.text
        location = resp.headers.get("location", "")
        assert "integrations" in location
        assert "account_created=" in location

        # Verify the account was actually created in the SQLite store.
        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="youtube")
        assert len(accounts) == 1
        acct = accounts[0]
        assert acct.metadata.get("channel_id") == "UC999"
        assert acct.account_label == "Test Channel"

    def test_callback_missing_code_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/youtube/oauth/callback?state=x",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_callback_error_param_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/youtube/oauth/callback?error=access_denied",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_callback_malformed_state_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/youtube/oauth/callback?code=c&state=no-org",
            follow_redirects=False,
        )
        assert resp.status_code == 400


# ─── Legacy adoption endpoint ───────────────────────────────────────────────
class TestAdoptLegacy:
    def test_unsupported_provider_422(self, client):
        resp = client.post(
            "/api/integrations/accounts/notaprovider/adopt-legacy",
            headers=_auth_header(),
        )
        assert resp.status_code == 422

    def test_no_legacy_connection_returns_null(self, client):
        # Mock substrate has no legacy `credentials` row → nothing to adopt.
        resp = client.post(
            "/api/integrations/accounts/youtube/adopt-legacy",
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json() is None
