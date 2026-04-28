"""
Tests for Analytics Router (admin only).

GET /api/admin/analytics/overview
GET /api/admin/analytics/revenue
GET /api/admin/analytics/tenants
"""
import pytest


# ---------------------------------------------------------------------------
# GET /api/admin/analytics/overview
# ---------------------------------------------------------------------------

class TestAnalyticsOverview:
    def test_overview_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("organizations", [{"id": "org-1"}, {"id": "org-2"}])
        mock_sb.set_table_data("noctus_users", [{"id": "u1"}, {"id": "u2"}])
        mock_sb.set_table_data("subscriptions", [
            {"id": "sub-1", "plan_id": "plan-1", "status": "active"},
        ])
        mock_sb.set_table_data("plans", [
            {"id": "plan-1", "price_monthly": 99},
        ])

        resp = admin_client.get("/api/admin/analytics/overview")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "mrr" in data
        assert "total_orgs" in data
        assert "active_orgs" in data
        assert "total_users" in data
        assert "churn_rate" in data

    def test_overview_forbidden_for_non_admin(self, client):
        resp = client.get("/api/admin/analytics/overview")
        assert resp.status_code == 403

    def test_overview_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/admin/analytics/overview")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/analytics/revenue
# ---------------------------------------------------------------------------

class TestAnalyticsRevenue:
    def test_revenue_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("subscriptions", [])
        mock_sb.set_table_data("plans", [])

        resp = admin_client.get("/api/admin/analytics/revenue")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_revenue_forbidden_for_non_admin(self, client):
        resp = client.get("/api/admin/analytics/revenue")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/admin/analytics/tenants
# ---------------------------------------------------------------------------

class TestAnalyticsTenants:
    def test_tenants_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("organizations", [
            {"id": "org-1", "nome": "Corp A", "slug": "corp-a", "created_at": "2025-01-01"},
        ])
        mock_sb.set_table_data("noctus_users", [
            {"id": "u1", "org_id": "org-1"},
        ])
        mock_sb.set_table_data("subscriptions", [])

        resp = admin_client.get("/api/admin/analytics/tenants")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["org_id"] == "org-1"
        assert data[0]["user_count"] == 1

    def test_tenants_forbidden_for_non_admin(self, client):
        resp = client.get("/api/admin/analytics/tenants")
        assert resp.status_code == 403
