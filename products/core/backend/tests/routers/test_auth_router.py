"""
Tests for Auth Router — Login, Signup, Session.

POST  /api/auth/signup
POST  /api/auth/login
GET   /api/auth/me
POST  /api/auth/logout
"""
import pytest
from unittest.mock import MagicMock, patch
from gotrue.errors import AuthApiError, AuthRetryableError
from tests.conftest import MockUser, MockUserResponse, MockQueryBuilder


# ---------------------------------------------------------------------------
# POST /api/auth/signup
# ---------------------------------------------------------------------------

class TestSignup:
    def test_signup_success(self, client):
        mock_sb = client.mock_supabase

        # Mock: auth.admin.create_user returns a user
        mock_auth_user = MockUser(id="new-user-id", email="new@example.com")
        mock_auth_response = MagicMock()
        mock_auth_response.user = mock_auth_user
        mock_sb.auth.admin.create_user = MagicMock(return_value=mock_auth_response)

        # Mock: org insert returns created org
        mock_sb.set_table_data("organizations", [{"id": "org-1", "nome": "Test Corp"}])
        mock_sb.set_table_data("noctus_users", [])

        resp = client.post("/api/auth/signup", json={
            "nome": "Test User",
            "email": "new@example.com",
            "password": "password123",
            "empresa": "Test Corp",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert data["data"]["user_id"] == "new-user-id"

    def test_signup_missing_fields(self, client):
        resp = client.post("/api/auth/signup", json={
            "nome": "Test",
            "email": "test@test.com",
        })
        assert resp.status_code == 422

    def test_signup_empty_body(self, client):
        resp = client.post("/api/auth/signup", json={})
        assert resp.status_code == 422


class TestSignupGate:
    """Website `signup_enabled` switch (contract §6, §10)."""

    def test_open_when_website_settings_never_configured(self, client):
        # No `website_settings` row at all AND no FE-built defaults file on
        # this test run — `WebsiteDefaultsMissing` must NOT block signup.
        mock_sb = client.mock_supabase
        mock_auth_user = MockUser(id="new-user-id", email="new@example.com")
        mock_auth_response = MagicMock()
        mock_auth_response.user = mock_auth_user
        mock_sb.auth.admin.create_user = MagicMock(return_value=mock_auth_response)
        mock_sb.set_table_data("website_settings", [])
        mock_sb.set_table_data("organizations", [{"id": "org-1", "nome": "Test Corp"}])
        mock_sb.set_table_data("noctus_users", [])

        resp = client.post("/api/auth/signup", json={
            "nome": "Test User", "email": "new@example.com",
            "password": "password123", "empresa": "Test Corp",
        })
        assert resp.status_code == 200

    def test_closed_returns_403_signup_closed(self, client, website_site):
        from tests.conftest import website_defaults_dict

        mock_sb = client.mock_supabase
        closed = {**website_defaults_dict(), "signup_enabled": False}
        mock_sb.set_table_data("website_settings", [{"version": 1, "data": closed}])

        resp = client.post("/api/auth/signup", json={
            "nome": "Test User", "email": "blocked@example.com",
            "password": "password123", "empresa": "Test Corp",
        })
        assert resp.status_code == 403
        assert resp.json()["detail"] == "signup_closed"

    def test_open_when_signup_enabled_true(self, client, website_site):
        mock_sb = client.mock_supabase
        mock_auth_user = MockUser(id="new-user-id", email="new@example.com")
        mock_auth_response = MagicMock()
        mock_auth_response.user = mock_auth_user
        mock_sb.auth.admin.create_user = MagicMock(return_value=mock_auth_response)
        mock_sb.set_table_data("website_settings", [])
        mock_sb.set_table_data("organizations", [{"id": "org-1", "nome": "Test Corp"}])
        mock_sb.set_table_data("noctus_users", [])

        resp = client.post("/api/auth/signup", json={
            "nome": "Test User", "email": "new@example.com",
            "password": "password123", "empresa": "Test Corp",
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self, client):
        mock_sb = client.mock_supabase

        mock_session = MagicMock()
        mock_session.access_token = "access-token-abc"
        mock_session.refresh_token = "refresh-token-xyz"
        mock_login_user = MagicMock()
        mock_login_user.id = "user-123"
        mock_login_user.email = "test@example.com"

        mock_response = MagicMock()
        mock_response.session = mock_session
        mock_response.user = mock_login_user
        mock_sb.auth.sign_in_with_password = MagicMock(return_value=mock_response)

        resp = client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "access-token-abc"
        assert data["refresh_token"] == "refresh-token-xyz"
        assert data["user"]["id"] == "user-123"

    def test_login_invalid_credentials(self, client):
        mock_sb = client.mock_supabase
        mock_sb.auth.sign_in_with_password = MagicMock(
            side_effect=Exception("Invalid login credentials")
        )

        resp = client.post("/api/auth/login", json={
            "email": "bad@example.com",
            "password": "wrong",
        })
        assert resp.status_code == 401

    def test_login_missing_fields(self, client):
        resp = client.post("/api/auth/login", json={"email": "test@test.com"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------

class TestGetMe:
    def test_get_me_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "email": "test@example.com",
            "nome": "Test User",
            "org_id": "org-1",
            "role": "admin",
        })
        mock_sb.set_table_data("organizations", {
            "id": "org-1",
            "nome": "Test Corp",
        })
        mock_sb.set_table_data("licenses", [])
        mock_sb.set_table_data("products", [])

        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert "user" in data
        assert "organization" in data
        # Website contract §3/§6: the FE auth-context needs `role` (e.g.
        # 'marketing') visible here — already true (profile is `SELECT *`),
        # pinned as a regression guard.
        assert data["user"]["role"] == "admin"

    def test_get_me_profile_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = client.get("/api/auth/me")
        assert resp.status_code == 404

    def test_get_me_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/auth/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/auth/logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_revokes_every_session_with_the_users_jwt(self, client):
        from app.routers import sso as sso_module

        admin_sign_out = MagicMock()
        client.mock_supabase.auth.admin.sign_out = admin_sign_out
        sso_module._session_cache.clear()
        sso_module._session_cache.set(
            sso_module._ScopedSSOSessionCache.scoped_key("test@example.com", "org-1", "p1"),
            {"access_token": "cached"},
        )

        resp = client.post("/api/auth/logout", headers={"Authorization": "Bearer t"})

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        # The caller's access token (not the user id) and the GLOBAL scope.
        admin_sign_out.assert_called_once_with("test-token-valid", scope="global")
        # Cached per-product SSO sessions of that user are flushed.
        assert sso_module._session_cache._store == {}

    def test_logout_revocation_failure_is_not_ok(self, client, caplog):
        client.mock_supabase.auth.admin.sign_out = MagicMock(side_effect=RuntimeError("gotrue down"))
        with caplog.at_level("ERROR"):
            resp = client.post("/api/auth/logout", headers={"Authorization": "Bearer t"})
        assert resp.status_code == 502
        assert resp.json().get("ok") is not True
        assert "global sign_out failed" in caplog.text

    def test_logout_ends_every_org_selection(self, client):
        mock_sb = client.mock_supabase
        mock_sb.auth.admin.sign_out = MagicMock()
        mock_sb.set_rpc_data("platform_org_selection_end", 1)

        resp = client.post("/api/auth/logout", headers={"Authorization": "Bearer t"})
        assert resp.status_code == 200
        assert mock_sb.rpc_calls == [
            ("platform_org_selection_end", {"p_user_id": "test-user-123", "p_reason": "logout"})
        ]

    def test_logout_still_ok_when_ending_selections_fails(self, client, caplog):
        mock_sb = client.mock_supabase
        mock_sb.auth.admin.sign_out = MagicMock()

        def boom(name, params=None):
            raise RuntimeError("db down")

        mock_sb.rpc = boom
        with caplog.at_level("ERROR"):
            resp = client.post("/api/auth/logout", headers={"Authorization": "Bearer t"})
        assert resp.status_code == 200
        assert "could not end org selections" in caplog.text

    def test_logout_unauthenticated(self, unauth_client):
        resp = unauth_client.post("/api/auth/logout")
        assert resp.status_code == 401


class TestChangePasswordRevokesOtherSessions:
    def test_passes_the_jwt_with_scope_others(self, client):
        admin = client.mock_supabase.auth.admin
        admin.update_user_by_id = MagicMock()
        admin.sign_out = MagicMock()
        resp = client.post(
            "/api/auth/change-password",
            json={"new_password": "longenough1"},
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 200
        admin.sign_out.assert_called_once_with("test-token-valid", scope="others")
        assert resp.json()["other_sessions_revoked"] is True

    def test_revocation_failure_is_surfaced_not_swallowed(self, client, caplog):
        admin = client.mock_supabase.auth.admin
        admin.update_user_by_id = MagicMock()
        admin.sign_out = MagicMock(side_effect=RuntimeError("boom"))
        with caplog.at_level("ERROR"):
            resp = client.post(
                "/api/auth/change-password",
                json={"new_password": "longenough1"},
                headers={"Authorization": "Bearer t"},
            )
        assert resp.status_code == 200
        assert resp.json()["other_sessions_revoked"] is False
        assert "could not revoke other sessions" in caplog.text


# ---------------------------------------------------------------------------
# POST /api/auth/refresh — 401 only when Supabase rejected the refresh token
# ---------------------------------------------------------------------------

class TestRefreshDistinguishesOutageFromDeadSession:
    """The core SPA logs the user out when /api/auth/refresh answers 401, so
    that status must mean "this refresh token is dead" — never "Supabase was
    unreachable for a moment" (2026-10-03: forced re-logins after deploys).
    gotrue wraps transport failures + Auth 502/503/504 into
    `AuthRetryableError`; those used to fall under `except Exception -> 401`.
    """

    def test_refresh_success(self, client):
        mock_sb = client.mock_supabase
        session = MagicMock(access_token="new-access", refresh_token="new-refresh")
        mock_sb.auth.refresh_session = MagicMock(
            return_value=MagicMock(session=session, user=None)
        )
        resp = client.post("/api/auth/refresh", json={"refresh_token": "r"})
        assert resp.status_code == 200
        assert resp.json() == {"access_token": "new-access", "refresh_token": "new-refresh"}

    @pytest.mark.parametrize("exc", [
        AuthRetryableError("Connection refused", 0),
        AuthRetryableError("Bad Gateway", 502),
        AuthApiError("Internal", 500, None),
        AuthApiError("rate", 429, None),
    ], ids=["conn-refused", "502", "api-500", "api-429"])
    def test_supabase_not_answering_is_503_not_401(self, client, exc):
        client.mock_supabase.auth.refresh_session = MagicMock(side_effect=exc)
        resp = client.post("/api/auth/refresh", json={"refresh_token": "r"})
        assert resp.status_code == 503
        assert resp.headers.get("retry-after") == "2"

    def test_rejected_refresh_token_is_401(self, client):
        client.mock_supabase.auth.refresh_session = MagicMock(
            side_effect=AuthApiError("Invalid Refresh Token: Already Used", 400, "refresh_token_already_used")
        )
        resp = client.post("/api/auth/refresh", json={"refresh_token": "r"})
        assert resp.status_code == 401
