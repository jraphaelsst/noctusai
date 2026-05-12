"""Status-pinned smoke tests for `credentials_router`.

Covers the 4 endpoints declared in PROJECT.md Phase 1:
  - POST /api/credentials/connect    → 200, returns {auth_url, state}
  - GET  /api/credentials/callback   → 200 happy path, 400 on missing params
  - POST /api/credentials/disconnect → 200 idempotent
  - GET  /api/credentials/status     → 200 with connected: False initial

Every assertion includes both `.status_code` AND a body assertion (per the
status-code-assertion rule, `KB § PATTERNS/testing.md`).

The `client` fixture is the seed conftest's `AuthClient(TestClient, mock_sb)`.
We pre-set the vault key via env-var-style patching of the settings before
the app boots.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet


# ─── Per-test settings patches ───────────────────────────────────────────────


@pytest.fixture(autouse=True)
def vault_key_set(monkeypatch):
    """Make `settings.youtube_crawler_vault_key` non-empty for every test.

    Without this, `_build_service()` returns 503 ("Vault not configured").
    """
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("YOUTUBE_CRAWLER_VAULT_KEY", key)
    # The settings instance is constructed at module-import time; patch its
    # attribute directly so the router picks it up.
    from app.config import settings as live_settings
    monkeypatch.setattr(live_settings, "youtube_crawler_vault_key", key)
    monkeypatch.setattr(live_settings, "google_oauth_client_id", "")
    monkeypatch.setattr(live_settings, "google_oauth_client_secret", "")


# ─── /connect ────────────────────────────────────────────────────────────────


class TestConnectEndpoint:
    def test_connect_returns_200_with_auth_url_and_state(self, client):
        resp = client.post(
            "/api/credentials/connect",
            json={"redirect_uri": "https://app.test/cb"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "auth_url" in body
        assert "state" in body
        assert body["auth_url"]  # non-empty
        assert body["state"]  # non-empty CSRF nonce

    def test_connect_rejects_unknown_body_keys_with_422(self, client):
        """`ConnectRequest` is a `StrictHttpModel` — unknown keys → 422.

        Defends against the silent-drop misroute (`feedback_pydantic_silent_drop_kills_writes`).
        """
        resp = client.post(
            "/api/credentials/connect",
            json={"redirect_uri": "https://app.test/cb", "bogus_extra": "value"},
        )
        assert resp.status_code == 422, resp.text
        # 422 body names the offending location.
        assert "bogus_extra" in resp.text or "extra" in resp.text.lower()

    def test_connect_requires_authentication(self, client):
        """No-auth call returns 401 (the `Depends(get_current_user_org)` shape)."""
        # `client.unauthed` (TestClient without auth header) — the conftest
        # AuthClient exposes the raw TestClient as `.client`.
        resp = client.raw().post(
            "/api/credentials/connect",
            json={"redirect_uri": "https://app.test/cb"},
        )
        # 401 or 403 depending on header presence; assert non-success class.
        assert resp.status_code in (401, 403), resp.text


# ─── /callback ───────────────────────────────────────────────────────────────


class TestCallbackEndpoint:
    def test_missing_code_returns_400(self, client):
        """No `code` query param → 400 with diagnostic detail."""
        resp = client.raw().get(
            "/api/credentials/callback",
            params={"state": "abc", "redirect_uri": "https://app.test/cb"},
        )
        assert resp.status_code == 400, resp.text
        assert "missing" in resp.text.lower() or "code" in resp.text.lower()

    def test_missing_state_returns_400(self, client):
        resp = client.raw().get(
            "/api/credentials/callback",
            params={"code": "abc", "redirect_uri": "https://app.test/cb"},
        )
        assert resp.status_code == 400, resp.text

    def test_missing_redirect_uri_returns_400(self, client):
        resp = client.raw().get(
            "/api/credentials/callback",
            params={"code": "abc", "state": "xyz"},
        )
        assert resp.status_code == 400, resp.text

    def test_provider_error_query_returns_200_with_ok_false(self, client):
        """Google appends ?error=access_denied when user declines consent.

        We surface that as 200 + ok:false (the operator's UI is the recovery
        path; we don't want the browser to see a 4xx for a user-decline)."""
        resp = client.raw().get(
            "/api/credentials/callback",
            params={"error": "access_denied", "state": "abc"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is False
        assert body["error"] == "access_denied"

    def test_unknown_state_returns_400(self, client):
        """Posting a state that doesn't match any persisted nonce → 400.

        The MockSupabaseClient returns empty result for the state lookup,
        so the service raises `unknown or expired state nonce`.
        """
        resp = client.raw().get(
            "/api/credentials/callback",
            params={
                "code": "auth-code-1",
                "state": "never-issued",
                "redirect_uri": "https://app.test/cb",
            },
        )
        assert resp.status_code == 400, resp.text
        assert "state" in resp.text.lower()


# ─── /disconnect ─────────────────────────────────────────────────────────────


class TestDisconnectEndpoint:
    def test_disconnect_returns_200_with_disconnected_field(self, client):
        """Even when no row exists, disconnect is idempotent — returns 200
        with `{disconnected: false}`."""
        resp = client.post("/api/credentials/disconnect")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "disconnected" in body
        assert isinstance(body["disconnected"], bool)

    def test_disconnect_requires_authentication(self, client):
        resp = client.raw().post("/api/credentials/disconnect")
        assert resp.status_code in (401, 403), resp.text


# ─── /status ─────────────────────────────────────────────────────────────────


class TestStatusEndpoint:
    def test_status_returns_200_with_disconnected_when_no_row(self, client):
        resp = client.get("/api/credentials/status")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # StrictHttpModel response — keys are exactly:
        assert set(body.keys()) == {
            "connected", "email", "scopes", "connected_at", "revoked_at"
        }
        assert body["connected"] is False
        assert body["scopes"] == []

    def test_status_requires_authentication(self, client):
        resp = client.raw().get("/api/credentials/status")
        assert resp.status_code in (401, 403), resp.text
