"""
Tests for Notifications Router.

GET   /api/notifications
GET   /api/notifications/unread-count
PATCH /api/notifications/read-all
PATCH /api/notifications/{id}/read
"""
import pytest


# ---------------------------------------------------------------------------
# GET /api/notifications
# ---------------------------------------------------------------------------

class TestListNotifications:
    def test_list_notifications_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("notifications", [
            {
                "id": "n1",
                "user_id": "test-user-123",
                "title": "Welcome!",
                "read": False,
            },
        ])

        resp = client.get("/api/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_list_notifications_empty(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("notifications", [])

        resp = client.get("/api/notifications")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_notifications_with_pagination(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("notifications", [
            {"id": "n1", "title": "Notification 1"},
        ])

        resp = client.get("/api/notifications?page=2&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["page_size"] == 10

    def test_list_notifications_invalid_page(self, client):
        resp = client.get("/api/notifications?page=0")
        assert resp.status_code == 422

    def test_list_notifications_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/notifications")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/notifications/unread-count
# ---------------------------------------------------------------------------

class TestUnreadCount:
    def test_unread_count_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("notifications", [
            {"id": "n1"},
            {"id": "n2"},
        ])

        resp = client.get("/api/notifications/unread-count")
        assert resp.status_code == 200
        data = resp.json()
        assert "unread_count" in data

    def test_unread_count_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/notifications/unread-count")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/notifications/read-all
# ---------------------------------------------------------------------------

class TestMarkAllRead:
    def test_mark_all_read_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("notifications", [
            {"id": "n1", "read": True},
            {"id": "n2", "read": True},
        ])

        resp = client.patch("/api/notifications/read-all")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "updated" in data

    def test_mark_all_read_none_unread(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("notifications", [])

        resp = client.patch("/api/notifications/read-all")
        assert resp.status_code == 200
        assert resp.json()["data"]["updated"] == 0


# ---------------------------------------------------------------------------
# PATCH /api/notifications/{id}/read
# ---------------------------------------------------------------------------

class TestMarkOneRead:
    def test_mark_one_read_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("notifications", [
            {"id": "n1", "read": True, "title": "Test"},
        ])

        resp = client.patch("/api/notifications/n1/read")
        assert resp.status_code == 200

    def test_mark_one_read_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("notifications", [])

        resp = client.patch("/api/notifications/nonexistent/read")
        assert resp.status_code == 404

    def test_mark_one_read_unauthenticated(self, unauth_client):
        resp = unauth_client.patch("/api/notifications/n1/read")
        assert resp.status_code == 401
