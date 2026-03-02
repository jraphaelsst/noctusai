"""
Tests for API Keys Router.

GET    /api/api-keys           (org scoped)
POST   /api/api-keys           (org scoped)
PATCH  /api/api-keys/{id}
DELETE /api/api-keys/{id}
GET    /api/admin/api-keys     (admin only)
"""
import pytest


# ---------------------------------------------------------------------------
# GET /api/api-keys
# ---------------------------------------------------------------------------

class TestListApiKeys:
    def test_list_api_keys_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("api_keys", [
            {
                "id": "key-1",
                "org_id": "org-1",
                "name": "My API Key",
                "key_prefix": "noctus_k_abc123",
                "scopes": ["read"],
                "is_active": True,
            },
        ])

        resp = client.get("/api/api-keys")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 1

    def test_list_api_keys_empty(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("api_keys", [])

        resp = client.get("/api/api-keys")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_api_keys_profile_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = client.get("/api/api-keys")
        assert resp.status_code == 404

    def test_list_api_keys_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/api-keys")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/api-keys
# ---------------------------------------------------------------------------

class TestCreateApiKey:
    def test_create_api_key_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("api_keys", [
            {
                "id": "key-new",
                "org_id": "org-1",
                "name": "New Key",
                "key_prefix": "noctus_k_xyz",
                "scopes": ["read", "write"],
                "is_active": True,
                "created_by": "test-user-123",
            }
        ])

        resp = client.post("/api/api-keys", json={
            "name": "New Key",
            "scopes": ["read", "write"],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "raw_key" in data
        assert data["raw_key"].startswith("noctus_k_")
        assert data["name"] == "New Key"

    def test_create_api_key_default_scopes(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("api_keys", [
            {
                "id": "key-new",
                "org_id": "org-1",
                "name": "Default Scopes Key",
                "key_prefix": "noctus_k_abc",
                "scopes": ["read"],
                "is_active": True,
                "created_by": "test-user-123",
            }
        ])

        resp = client.post("/api/api-keys", json={
            "name": "Default Scopes Key",
        })
        assert resp.status_code == 200

    def test_create_api_key_missing_name(self, client):
        resp = client.post("/api/api-keys", json={})
        assert resp.status_code == 422

    def test_create_api_key_profile_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = client.post("/api/api-keys", json={"name": "Key"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/api-keys/{id}
# ---------------------------------------------------------------------------

class TestUpdateApiKey:
    def test_update_api_key_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("api_keys", [
            {"id": "key-1", "name": "Updated Key", "scopes": ["read", "write"]},
        ])

        resp = client.patch("/api/api-keys/key-1", json={
            "name": "Updated Key",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Updated Key"

    def test_update_api_key_empty_body(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})

        resp = client.patch("/api/api-keys/key-1", json={})
        assert resp.status_code == 400

    def test_update_api_key_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("api_keys", [])

        resp = client.patch("/api/api-keys/nonexistent", json={
            "name": "New Name",
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/api-keys/{id}
# ---------------------------------------------------------------------------

class TestRevokeApiKey:
    def test_revoke_api_key_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("api_keys", [
            {"id": "key-1", "is_active": False},
        ])

        resp = client.delete("/api/api-keys/key-1")
        assert resp.status_code == 200

    def test_revoke_api_key_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("api_keys", [])

        resp = client.delete("/api/api-keys/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/admin/api-keys (admin only)
# ---------------------------------------------------------------------------

class TestAdminListApiKeys:
    def test_admin_list_api_keys_success(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("api_keys", [
            {"id": "key-1", "org_id": "org-1", "name": "Key 1"},
            {"id": "key-2", "org_id": "org-2", "name": "Key 2"},
        ])

        resp = admin_client.get("/api/admin/api-keys")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 2

    def test_admin_list_api_keys_forbidden_for_non_admin(self, client):
        resp = client.get("/api/admin/api-keys")
        assert resp.status_code == 403

    def test_admin_list_api_keys_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/admin/api-keys")
        assert resp.status_code == 401
