"""
Tests for Webhooks Router.

GET    /api/webhooks
POST   /api/webhooks
PATCH  /api/webhooks/{id}
DELETE /api/webhooks/{id}
GET    /api/webhooks/{id}/deliveries
"""
import pytest


# ---------------------------------------------------------------------------
# GET /api/webhooks
# ---------------------------------------------------------------------------

class TestListWebhooks:
    def test_list_webhooks_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("webhook_endpoints", [
            {
                "id": "wh-1",
                "org_id": "org-1",
                "url": "https://example.com/webhook",
                "is_active": True,
            },
        ])

        resp = client.get("/api/webhooks")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 1

    def test_list_webhooks_empty(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("webhook_endpoints", [])

        resp = client.get("/api/webhooks")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_webhooks_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/webhooks")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/webhooks
# ---------------------------------------------------------------------------

class TestCreateWebhook:
    def test_create_webhook_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("webhook_endpoints", [
            {
                "id": "wh-new",
                "org_id": "org-1",
                "url": "https://example.com/hook",
                "events": ["subscription.created"],
                "is_active": True,
            }
        ])

        resp = client.post("/api/webhooks", json={
            "url": "https://example.com/hook",
            "events": ["subscription.created"],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "signing_secret" in data
        assert data["signing_secret"].startswith("whsec_")

    def test_create_webhook_missing_url(self, client):
        resp = client.post("/api/webhooks", json={
            "events": ["subscription.created"],
        })
        assert resp.status_code == 422



# ---------------------------------------------------------------------------
# PATCH /api/webhooks/{id}
# ---------------------------------------------------------------------------

class TestUpdateWebhook:
    def test_update_webhook_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("webhook_endpoints", [
            {"id": "wh-1", "org_id": "org-1", "url": "https://updated.com/hook", "is_active": True},
        ])

        resp = client.patch("/api/webhooks/wh-1", json={
            "url": "https://updated.com/hook",
        })
        assert resp.status_code == 200

    def test_update_webhook_empty_body(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})

        resp = client.patch("/api/webhooks/wh-1", json={})
        assert resp.status_code == 400

    def test_update_webhook_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("webhook_endpoints", [])

        resp = client.patch("/api/webhooks/nonexistent", json={
            "url": "https://new.com/hook",
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/webhooks/{id}
# ---------------------------------------------------------------------------

class TestDeleteWebhook:
    def test_delete_webhook_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("webhook_endpoints", [
            {"id": "wh-1"},
        ])

        resp = client.delete("/api/webhooks/wh-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["deleted"] is True

    def test_delete_webhook_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("webhook_endpoints", [])

        resp = client.delete("/api/webhooks/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/webhooks/{id}/deliveries
# ---------------------------------------------------------------------------

class TestListDeliveries:
    def test_list_deliveries_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("webhook_endpoints", [{"id": "wh-1"}])
        mock_sb.set_table_data("webhook_deliveries", [
            {
                "id": "del-1",
                "endpoint_id": "wh-1",
                "event_type": "subscription.created",
                "status": "success",
            },
        ])

        resp = client.get("/api/webhooks/wh-1/deliveries")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "total" in data
        assert "page" in data

    def test_list_deliveries_endpoint_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("webhook_endpoints", [])

        resp = client.get("/api/webhooks/nonexistent/deliveries")
        assert resp.status_code == 404

    def test_list_deliveries_with_pagination(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("webhook_endpoints", [{"id": "wh-1"}])
        mock_sb.set_table_data("webhook_deliveries", [])

        resp = client.get("/api/webhooks/wh-1/deliveries?page=2&page_size=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["page_size"] == 5
