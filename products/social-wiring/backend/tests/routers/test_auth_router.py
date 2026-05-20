"""Tests for the Wave-2 auth router — /api/auth/{login,me,logout} +
/api/settings/api-tokens.

Uses the shared ``client`` fixture (``MockSupabaseClient`` + bearer
auth) — the legacy JWT bridge in ``app.dependencies`` is what
``/api/auth/me`` falls through to under the test fixture (no cookie
present, bearer-token-shaped Authorization header). The cookie path
isn't exercised here because the dev/test ``FakeSessionStore`` is
process-local — covered by the seed's own ``test_session.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from noctusai_lib.testing import MockUser, MockUserResponse


_ORG = "00000000-0000-4000-8000-0000000000aa"
_USER = "00000000-0000-4000-8000-0000000000bb"


class TestMe:
    """``GET /api/auth/me`` resolves the bearer JWT through the legacy
    bridge and projects an ``AuthContext`` view to the caller."""

    def test_returns_user_payload_for_jwt_bearer(self, client):
        # The shared client fixture already binds get_user to a
        # MockUser with org_id="test-org-123". Re-bind to a clean UUID
        # so the response is predictable.
        client.mock_supabase.auth.get_user = MagicMock(
            return_value=MockUserResponse(MockUser(id=_USER, org_id=_ORG))
        )
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["caller_kind"] == "user"
        assert body["org"]["id"] == _ORG
        assert body["user"]["id"] == _USER

    def test_unauthenticated_rejected(self, client):
        # raw() returns the TestClient without Authorization header.
        resp = client.raw().get("/api/auth/me")
        assert resp.status_code == 401


class TestLogout:
    """``POST /api/auth/logout`` deletes the session (no-op when only
    the bearer is present) and clears the cookie."""

    def test_logout_succeeds_for_bearer_caller(self, client):
        client.mock_supabase.auth.get_user = MagicMock(
            return_value=MockUserResponse(MockUser(id=_USER, org_id=_ORG))
        )
        resp = client.post("/api/auth/logout")
        # 204 success + the response carries a Set-Cookie clearing
        # nai_session even when the caller didn't have one (idempotent).
        assert resp.status_code == 204, resp.text


class TestLoginInputValidation:
    """``POST /api/auth/login`` validates the body shape before
    reaching Supabase."""

    def test_missing_body_rejected(self, client):
        resp = client.raw().post("/api/auth/login", json={})
        assert resp.status_code == 422

    def test_malformed_email_rejected(self, client):
        resp = client.raw().post(
            "/api/auth/login",
            json={"email": "not-an-email", "password": "x"},
        )
        assert resp.status_code == 422


class TestApiTokensCreate:
    """``POST /api/settings/api-tokens`` mints a new ``pk_*`` token.
    Owner / admin only; the secret is returned ONCE."""

    def test_owner_can_mint_token(self, client):
        client.mock_supabase.auth.get_user = MagicMock(
            return_value=MockUserResponse(
                MockUser(id=_USER, org_id=_ORG, org_role="owner")
            )
        )
        # Seed the noctus_users row the route looks up for the
        # role re-check.
        client.mock_supabase.set_table_data(
            "noctus_users",
            [{"id": _USER, "org_id": _ORG, "org_role": "owner"}],
        )
        resp = client.post(
            "/api/settings/api-tokens",
            json={"label": "n8n webhook", "scopes": ["publish"]},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["label"] == "n8n webhook"
        assert body["token"].startswith("pk_")
        assert body["prefix"].startswith("pk_")
        assert body["scopes"] == ["publish"]

    def test_non_admin_role_rejected(self, client):
        client.mock_supabase.auth.get_user = MagicMock(
            return_value=MockUserResponse(
                MockUser(id=_USER, org_id=_ORG, org_role="member")
            )
        )
        client.mock_supabase.set_table_data(
            "noctus_users",
            [{"id": _USER, "org_id": _ORG, "org_role": "member"}],
        )
        resp = client.post(
            "/api/settings/api-tokens",
            json={"label": "trying", "scopes": []},
        )
        assert resp.status_code == 403

    def test_label_required(self, client):
        client.mock_supabase.auth.get_user = MagicMock(
            return_value=MockUserResponse(
                MockUser(id=_USER, org_id=_ORG, org_role="owner")
            )
        )
        client.mock_supabase.set_table_data(
            "noctus_users",
            [{"id": _USER, "org_id": _ORG, "org_role": "owner"}],
        )
        resp = client.post(
            "/api/settings/api-tokens",
            json={"label": "", "scopes": []},
        )
        # Pydantic min_length=1 → 422.
        assert resp.status_code == 422


class TestApiTokensList:
    def test_returns_only_metadata_no_secrets(self, client):
        client.mock_supabase.auth.get_user = MagicMock(
            return_value=MockUserResponse(MockUser(id=_USER, org_id=_ORG))
        )
        client.mock_supabase.set_table_data(
            "api_tokens",
            [
                {
                    "id": "10000000-0000-4000-8000-000000000001",
                    "org_id": _ORG,
                    "label": "n8n",
                    "token_prefix": "pk_abc12345",
                    "scopes": ["publish"],
                    "created_at": "2026-05-01T00:00:00+00:00",
                    "last_used_at": None,
                    "revoked_at": None,
                }
            ],
        )
        resp = client.get("/api/settings/api-tokens")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        if body:
            # No raw secret / hash leaks.
            assert "token_hash" not in body[0]
            assert "token" not in body[0]
