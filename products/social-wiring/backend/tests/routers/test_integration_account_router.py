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
    provider            TEXT NOT NULL CHECK (provider IN ('youtube', 'google_drive', 'gmail', 'meta', 'n8n', 'instagram')),
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
        assert {
            "youtube",
            "google_drive",
            "gmail",
            "meta",
            "instagram",
            "n8n",
        } == ids

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

        # Should redirect to /clientes?account_created=<id>
        assert resp.status_code in (302, 303), resp.text
        location = resp.headers.get("location", "")
        assert "clientes" in location
        assert "account_created=" in location

        # Verify the account was actually created in the SQLite store.
        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="youtube")
        assert len(accounts) == 1
        acct = accounts[0]
        assert acct.metadata.get("channel_id") == "UC999"
        assert acct.account_label == "Test Channel"

    def test_callback_reconnect_same_channel_is_idempotent(self, client, ia_service):
        """Re-connecting the SAME channel RE-AUTHENTICATES the existing account
        instead of inserting a duplicate (which hit UNIQUE(org, provider,
        account_label) → CONFLICT "Registro duplicado"). Two callbacks for the
        same channel_id ⇒ exactly ONE account. This is the de-hardcode fix that
        makes the legacy auto-adopted account fully UI-manageable."""
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
            channel_id="UC_SAME",
            title="Same Channel",
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
        }
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce-reconnect"
            for _ in range(2):  # connect the SAME channel twice
                resp = client.get(
                    "/api/integrations/accounts/youtube/oauth/callback"
                    f"?code=auth-code&state={state}",
                    follow_redirects=False,
                )
                assert resp.status_code in (302, 303), resp.text
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        # Idempotent: exactly one account for the channel, no CONFLICT.
        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="youtube")
        same = [a for a in accounts if a.metadata.get("channel_id") == "UC_SAME"]
        assert len(same) == 1, f"expected 1 account for UC_SAME, got {len(same)}"

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


# ─── YouTube OAuth: client_id round-trip (migration 017) ────────────────────

_FAKE_YT_CLIENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class TestYouTubeOAuthClientId:
    """Verify that client_id threads correctly through the YouTube OAuth flow
    (migration 017): start encodes it into state, callback decodes and passes
    it to create_account.

    Uses the same DI seam pattern as TestYouTubeOAuthCallback — no monkeypatch,
    no mock of our own code.  build_client_service is called with get_admin_client()
    for the validation step; the mock admin client returns a MockSupabaseClient
    that does NOT raise on .table().select().eq().eq().execute(), so the
    validation succeeds with a stub response (empty data → None → 404 from the
    router).  We bypass the live validation by injecting a body with a UUID that
    the mock returns as non-None.
    """

    def _yt_overrides(self, app, settings_mod):
        """Build the common DI override dict for YouTube OAuth tests."""
        from app.dependencies import get_settings
        from app.routers.integration_accounts_router import (
            get_yt_oauth_provider,
            get_yt_pkce_redis,
            get_yt_client_factory,
        )
        from noctusai_lib.security.oauth.fake import FakeOAuthProvider
        from noctusai_lib.integrations.youtube import ChannelInfo
        from noctusai_lib.integrations.youtube.fake import FakeYoutubeClient

        fake_cfg = settings_mod.model_copy(
            update={
                "youtube_client_id": "fake-cid",
                "youtube_client_secret": "fake-cs",
                "frontend_base_url": "",
            }
        )
        owned = ChannelInfo(
            channel_id="UC-client-test",
            title="Client Channel",
            subscriber_count=0,
            video_count=0,
            view_count=0,
        )
        return {
            get_settings: lambda: fake_cfg,
            get_yt_oauth_provider: lambda: FakeOAuthProvider(use_pkce=False),
            get_yt_pkce_redis: lambda: None,
            get_yt_client_factory: lambda: (
                lambda **kw: FakeYoutubeClient(owned_channel_info=owned)
            ),
        }

    def test_start_state_contains_org_id(self, client):
        """POST /start without client_id → state still contains org_id (backward compat)."""
        from app.config import settings as _settings
        from app.main import app
        from app.dependencies import get_settings
        from app.routers.integration_accounts_router import (
            get_yt_oauth_provider,
            get_yt_pkce_redis,
        )
        from noctusai_lib.security.oauth.fake import FakeOAuthProvider

        fake_cfg = _settings.model_copy(
            update={
                "youtube_client_id": "fake-cid",
                "youtube_client_secret": "fake-cs",
            }
        )
        overrides = {
            get_settings: lambda: fake_cfg,
            get_yt_oauth_provider: lambda: FakeOAuthProvider(use_pkce=False),
            get_yt_pkce_redis: lambda: None,
        }
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            resp = client.post(
                "/api/integrations/accounts/youtube/oauth/start",
                headers=_auth_header(),
                # No body — backward-compatible path.
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code == 200, resp.text
        state = resp.json()["state"]
        parts = state.split(":")
        assert parts[0] == _ORG_A
        # Third part should be empty (no client_id supplied).
        assert len(parts) >= 3
        assert parts[2] == ""

    def test_callback_three_part_state_creates_account_with_client_id(
        self, client, ia_service
    ):
        """Callback with state={org}:{nonce}:{client_id} creates the account
        linked to that client_id — the third-segment round-trip."""
        from app.config import settings as _settings
        from app.main import app

        overrides = self._yt_overrides(app, _settings)
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce-client:{_FAKE_YT_CLIENT_ID}"
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
        assert str(accounts[0].client_id) == _FAKE_YT_CLIENT_ID

    def test_callback_two_part_state_creates_account_without_client_id(
        self, client, ia_service
    ):
        """Callback with old-style state={org}:{nonce} (no third part) still
        creates the account — backward-compatible, client_id=None."""
        from app.config import settings as _settings
        from app.main import app

        overrides = self._yt_overrides(app, _settings)
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce-compat"
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
        assert accounts[0].client_id is None


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


# ─── YouTube OAuth redirect retarget ─────────────────────────────────────────
class TestYouTubeRedirectClientes:
    """Verify that the YouTube callback now redirects to /clientes, not /integrations."""

    def test_callback_redirects_to_clientes(self, client, ia_service):
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
            channel_id="UC_CLIENTES",
            title="Clientes Channel",
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
        }
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce-redir"
            resp = client.get(
                "/api/integrations/accounts/youtube/oauth/callback"
                f"?code=code&state={state}",
                follow_redirects=False,
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code in (302, 303), resp.text
        location = resp.headers.get("location", "")
        assert "clientes" in location, f"expected /clientes redirect, got: {location}"
        assert "account_created=" in location


# ─── Gmail OAuth ──────────────────────────────────────────────────────────────
class TestGmailOAuthStart:
    def test_start_returns_auth_url_and_state(self, client):
        """Gmail start with FakeOAuthProvider → returns auth_url + state."""
        from app.dependencies import get_settings
        from app.config import settings as _settings
        from app.main import app
        from app.routers.integration_accounts_router import (
            get_gmail_oauth_provider,
            get_gmail_pkce_redis,
        )
        from noctusai_lib.security.oauth.fake import FakeOAuthProvider

        fake_cfg = _settings.model_copy(
            update={
                "google_oauth_client_id": "fake-google-cid",
                "google_oauth_client_secret": "fake-google-cs",
            }
        )
        overrides = {
            get_settings: lambda: fake_cfg,
            get_gmail_oauth_provider: lambda: FakeOAuthProvider(use_pkce=True),
            get_gmail_pkce_redis: lambda: None,
        }
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            resp = client.post(
                "/api/integrations/accounts/gmail/oauth/start",
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

    def test_start_503_when_google_oauth_not_configured(self, client):
        """503 when GOOGLE_OAUTH_CLIENT_ID is empty."""
        from app.dependencies import get_settings
        from app.config import settings as _settings
        from app.main import app

        fake_cfg = _settings.model_copy(
            update={"google_oauth_client_id": "", "google_oauth_client_secret": ""}
        )
        prev = app.dependency_overrides.get(get_settings)
        app.dependency_overrides[get_settings] = lambda: fake_cfg
        try:
            resp = client.post(
                "/api/integrations/accounts/gmail/oauth/start",
                headers=_auth_header(),
            )
            assert resp.status_code == 503
        finally:
            app.dependency_overrides.pop(get_settings, None)
            if prev is not None:
                app.dependency_overrides[get_settings] = prev


class TestGmailOAuthCallback:
    """Gmail callback — mirrors the YouTube callback test pattern.

    No monkeypatch: uses DI seams (get_gmail_oauth_provider, get_gmail_pkce_redis).
    Gmail has no channel info step — the callback uses a best-effort Gmail profile
    fetch (mocked away via the DI seam override path below, since the FakeOAuthProvider
    returns tokens that can't hit real Google APIs in tests).
    """

    def _gmail_overrides(self, app, settings_mod):
        from app.dependencies import get_settings
        from app.routers.integration_accounts_router import (
            get_gmail_oauth_provider,
            get_gmail_pkce_redis,
        )
        from noctusai_lib.security.oauth.fake import FakeOAuthProvider

        fake_cfg = settings_mod.model_copy(
            update={
                "google_oauth_client_id": "fake-gcid",
                "google_oauth_client_secret": "fake-gcs",
                "frontend_base_url": "",
            }
        )
        return {
            get_settings: lambda: fake_cfg,
            get_gmail_oauth_provider: lambda: FakeOAuthProvider(use_pkce=False),
            get_gmail_pkce_redis: lambda: None,
        }

    def test_callback_creates_gmail_account(self, client, ia_service):
        """Gmail callback with FakeOAuthProvider → account created with
        provider='gmail'; redirect to /clientes with account_created param.
        Gmail profile fetch fails (no real API in test) → fallback label used."""
        from app.config import settings as _settings
        from app.main import app

        overrides = self._gmail_overrides(app, _settings)
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:gmail-nonce"
            resp = client.get(
                "/api/integrations/accounts/gmail/oauth/callback"
                f"?code=gmail-code&state={state}",
                follow_redirects=False,
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code in (302, 303), resp.text
        location = resp.headers.get("location", "")
        assert "clientes" in location, f"expected /clientes redirect, got: {location}"
        assert "account_created=" in location

        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="gmail")
        assert len(accounts) == 1
        assert accounts[0].provider == "gmail"
        assert accounts[0].status == "validated"

    def test_callback_with_client_id_links_account(self, client, ia_service):
        """client_id in state is decoded and stored on the gmail account row."""
        from app.config import settings as _settings
        from app.main import app

        overrides = self._gmail_overrides(app, _settings)
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:gmail-nonce2:{_FAKE_YT_CLIENT_ID}"
            resp = client.get(
                "/api/integrations/accounts/gmail/oauth/callback"
                f"?code=gmail-code2&state={state}",
                follow_redirects=False,
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code in (302, 303), resp.text
        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="gmail")
        assert len(accounts) == 1
        assert str(accounts[0].client_id) == _FAKE_YT_CLIENT_ID

    def test_callback_missing_code_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/gmail/oauth/callback?state=x",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_callback_error_param_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/gmail/oauth/callback?error=access_denied",
            follow_redirects=False,
        )
        assert resp.status_code == 400


# ─── Google Drive OAuth ───────────────────────────────────────────────────────
class TestDriveOAuthStart:
    def test_start_returns_auth_url_and_state(self, client):
        """Drive start with FakeOAuthProvider → returns auth_url + state."""
        from app.dependencies import get_settings
        from app.config import settings as _settings
        from app.main import app
        from app.routers.integration_accounts_router import (
            get_drive_oauth_provider,
            get_drive_pkce_redis,
        )
        from noctusai_lib.security.oauth.fake import FakeOAuthProvider

        fake_cfg = _settings.model_copy(
            update={
                "google_oauth_client_id": "fake-google-cid",
                "google_oauth_client_secret": "fake-google-cs",
            }
        )
        overrides = {
            get_settings: lambda: fake_cfg,
            get_drive_oauth_provider: lambda: FakeOAuthProvider(use_pkce=True),
            get_drive_pkce_redis: lambda: None,
        }
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            resp = client.post(
                "/api/integrations/accounts/google_drive/oauth/start",
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

    def test_start_503_when_google_oauth_not_configured(self, client):
        from app.dependencies import get_settings
        from app.config import settings as _settings
        from app.main import app

        fake_cfg = _settings.model_copy(
            update={"google_oauth_client_id": "", "google_oauth_client_secret": ""}
        )
        prev = app.dependency_overrides.get(get_settings)
        app.dependency_overrides[get_settings] = lambda: fake_cfg
        try:
            resp = client.post(
                "/api/integrations/accounts/google_drive/oauth/start",
                headers=_auth_header(),
            )
            assert resp.status_code == 503
        finally:
            app.dependency_overrides.pop(get_settings, None)
            if prev is not None:
                app.dependency_overrides[get_settings] = prev


class TestDriveOAuthCallback:
    """Drive callback — same pattern as Gmail callback tests."""

    def _drive_overrides(self, app, settings_mod):
        from app.dependencies import get_settings
        from app.routers.integration_accounts_router import (
            get_drive_oauth_provider,
            get_drive_pkce_redis,
        )
        from noctusai_lib.security.oauth.fake import FakeOAuthProvider

        fake_cfg = settings_mod.model_copy(
            update={
                "google_oauth_client_id": "fake-gcid",
                "google_oauth_client_secret": "fake-gcs",
                "frontend_base_url": "",
            }
        )
        return {
            get_settings: lambda: fake_cfg,
            get_drive_oauth_provider: lambda: FakeOAuthProvider(use_pkce=False),
            get_drive_pkce_redis: lambda: None,
        }

    def test_callback_creates_drive_account(self, client, ia_service):
        """Drive callback with FakeOAuthProvider → account created with
        provider='google_drive'; redirect to /clientes."""
        from app.config import settings as _settings
        from app.main import app

        overrides = self._drive_overrides(app, _settings)
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:drive-nonce"
            resp = client.get(
                "/api/integrations/accounts/google_drive/oauth/callback"
                f"?code=drive-code&state={state}",
                follow_redirects=False,
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code in (302, 303), resp.text
        location = resp.headers.get("location", "")
        assert "clientes" in location, f"expected /clientes redirect, got: {location}"
        assert "account_created=" in location

        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="google_drive")
        assert len(accounts) == 1
        assert accounts[0].provider == "google_drive"
        assert accounts[0].status == "validated"

    def test_callback_with_client_id_links_account(self, client, ia_service):
        """client_id in state is decoded and stored on the drive account row."""
        from app.config import settings as _settings
        from app.main import app

        overrides = self._drive_overrides(app, _settings)
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:drive-nonce2:{_FAKE_YT_CLIENT_ID}"
            resp = client.get(
                "/api/integrations/accounts/google_drive/oauth/callback"
                f"?code=drive-code2&state={state}",
                follow_redirects=False,
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code in (302, 303), resp.text
        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="google_drive")
        assert len(accounts) == 1
        assert str(accounts[0].client_id) == _FAKE_YT_CLIENT_ID

    def test_callback_missing_code_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/google_drive/oauth/callback?state=x",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_callback_error_param_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/google_drive/oauth/callback?error=access_denied",
            follow_redirects=False,
        )
        assert resp.status_code == 400


# ─── Meta OAuth: per-client connection (Wave 2) ──────────────────────────────
class TestMetaOAuthStart:
    """POST /accounts/meta/oauth/start — app creds resolve via
    ``resolve_meta_app_creds`` (DB-first, env-fallback); ENCRYPTION_KEY is
    empty in this test env so the DB leg raises EncryptionNotConfigured and
    the resolver falls back to the injected settings, exercising the SAME
    env-fallback path production hits before ENCRYPTION_KEY is set."""

    @staticmethod
    def _fake_cfg(app_id="fake-app-id", app_secret="fake-app-secret"):
        from app.config import settings as _settings

        return _settings.model_copy(
            update={"meta_app_id": app_id, "meta_app_secret": app_secret}
        )

    def test_start_returns_auth_url_and_state(self, client):
        from app.dependencies import get_settings
        from app.main import app

        fake_cfg = self._fake_cfg()
        prev = app.dependency_overrides.get(get_settings)
        app.dependency_overrides[get_settings] = lambda: fake_cfg
        try:
            resp = client.post(
                "/api/integrations/accounts/meta/oauth/start",
                headers=_auth_header(),
            )
        finally:
            app.dependency_overrides.pop(get_settings, None)
            if prev is not None:
                app.dependency_overrides[get_settings] = prev

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "auth_url" in body
        assert "state" in body
        assert "facebook.com" in body["auth_url"]
        assert "client_id=fake-app-id" in body["auth_url"]
        # The Wave 2-pinned scope set — not the org-level auto-discovered set.
        for scope in (
            "instagram_basic",
            "instagram_content_publish",
            "instagram_manage_comments",
            "instagram_manage_messages",
            "instagram_manage_insights",
            "pages_show_list",
            "pages_read_engagement",
            "pages_manage_posts",
            "pages_manage_engagement",
            # Required by the IG Conversations API (DM reading) alongside
            # instagram_manage_messages — missing it caused Graph #3.
            "pages_manage_metadata",
        ):
            assert scope in body["auth_url"], scope
        # `pages_messaging` must NOT be requested — it's an Invalid Scope for
        # this use-case config (blocks the admin's OAuth) and the IG
        # conversations branch does not need it (that #200 was the Messenger
        # branch). See META_IA_OAUTH_SCOPES note.
        assert "pages_messaging" not in body["auth_url"]
        assert _ORG_A in body["state"]
        parts = body["state"].split(":")
        assert len(parts) == 3
        assert parts[2] == ""  # no client_id supplied → empty third segment

    def test_start_503_when_app_creds_missing(self, client):
        from app.dependencies import get_settings
        from app.main import app

        fake_cfg = self._fake_cfg(app_id="", app_secret="")
        prev = app.dependency_overrides.get(get_settings)
        app.dependency_overrides[get_settings] = lambda: fake_cfg
        try:
            resp = client.post(
                "/api/integrations/accounts/meta/oauth/start",
                headers=_auth_header(),
            )
            assert resp.status_code == 503
        finally:
            app.dependency_overrides.pop(get_settings, None)
            if prev is not None:
                app.dependency_overrides[get_settings] = prev

    def test_start_404_when_client_id_not_found(self, client):
        """A client_id that doesn't resolve via build_client_service (the
        mock admin client's default empty-select) 404s — never silently
        proceeds with an unvalidated FK."""
        from app.dependencies import get_settings
        from app.main import app

        fake_cfg = self._fake_cfg()
        prev = app.dependency_overrides.get(get_settings)
        app.dependency_overrides[get_settings] = lambda: fake_cfg
        try:
            resp = client.post(
                "/api/integrations/accounts/meta/oauth/start",
                json={"client_id": _FAKE_YT_CLIENT_ID},
                headers=_auth_header(),
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_settings, None)
            if prev is not None:
                app.dependency_overrides[get_settings] = prev


class TestMetaOAuthCallback:
    """GET /accounts/meta/oauth/callback — injects fake code/long-lived
    exchange callables + a fake MetaOAuthAdapter factory via the router's
    DI seams (get_meta_code_exchange / get_meta_long_lived_exchange /
    get_meta_oauth_adapter_factory), mirroring the YouTube/Gmail callback
    tests. No monkey-patching of this module's own imported symbols per
    KB § PATTERNS/compliance/testing.md."""

    @staticmethod
    def _fake_cfg():
        from app.config import settings as _settings

        return _settings.model_copy(
            update={
                "meta_app_id": "fake-app-id",
                "meta_app_secret": "fake-app-secret",
                "frontend_base_url": "",
            }
        )

    class _FakeProbeAdapter:
        """Stand-in for MetaOAuthAdapter's probe surface — no network."""

        def __init__(self, **_kw):
            pass

        def me(self):
            return {"id": "USER1", "name": "Test User"}

        def list_facebook_pages(self):
            from noctusai_lib.integrations.meta.types import FacebookPage

            return [FacebookPage(id="PAGE1", name="Test Page")]

        def list_instagram_accounts(self):
            from noctusai_lib.integrations.meta.types import InstagramAccount

            return [InstagramAccount(id="IG1", username="test_ig")]

    def _meta_overrides(self, app, settings_mod):
        """Build the common DI override dict for Meta OAuth callback tests
        (mirrors ``TestGmailOAuthCallback._gmail_overrides``): fake
        code/long-lived exchange callables + a fake adapter factory,
        injected via the router's DI seams — no monkeypatching of this
        module's own imported symbols."""
        from app.dependencies import get_settings
        from app.routers.integration_accounts_router import (
            get_meta_code_exchange,
            get_meta_long_lived_exchange,
            get_meta_oauth_adapter_factory,
        )
        from noctusai_lib.integrations.meta.types import TokenBundle

        fake_cfg = self._fake_cfg()
        return {
            get_settings: lambda: fake_cfg,
            get_meta_code_exchange: lambda: (lambda **kw: "SHORT-TOKEN"),
            get_meta_long_lived_exchange: lambda: (
                lambda **kw: TokenBundle(
                    access_token="LONG-TOKEN",
                    token_type="bearer",
                    expires_in=5184000,
                )
            ),
            get_meta_oauth_adapter_factory: lambda: (
                lambda **kw: self._FakeProbeAdapter(**kw)
            ),
        }

    def test_callback_creates_account_with_ig_label(self, client, ia_service):
        from app.config import settings as _settings
        from app.main import app

        overrides = self._meta_overrides(app, _settings)
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce123"
            resp = client.get(
                "/api/integrations/accounts/meta/oauth/callback"
                f"?code=auth-code&state={state}",
                follow_redirects=False,
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code in (302, 303), resp.text
        location = resp.headers.get("location", "")
        assert "clientes" in location
        assert "account_created=" in location

        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="meta")
        assert len(accounts) == 1
        acct = accounts[0]
        # IG account is the preferred label source when present.
        assert acct.metadata.get("channel_id") == "IG1"
        assert acct.account_label == "test_ig"
        assert acct.metadata.get("user_id") == "USER1"

    def test_callback_reconnect_same_channel_is_idempotent(self, client, ia_service):
        from app.config import settings as _settings
        from app.main import app

        overrides = self._meta_overrides(app, _settings)
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce-reconnect"
            for _ in range(2):
                resp = client.get(
                    "/api/integrations/accounts/meta/oauth/callback"
                    f"?code=auth-code&state={state}",
                    follow_redirects=False,
                )
                assert resp.status_code in (302, 303), resp.text
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="meta")
        same = [a for a in accounts if a.metadata.get("channel_id") == "IG1"]
        assert len(same) == 1, f"expected 1 account for IG1, got {len(same)}"

    def test_callback_with_client_id_links_account(self, client, ia_service):
        """State's third segment (client_id) round-trips onto the created
        account — mirrors the YouTube client_id round-trip."""
        from app.config import settings as _settings
        from app.main import app

        overrides = self._meta_overrides(app, _settings)
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce-client:{_FAKE_YT_CLIENT_ID}"
            resp = client.get(
                "/api/integrations/accounts/meta/oauth/callback"
                f"?code=auth-code&state={state}",
                follow_redirects=False,
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code in (302, 303), resp.text
        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="meta")
        assert len(accounts) == 1
        assert str(accounts[0].client_id) == _FAKE_YT_CLIENT_ID

    def test_callback_missing_code_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/meta/oauth/callback?state=x",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_callback_error_param_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/meta/oauth/callback?error=access_denied",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_callback_malformed_state_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/meta/oauth/callback?code=c&state=no-org",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_callback_503_when_app_creds_missing(self, client):
        from app.dependencies import get_settings
        from app.main import app

        fake_cfg = self._fake_cfg().model_copy(
            update={"meta_app_id": "", "meta_app_secret": ""}
        )
        prev = app.dependency_overrides.get(get_settings)
        app.dependency_overrides[get_settings] = lambda: fake_cfg
        try:
            state = f"{_ORG_A}:nonce-noapp"
            resp = client.get(
                "/api/integrations/accounts/meta/oauth/callback"
                f"?code=auth-code&state={state}",
                follow_redirects=False,
            )
            assert resp.status_code == 503
        finally:
            app.dependency_overrides.pop(get_settings, None)
            if prev is not None:
                app.dependency_overrides[get_settings] = prev


# ─── Instagram Business Login (Instagram-Login model) OAuth ─────────────────
class TestInstagramOAuthStart:
    """POST /accounts/instagram/oauth/start — the unified Meta app covers
    Instagram too, so app creds resolve via ``resolve_meta_app_creds``
    (DB-first, env-fallback); ENCRYPTION_KEY is empty in this test env so the
    DB leg raises EncryptionNotConfigured and the resolver falls back to the
    injected settings."""

    @staticmethod
    def _fake_cfg(app_id="fake-ig-app-id", app_secret="fake-ig-app-secret"):
        from app.config import settings as _settings

        return _settings.model_copy(
            update={"meta_app_id": app_id, "meta_app_secret": app_secret}
        )

    def test_start_returns_auth_url_and_state(self, client):
        from app.dependencies import get_settings
        from app.main import app

        fake_cfg = self._fake_cfg()
        prev = app.dependency_overrides.get(get_settings)
        app.dependency_overrides[get_settings] = lambda: fake_cfg
        try:
            resp = client.post(
                "/api/integrations/accounts/instagram/oauth/start",
                headers=_auth_header(),
            )
        finally:
            app.dependency_overrides.pop(get_settings, None)
            if prev is not None:
                app.dependency_overrides[get_settings] = prev

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "auth_url" in body
        assert "state" in body
        assert "www.instagram.com" in body["auth_url"]
        assert "client_id=fake-ig-app-id" in body["auth_url"]
        for scope in (
            "instagram_business_basic",
            "instagram_business_manage_messages",
        ):
            assert scope in body["auth_url"], scope
        assert _ORG_A in body["state"]
        parts = body["state"].split(":")
        assert len(parts) == 3
        assert parts[2] == ""

    def test_start_503_when_app_creds_missing(self, client):
        from app.dependencies import get_settings
        from app.main import app

        fake_cfg = self._fake_cfg(app_id="", app_secret="")
        prev = app.dependency_overrides.get(get_settings)
        app.dependency_overrides[get_settings] = lambda: fake_cfg
        try:
            resp = client.post(
                "/api/integrations/accounts/instagram/oauth/start",
                headers=_auth_header(),
            )
            assert resp.status_code == 503
        finally:
            app.dependency_overrides.pop(get_settings, None)
            if prev is not None:
                app.dependency_overrides[get_settings] = prev

    def test_start_404_when_client_id_not_found(self, client):
        from app.dependencies import get_settings
        from app.main import app

        fake_cfg = self._fake_cfg()
        prev = app.dependency_overrides.get(get_settings)
        app.dependency_overrides[get_settings] = lambda: fake_cfg
        try:
            resp = client.post(
                "/api/integrations/accounts/instagram/oauth/start",
                json={"client_id": _FAKE_YT_CLIENT_ID},
                headers=_auth_header(),
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_settings, None)
            if prev is not None:
                app.dependency_overrides[get_settings] = prev


class TestInstagramOAuthCallback:
    """GET /accounts/instagram/oauth/callback — injects fake code/long-lived
    exchange callables + a fake InstagramLoginOAuthAdapter factory via the
    router's DI seams (get_ig_code_exchange / get_ig_long_lived_exchange /
    get_instagram_oauth_adapter_factory), mirroring the Meta callback tests.
    No monkey-patching of this module's own imported symbols."""

    @staticmethod
    def _fake_cfg():
        from app.config import settings as _settings

        return _settings.model_copy(
            update={
                "meta_app_id": "fake-ig-app-id",
                "meta_app_secret": "fake-ig-app-secret",
                "frontend_base_url": "",
            }
        )

    class _FakeIgProbeAdapter:
        """Stand-in for InstagramLoginOAuthAdapter's /me probe — no network."""

        def __init__(self, *_a, **_kw):
            pass

        def me(self):
            return {"id": "IGUSER1", "username": "test_ig_user"}

    def _ig_overrides(self):
        from app.dependencies import get_settings
        from app.routers.integration_accounts_router import (
            get_ig_code_exchange,
            get_ig_long_lived_exchange,
            get_instagram_oauth_adapter_factory,
        )
        from noctusai_lib.integrations.meta._meta_api import IgLongToken, IgShortToken

        fake_cfg = self._fake_cfg()
        return {
            get_settings: lambda: fake_cfg,
            get_ig_code_exchange: lambda: (
                lambda **kw: IgShortToken(
                    access_token="IG-SHORT", user_id="IGUSER1", permissions="p1,p2"
                )
            ),
            get_ig_long_lived_exchange: lambda: (
                lambda **kw: IgLongToken(
                    access_token="IG-LONG", token_type="bearer", expires_in=5184000
                )
            ),
            get_instagram_oauth_adapter_factory: lambda: (
                lambda *a, **kw: self._FakeIgProbeAdapter(*a, **kw)
            ),
        }

    def test_callback_creates_account_with_ig_label(self, client, ia_service):
        from app.main import app

        overrides = self._ig_overrides()
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce123"
            resp = client.get(
                "/api/integrations/accounts/instagram/oauth/callback"
                f"?code=auth-code&state={state}",
                follow_redirects=False,
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code in (302, 303), resp.text
        location = resp.headers.get("location", "")
        assert "clientes" in location
        assert "account_created=" in location

        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="instagram")
        assert len(accounts) == 1
        acct = accounts[0]
        assert acct.metadata.get("channel_id") == "IGUSER1"
        assert acct.account_label == "test_ig_user"
        assert acct.metadata.get("model") == "instagram_login"

    def test_callback_reconnect_same_channel_is_idempotent(self, client, ia_service):
        from app.main import app

        overrides = self._ig_overrides()
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce-reconnect"
            for _ in range(2):
                resp = client.get(
                    "/api/integrations/accounts/instagram/oauth/callback"
                    f"?code=auth-code&state={state}",
                    follow_redirects=False,
                )
                assert resp.status_code in (302, 303), resp.text
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="instagram")
        same = [a for a in accounts if a.metadata.get("channel_id") == "IGUSER1"]
        assert len(same) == 1, f"expected 1 account for IGUSER1, got {len(same)}"

    def test_callback_with_client_id_links_account(self, client, ia_service):
        from app.main import app

        overrides = self._ig_overrides()
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce-client:{_FAKE_YT_CLIENT_ID}"
            resp = client.get(
                "/api/integrations/accounts/instagram/oauth/callback"
                f"?code=auth-code&state={state}",
                follow_redirects=False,
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code in (302, 303), resp.text
        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="instagram")
        assert len(accounts) == 1
        assert str(accounts[0].client_id) == _FAKE_YT_CLIENT_ID

    def test_callback_falls_back_to_short_token_on_long_lived_failure(
        self, client, ia_service
    ):
        """A failed long-lived exchange never blocks account creation —
        the short-lived token is persisted instead."""
        from app.main import app
        from noctusai_lib.integrations.meta._meta_api import MetaGraphError

        overrides = self._ig_overrides()

        def _boom(**kw):
            raise MetaGraphError("long-lived exchange failed", code=190)

        from app.routers.integration_accounts_router import get_ig_long_lived_exchange

        overrides[get_ig_long_lived_exchange] = lambda: _boom
        prev = {k: app.dependency_overrides.get(k) for k in overrides}
        app.dependency_overrides.update(overrides)
        try:
            state = f"{_ORG_A}:nonce-fallback"
            resp = client.get(
                "/api/integrations/accounts/instagram/oauth/callback"
                f"?code=auth-code&state={state}",
                follow_redirects=False,
            )
        finally:
            for k, p in prev.items():
                app.dependency_overrides.pop(k, None)
                if p is not None:
                    app.dependency_overrides[k] = p

        assert resp.status_code in (302, 303), resp.text
        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="instagram")
        assert len(accounts) == 1

    def test_callback_missing_code_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/instagram/oauth/callback?state=x",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_callback_error_param_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/instagram/oauth/callback?error=access_denied",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_callback_malformed_state_400(self, client):
        resp = client.get(
            "/api/integrations/accounts/instagram/oauth/callback?code=c&state=no-org",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_callback_503_when_app_creds_missing(self, client):
        from app.dependencies import get_settings
        from app.main import app

        fake_cfg = self._fake_cfg().model_copy(
            update={"meta_app_id": "", "meta_app_secret": ""}
        )
        prev = app.dependency_overrides.get(get_settings)
        app.dependency_overrides[get_settings] = lambda: fake_cfg
        try:
            state = f"{_ORG_A}:nonce-noapp"
            resp = client.get(
                "/api/integrations/accounts/instagram/oauth/callback"
                f"?code=auth-code&state={state}",
                follow_redirects=False,
            )
            assert resp.status_code == 503
        finally:
            app.dependency_overrides.pop(get_settings, None)
            if prev is not None:
                app.dependency_overrides[get_settings] = prev


class TestInstagramManualToken:
    """POST /accounts/instagram/token — manual-token fallback. Validated by
    probing ``/me`` via the ``get_instagram_oauth_adapter_factory`` DI seam;
    an invalid token 400s before anything is persisted."""

    class _FakeIgProbeAdapter:
        def __init__(self, token, *_a, **_kw):
            self._token = token

        def me(self):
            if self._token == "BAD-TOKEN":
                from noctusai_lib.integrations.meta._meta_api import MetaGraphError

                raise MetaGraphError("invalid token", code=190)
            return {"id": "IGUSER2", "username": "manual_ig_user"}

    def _override(self, app):
        from app.routers.integration_accounts_router import (
            get_instagram_oauth_adapter_factory,
        )

        prev = app.dependency_overrides.get(get_instagram_oauth_adapter_factory)
        app.dependency_overrides[get_instagram_oauth_adapter_factory] = (
            lambda: self._FakeIgProbeAdapter
        )
        return prev, get_instagram_oauth_adapter_factory

    def test_valid_token_creates_account(self, client, ia_service):
        from app.main import app

        prev, key = self._override(app)
        try:
            resp = client.post(
                "/api/integrations/accounts/instagram/token",
                json={"access_token": "GOOD-TOKEN"},
                headers=_auth_header(),
            )
        finally:
            app.dependency_overrides.pop(key, None)
            if prev is not None:
                app.dependency_overrides[key] = prev

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["provider"] == "instagram"
        assert body["account_label"] == "manual_ig_user"
        assert body["metadata"]["channel_id"] == "IGUSER2"

        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="instagram")
        assert len(accounts) == 1

    def test_invalid_token_400(self, client, ia_service):
        from app.main import app

        prev, key = self._override(app)
        try:
            resp = client.post(
                "/api/integrations/accounts/instagram/token",
                json={"access_token": "BAD-TOKEN"},
                headers=_auth_header(),
            )
        finally:
            app.dependency_overrides.pop(key, None)
            if prev is not None:
                app.dependency_overrides[key] = prev

        assert resp.status_code == 400, resp.text
        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="instagram")
        assert len(accounts) == 0

    def test_client_id_not_found_404(self, client, ia_service):
        from app.main import app

        prev, key = self._override(app)
        try:
            resp = client.post(
                "/api/integrations/accounts/instagram/token",
                json={"access_token": "GOOD-TOKEN", "client_id": _FAKE_YT_CLIENT_ID},
                headers=_auth_header(),
            )
        finally:
            app.dependency_overrides.pop(key, None)
            if prev is not None:
                app.dependency_overrides[key] = prev

        assert resp.status_code == 404, resp.text


# ─── n8n manual create with client_id round-trip ─────────────────────────────
class TestN8nClientIdRoundTrip:
    """n8n is manual-key-only (no OAuth); verify client_id persists correctly
    via the existing POST /api/integrations/accounts path.
    Also confirms 'n8n' passes the integration_accounts CHECK constraint.
    """

    def test_n8n_create_with_client_id_round_trips(self, client, ia_service):
        """Create an n8n account with a client_id; read it back and confirm the
        client_id is stored (the field survives the Pydantic → service → DB round-trip).
        No OAuth, no external call — pure CRUD validation."""
        n8n_client_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        body = {
            "provider": "n8n",
            "account_label": "N8N Main",
            "credential": {"webhook_url": "https://n8n.example.com/webhook/abc", "api_key": "n8n-key-123"},
            "client_id": n8n_client_id,
        }
        resp = client.post("/api/integrations/accounts", json=body, headers=_auth_header())
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["provider"] == "n8n"
        assert data["account_label"] == "N8N Main"
        # credential must not appear in the response (Fernet-encrypted at rest).
        assert "credential" not in data
        assert "encrypted_credential" not in data

        # Read back via the service directly to confirm client_id is stored.
        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="n8n")
        assert len(accounts) == 1
        assert str(accounts[0].client_id) == n8n_client_id

    def test_n8n_create_without_client_id(self, client, ia_service):
        """n8n without client_id also creates successfully (optional field)."""
        body = {
            "provider": "n8n",
            "account_label": "N8N Standalone",
            "credential": {"webhook_url": "https://n8n.example.com/webhook/xyz"},
        }
        resp = client.post("/api/integrations/accounts", json=body, headers=_auth_header())
        assert resp.status_code == 201, resp.text
        accounts = ia_service.list_accounts(org_id=UUID(_ORG_A), provider="n8n")
        assert len(accounts) == 1
        assert accounts[0].client_id is None
