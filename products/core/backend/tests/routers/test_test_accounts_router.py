"""
Tests for Test Accounts Router (admin only).

POST   /api/admin/test-accounts
GET    /api/admin/test-accounts
DELETE /api/admin/test-accounts/{org_id}
"""
import pytest
from unittest.mock import MagicMock
from tests.conftest import MockUser


# ---------------------------------------------------------------------------
# POST /api/admin/test-accounts
# ---------------------------------------------------------------------------

class TestCreateTestAccount:
    def test_create_test_account_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase

        # Mock auth.admin.create_user
        mock_auth_user = MockUser(id="test-acct-user", email="test-acct@example.com")
        mock_auth_response = MagicMock()
        mock_auth_response.user = mock_auth_user
        mock_sb.auth.admin.create_user = MagicMock(return_value=mock_auth_response)

        mock_sb.set_table_data("organizations", [
            {"id": "test-org-1", "nome": "Test Company"},
        ])
        mock_sb.set_table_data("noctus_users", [])
        mock_sb.set_table_data("products", [
            {"id": "prod-1"},
            {"id": "prod-2"},
        ])
        mock_sb.set_table_data("licenses", [])
        mock_sb.set_table_data("plans", [
            {"id": "plan-enterprise", "price_monthly": 299},
        ])
        mock_sb.set_table_data("subscriptions", [])

        resp = admin_client.post("/api/admin/test-accounts", json={
            "nome": "Test Account User",
            "email": "test-acct@example.com",
            "password": "password123",
            "empresa": "Test Company",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == "test-acct-user"
        assert data["category"] == "test"

    def test_create_test_account_forbidden_for_non_admin(self, client):
        resp = client.post("/api/admin/test-accounts", json={
            "nome": "Test",
            "email": "test@test.com",
            "password": "password123",
            "empresa": "Test Corp",
        })
        assert resp.status_code == 403

    def test_create_test_account_missing_fields(self, admin_client):
        resp = admin_client.post("/api/admin/test-accounts", json={
            "nome": "Test",
            "email": "test@test.com",
        })
        assert resp.status_code == 422

    def test_create_test_account_password_too_short(self, admin_client):
        resp = admin_client.post("/api/admin/test-accounts", json={
            "nome": "Test",
            "email": "test@test.com",
            "password": "abc",
            "empresa": "Corp",
        })
        assert resp.status_code == 422

    def test_create_test_account_unauthenticated(self, unauth_client):
        resp = unauth_client.post("/api/admin/test-accounts", json={
            "nome": "Test",
            "email": "test@test.com",
            "password": "password123",
            "empresa": "Corp",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/test-accounts
# ---------------------------------------------------------------------------

class TestListTestAccounts:
    def test_list_test_accounts_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("organizations", [
            {"id": "org-1", "nome": "Test Corp 1", "category": "test"},
            {"id": "org-2", "nome": "Test Corp 2", "category": "test"},
        ])

        resp = admin_client.get("/api/admin/test-accounts")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_list_test_accounts_forbidden_for_non_admin(self, client):
        resp = client.get("/api/admin/test-accounts")
        assert resp.status_code == 403

    def test_list_test_accounts_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/admin/test-accounts")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/admin/test-accounts/{org_id}
# ---------------------------------------------------------------------------

class TestDeactivateTestAccount:
    def test_deactivate_test_account_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("organizations", {
            "id": "test-org-1",
            "category": "test",
        })
        mock_sb.set_table_data("licenses", [])
        mock_sb.set_table_data("subscriptions", [])

        resp = admin_client.delete("/api/admin/test-accounts/test-org-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "deactivated"

    def test_deactivate_test_account_not_test_org(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("organizations", {
            "id": "normal-org",
            "category": "normal",
        })

        resp = admin_client.delete("/api/admin/test-accounts/normal-org")
        assert resp.status_code == 400

    def test_deactivate_test_account_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("organizations", None)

        resp = admin_client.delete("/api/admin/test-accounts/nonexistent")
        assert resp.status_code == 404

    def test_deactivate_test_account_forbidden_for_non_admin(self, client):
        resp = client.delete("/api/admin/test-accounts/org-1")
        assert resp.status_code == 403
