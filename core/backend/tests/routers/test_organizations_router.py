"""
Tests for Organizations Router.

GET    /api/organizations
GET    /api/organizations/{id}
PATCH  /api/organizations/{id}
"""
import pytest
from tests.conftest import MockQueryBuilder


# ---------------------------------------------------------------------------
# GET /api/organizations
# ---------------------------------------------------------------------------

class TestListOrganizations:
    def test_list_as_admin_returns_all(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "org_id": "org-1",
            "role": "admin",
        })
        mock_sb.set_table_data("organizations", [
            {"id": "org-1", "nome": "Org A"},
            {"id": "org-2", "nome": "Org B"},
        ])

        resp = client.get("/api/organizations")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_list_as_user_returns_own(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "org_id": "org-1",
            "role": "user",
        })
        mock_sb.set_table_data("organizations", [
            {"id": "org-1", "nome": "My Org"},
        ])

        resp = client.get("/api/organizations")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_list_profile_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = client.get("/api/organizations")
        assert resp.status_code == 404

    def test_list_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/organizations")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/organizations/{id}
# ---------------------------------------------------------------------------

class TestGetOrganization:
    def test_get_org_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("organizations", {
            "id": "org-1",
            "nome": "Test Corp",
            "plano": "free",
        })

        resp = client.get("/api/organizations/org-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "org-1"

    def test_get_org_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("organizations", None)

        resp = client.get("/api/organizations/nonexistent")
        assert resp.status_code == 404

    def test_get_org_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/organizations/org-1")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/organizations/{id}
# ---------------------------------------------------------------------------

class TestUpdateOrganization:
    def test_update_org_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("organizations", [
            {"id": "org-1", "nome": "Updated Corp", "plano": "pro"},
        ])

        resp = client.patch("/api/organizations/org-1", json={
            "nome": "Updated Corp",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nome"] == "Updated Corp"

    def test_update_org_empty_body(self, client):
        resp = client.patch("/api/organizations/org-1", json={})
        assert resp.status_code == 400

    def test_update_org_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("organizations", [])

        resp = client.patch("/api/organizations/nonexistent", json={
            "nome": "New Name",
        })
        assert resp.status_code == 404

    def test_update_org_invalid_category(self, client):
        resp = client.patch("/api/organizations/org-1", json={
            "category": "invalid_category",
        })
        assert resp.status_code == 422

    def test_update_org_valid_category(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("organizations", [
            {"id": "org-1", "nome": "Corp", "category": "test"},
        ])

        resp = client.patch("/api/organizations/org-1", json={
            "category": "test",
        })
        assert resp.status_code == 200

    def test_update_org_unauthenticated(self, unauth_client):
        resp = unauth_client.patch("/api/organizations/org-1", json={"nome": "X"})
        assert resp.status_code == 401
