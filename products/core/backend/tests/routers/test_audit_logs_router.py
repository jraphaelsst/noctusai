"""
Tests for Audit Logs Router.

GET /api/audit-logs              (org scoped)
GET /api/admin/audit-logs        (admin only)
"""
import pytest


# ---------------------------------------------------------------------------
# GET /api/audit-logs
# ---------------------------------------------------------------------------

class TestListAuditLogs:
    def test_list_audit_logs_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("audit_logs", [
            {
                "id": "log-1",
                "org_id": "org-1",
                "action": "create",
                "resource_type": "license",
                "created_at": "2026-01-15T10:00:00Z",
            },
        ])

        resp = client.get("/api/audit-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_list_audit_logs_empty(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("audit_logs", [])

        resp = client.get("/api/audit-logs")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_audit_logs_with_filters(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("audit_logs", [
            {"id": "log-1", "action": "create", "resource_type": "user"},
        ])

        resp = client.get("/api/audit-logs?action=create&resource_type=user")
        assert resp.status_code == 200

    def test_list_audit_logs_with_pagination(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("audit_logs", [])

        resp = client.get("/api/audit-logs?page=3&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 3
        assert data["page_size"] == 10

    def test_list_audit_logs_invalid_page(self, client):
        resp = client.get("/api/audit-logs?page=0")
        assert resp.status_code == 422

    def test_list_audit_logs_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/audit-logs")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/audit-logs (admin only)
# ---------------------------------------------------------------------------

class TestAdminListAuditLogs:
    def test_admin_list_audit_logs_success(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("audit_logs", [
            {
                "id": "log-1",
                "org_id": "org-1",
                "action": "create",
                "resource_type": "subscription",
            },
            {
                "id": "log-2",
                "org_id": "org-2",
                "action": "delete",
                "resource_type": "license",
            },
        ])

        resp = admin_client.get("/api/admin/audit-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "total" in data

    def test_admin_list_with_filters(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("audit_logs", [])

        resp = admin_client.get("/api/admin/audit-logs?action=delete&resource_type=user")
        assert resp.status_code == 200

    def test_admin_list_with_pagination(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("audit_logs", [])

        resp = admin_client.get("/api/admin/audit-logs?page=2&page_size=50")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["page_size"] == 50

    def test_admin_list_forbidden_for_non_admin(self, client):
        resp = client.get("/api/admin/audit-logs")
        assert resp.status_code == 403

    def test_admin_list_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/admin/audit-logs")
        assert resp.status_code == 401
