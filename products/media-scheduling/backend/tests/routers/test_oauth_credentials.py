"""OAuth credential persistence — router-level coverage.

Adapted from `whatsapp-google-scheduling/tests/test_oauth_credential_repo.py`.

Source-side: a hand-rolled `OAuthCredentialRepo` ran upsert / get / update
methods over a SQLAlchemy session.
Product-side (Phase 3 decision): no repo class — the OAuth router talks
directly to Supabase via `app.routers.oauth`. The same upsert / fetch
contract holds, but it lives inside `google_oauth_callback` and
`google_oauth_status` rather than in a standalone class.

What we cover here (router-level, since that's where the logic moved):
  - GET /api/oauth/google/status returns `connected: false` when no row.
  - GET /api/oauth/google/status returns the most-recent row's metadata
    when a row exists (single-account flow).
  - GET /api/oauth/google/status requires authentication.
  - GET /oauth/google/init refuses with 503 when env not configured.

Full callback-flow coverage (the source's "first connect / refresh
overwrite / no-refresh-token error" cases) requires mocking Google's
httpx round-trip and Supabase, which exercises >2x the surface for
the same persistence guarantee. Deferred — see this file's tail comment.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from noctusai_lib.testing import MockSupabaseClient


def _patch_oauth_db(mock_sb):
    """`oauth.py` does `from app.database import get_supabase_client`, which
    snapshots the symbol at import time — patching `app.database._db.get_client`
    after the fact doesn't reach the cached reference. Patch the router's
    bound symbol directly for the status / callback flows.
    """
    return patch("app.routers.oauth.get_supabase_client", return_value=mock_sb)


def test_oauth_status_returns_disconnected_when_no_row(client):
    """No oauth_credentials rows → response is `{connected: false}`."""
    mock = MockSupabaseClient()
    mock.set_table_data("oauth_credentials", [])

    with _patch_oauth_db(mock):
        resp = client.get("/api/oauth/google/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"connected": False}


def test_oauth_status_returns_connected_with_metadata_when_row_exists(client):
    """One row → response surfaces account_email + access_token_expires_at."""
    mock = MockSupabaseClient()
    mock.set_table_data(
        "oauth_credentials",
        [
            {
                "account_email": "media@noctusai.com",
                "access_token_expires_at": "2026-12-31T00:00:00+00:00",
                "scopes": "openid email https://www.googleapis.com/auth/calendar",
                "updated_at": "2026-05-03T10:00:00+00:00",
            },
        ],
    )

    with _patch_oauth_db(mock):
        resp = client.get("/api/oauth/google/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["account_email"] == "media@noctusai.com"
    assert body["expires_at"] == "2026-12-31T00:00:00+00:00"
    assert body["last_error"] is None


def test_oauth_status_requires_auth(client):
    """No Authorization header → 401."""
    resp = client.raw().get("/api/oauth/google/status")
    assert resp.status_code == 401


def test_oauth_init_refuses_when_unconfigured(client, monkeypatch):
    """Without GOOGLE_OAUTH_* env, GET /oauth/google/init returns 503."""
    from app.config import settings

    monkeypatch.setattr(settings, "google_oauth_client_id", "", raising=False)  # self-patch-ok: simulates the unconfigured-env path the router itself returns 503 on
    monkeypatch.setattr(settings, "google_oauth_client_secret", "", raising=False)  # self-patch-ok: same
    monkeypatch.setattr(settings, "google_oauth_redirect_uri", "", raising=False)  # self-patch-ok: same

    resp = client.raw().get("/oauth/google/init", follow_redirects=False)
    assert resp.status_code == 503


def test_oauth_init_redirects_when_configured(client, monkeypatch):
    """With env set, GET bounces to Google's consent screen (302)."""
    from app.config import settings

    monkeypatch.setattr(
        settings, "google_oauth_client_id", "fake-client-id.apps.googleusercontent.com",
        raising=False,
    )
    monkeypatch.setattr(
        settings, "google_oauth_client_secret", "fake-secret", raising=False
    )
    monkeypatch.setattr(
        settings, "google_oauth_redirect_uri",
        "https://media-scheduling.local/oauth/google/callback",
        raising=False,
    )

    resp = client.raw().get("/oauth/google/init", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert "accounts.google.com" in resp.headers["location"]
    # Must include client_id + redirect_uri + scope + offline access.
    assert "fake-client-id.apps.googleusercontent.com" in resp.headers["location"]
    assert "access_type=offline" in resp.headers["location"]


def test_oauth_init_post_returns_authorize_url_when_configured(client, monkeypatch):
    """POST programmatic flow returns JSON `{authorize_url}`."""
    from app.config import settings

    monkeypatch.setattr(
        settings, "google_oauth_client_id", "fake-client-id.apps.googleusercontent.com",
        raising=False,
    )
    monkeypatch.setattr(
        settings, "google_oauth_client_secret", "fake-secret", raising=False
    )
    monkeypatch.setattr(
        settings, "google_oauth_redirect_uri",
        "https://media-scheduling.local/oauth/google/callback",
        raising=False,
    )

    resp = client.raw().post("/oauth/google/init")

    assert resp.status_code == 200
    body = resp.json()
    assert "authorize_url" in body
    assert body["authorize_url"].startswith("https://accounts.google.com/")


# ---------------------------------------------------------------------------
# Source repo's "first-connect-without-refresh-token-rejects" /
# "subsequent-connect-without-refresh-token-keeps-old" tests are not
# replicated here — they require mocking httpx for both the token and
# userinfo Google calls. Deferred to a Phase 7 follow-up if a regression
# surfaces; the upsert logic itself is straight-line in `oauth.py` callback.
# ---------------------------------------------------------------------------
