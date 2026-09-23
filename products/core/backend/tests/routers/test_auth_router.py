"""
Tests for Auth Router — Login, Signup, Session.

POST  /api/auth/signup
POST  /api/auth/login
GET   /api/auth/me
POST  /api/auth/logout
"""
import pytest
from unittest.mock import MagicMock, patch
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
    def test_logout_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.auth.sign_out = MagicMock()

        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_logout_unauthenticated(self, unauth_client):
        resp = unauth_client.post("/api/auth/logout")
        assert resp.status_code == 401
