"""
Tests for OAuth Router.

GET  /api/auth/oauth/providers
POST /api/auth/oauth/callback
"""
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# GET /api/auth/oauth/providers
# ---------------------------------------------------------------------------

class TestListProviders:
    def test_list_providers_returns_enabled(self, client):
        resp = client.get("/api/auth/oauth/providers")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        # Google and Azure should be listed
        provider_ids = [p["id"] for p in data]
        assert "google" in provider_ids
        assert "azure" in provider_ids

    def test_list_providers_contains_auth_urls(self, client):
        resp = client.get("/api/auth/oauth/providers")
        assert resp.status_code == 200
        for provider in resp.json()["data"]:
            assert "auth_url" in provider
            assert "authorize" in provider["auth_url"]


# ---------------------------------------------------------------------------
# POST /api/auth/oauth/callback
# ---------------------------------------------------------------------------

class TestOAuthCallback:
    def test_callback_existing_user(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", [
            {
                "id": "test-user-123",
                "org_id": "org-1",
                "role": "user",
                "nome": "Test User",
            }
        ])
        mock_sb.set_table_data("organizations", {
            "id": "org-1",
            "nome": "Test Org",
        })

        resp = client.post("/api/auth/oauth/callback", json={
            "provider": "google",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_new"] is False
        assert data["user"]["id"] == "test-user-123"

    def test_callback_new_user_creates_profile(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", [])
        mock_sb.set_table_data("organizations", [
            {"id": "new-org-1", "nome": "Org de Test"},
        ])
        mock_sb.set_table_data("plans", [{"id": "free-plan", "slug": "free"}])
        mock_sb.set_table_data("subscriptions", [])

        resp = client.post("/api/auth/oauth/callback", json={
            "provider": "google",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_new"] is True

    def test_callback_missing_provider(self, client):
        resp = client.post("/api/auth/oauth/callback", json={})
        assert resp.status_code == 422

    def test_callback_unauthenticated(self, unauth_client):
        resp = unauth_client.post("/api/auth/oauth/callback", json={
            "provider": "google",
        })
        assert resp.status_code == 401
