"""Tests for the Usage Reporting router."""
import pytest


class TestGetAllUsage:
    """GET /api/admin/usage — admin-only."""

    def test_admin_can_list_usage(self, admin_client):
        admin_client.mock_supabase.set_table_data("product_usage", [
            {"id": "u1", "org_id": "o1", "product_id": "p1", "metric": "active_users_30d", "value": 5},
            {"id": "u2", "org_id": "o1", "product_id": "p1", "metric": "total_records", "value": 150},
        ])
        resp = admin_client.get("/api/admin/usage")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_non_admin_forbidden(self, client):
        resp = client.get("/api/admin/usage")
        assert resp.status_code == 403

    def test_empty_usage_returns_empty_list(self, admin_client):
        admin_client.mock_supabase.set_table_data("product_usage", [])
        resp = admin_client.get("/api/admin/usage")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestGetOrgUsage:
    """GET /api/admin/usage/{org_id} — admin-only, org-scoped."""

    def test_admin_can_get_org_usage(self, admin_client):
        admin_client.mock_supabase.set_table_data("product_usage", [
            {"id": "u1", "org_id": "org-123", "metric": "total_records", "value": 42},
        ])
        resp = admin_client.get("/api/admin/usage/org-123")
        assert resp.status_code == 200

    def test_non_admin_forbidden(self, client):
        resp = client.get("/api/admin/usage/org-123")
        assert resp.status_code == 403


class TestGetMyUsage:
    """GET /api/usage/me — authenticated user, own org."""

    def test_user_can_see_own_usage(self, client):
        client.mock_supabase.set_table_data("product_usage", [
            {"id": "u1", "org_id": "test-org-123", "metric": "active_users_30d", "value": 3},
        ])
        resp = client.get("/api/usage/me")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_unauthenticated_returns_401(self, client):
        resp = client.raw().get("/api/usage/me")
        assert resp.status_code == 401


class TestTriggerSnapshot:
    """POST /api/admin/usage/snapshot — admin-only manual trigger."""

    def test_admin_can_trigger_snapshot(self, admin_client):
        resp = admin_client.post("/api/admin/usage/snapshot")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_non_admin_forbidden(self, client):
        resp = client.post("/api/admin/usage/snapshot")
        assert resp.status_code == 403
