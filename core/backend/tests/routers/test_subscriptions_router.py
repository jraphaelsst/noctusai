"""
Tests for Subscriptions Router.

GET    /api/subscriptions           (admin only)
GET    /api/subscriptions/me
GET    /api/subscriptions/org/{id}  (admin only)
POST   /api/subscriptions           (admin only)
PATCH  /api/subscriptions/{id}      (admin only)
DELETE /api/subscriptions/{id}      (admin only)
"""
import pytest


# ---------------------------------------------------------------------------
# GET /api/subscriptions (admin only)
# ---------------------------------------------------------------------------

class TestListSubscriptions:
    def test_list_subscriptions_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("subscriptions", [
            {"id": "sub-1", "org_id": "org-1", "plan_id": "plan-1", "status": "active"},
            {"id": "sub-2", "org_id": "org-2", "plan_id": "plan-2", "status": "trial"},
        ])

        resp = admin_client.get("/api/subscriptions")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 2

    def test_list_subscriptions_forbidden_for_non_admin(self, client):
        resp = client.get("/api/subscriptions")
        assert resp.status_code == 403

    def test_list_subscriptions_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/subscriptions")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/subscriptions/me
# ---------------------------------------------------------------------------

class TestGetMySubscription:
    def test_get_my_subscription_active(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("subscriptions", [
            {
                "id": "sub-1",
                "org_id": "org-1",
                "plan_id": "plan-1",
                "status": "active",
                "plans": {"id": "plan-1", "name": "Pro"},
            }
        ])

        resp = client.get("/api/subscriptions/me")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data is not None
        assert data["status"] == "active"

    def test_get_my_subscription_none(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("subscriptions", [])

        resp = client.get("/api/subscriptions/me")
        assert resp.status_code == 200
        assert resp.json()["data"] is None

    def test_get_my_subscription_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/subscriptions/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/subscriptions/org/{org_id} (admin only)
# ---------------------------------------------------------------------------

class TestGetOrgSubscription:
    def test_get_org_subscription_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("subscriptions", [
            {"id": "sub-1", "org_id": "org-1", "status": "active"},
        ])

        resp = admin_client.get("/api/subscriptions/org/org-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_get_org_subscription_forbidden_for_non_admin(self, client):
        resp = client.get("/api/subscriptions/org/org-1")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/subscriptions (admin only)
# ---------------------------------------------------------------------------

class TestCreateSubscription:
    def test_create_subscription_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("organizations", {"id": "org-1"})
        mock_sb.set_table_data("plans", {"id": "plan-1"})
        mock_sb.set_table_data("subscriptions", [
            {"id": "sub-new", "org_id": "org-1", "plan_id": "plan-1", "status": "active"},
        ])

        resp = admin_client.post("/api/subscriptions", json={
            "org_id": "org-1",
            "plan_id": "plan-1",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "active"

    def test_create_subscription_forbidden_for_non_admin(self, client):
        resp = client.post("/api/subscriptions", json={
            "org_id": "org-1",
            "plan_id": "plan-1",
        })
        assert resp.status_code == 403

    def test_create_subscription_org_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("organizations", None)

        resp = admin_client.post("/api/subscriptions", json={
            "org_id": "nonexistent",
            "plan_id": "plan-1",
        })
        assert resp.status_code == 404

    def test_create_subscription_invalid_status(self, admin_client):
        resp = admin_client.post("/api/subscriptions", json={
            "org_id": "org-1",
            "plan_id": "plan-1",
            "status": "invalid_status",
        })
        assert resp.status_code == 422

    def test_create_subscription_missing_fields(self, admin_client):
        resp = admin_client.post("/api/subscriptions", json={
            "org_id": "org-1",
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/subscriptions/{id} (admin only)
# ---------------------------------------------------------------------------

class TestUpdateSubscription:
    def test_update_subscription_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("subscriptions", [
            {"id": "sub-1", "status": "canceled"},
        ])

        resp = admin_client.patch("/api/subscriptions/sub-1", json={
            "status": "canceled",
        })
        assert resp.status_code == 200

    def test_update_subscription_forbidden_for_non_admin(self, client):
        resp = client.patch("/api/subscriptions/sub-1", json={
            "status": "canceled",
        })
        assert resp.status_code == 403

    def test_update_subscription_empty_body(self, admin_client):
        resp = admin_client.patch("/api/subscriptions/sub-1", json={})
        assert resp.status_code == 400

    def test_update_subscription_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("subscriptions", [])

        resp = admin_client.patch("/api/subscriptions/nonexistent", json={
            "status": "expired",
        })
        assert resp.status_code == 404

    def test_update_subscription_invalid_status(self, admin_client):
        resp = admin_client.patch("/api/subscriptions/sub-1", json={
            "status": "bogus",
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/subscriptions/{id} (admin only)
# ---------------------------------------------------------------------------

class TestCancelSubscription:
    def test_cancel_subscription_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("subscriptions", [
            {"id": "sub-1", "status": "canceled"},
        ])

        resp = admin_client.delete("/api/subscriptions/sub-1")
        assert resp.status_code == 200

    def test_cancel_subscription_forbidden_for_non_admin(self, client):
        resp = client.delete("/api/subscriptions/sub-1")
        assert resp.status_code == 403

    def test_cancel_subscription_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("subscriptions", [])

        resp = admin_client.delete("/api/subscriptions/nonexistent")
        assert resp.status_code == 404
