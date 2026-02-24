"""
Tests for Plans Router.

GET    /api/plans          (authenticated)
GET    /api/plans/{id}     (authenticated)
POST   /api/plans          (admin only)
PATCH  /api/plans/{id}     (admin only)
DELETE /api/plans/{id}     (admin only)
"""
import pytest


# ---------------------------------------------------------------------------
# GET /api/plans
# ---------------------------------------------------------------------------

class TestListPlans:
    def test_list_plans_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("plans", [
            {"id": "plan-1", "name": "Free", "slug": "free", "price_monthly": 0},
            {"id": "plan-2", "name": "Pro", "slug": "pro", "price_monthly": 99},
        ])

        resp = client.get("/api/plans")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 2

    def test_list_plans_empty(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("plans", [])

        resp = client.get("/api/plans")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_plans_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/plans")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/plans/{id}
# ---------------------------------------------------------------------------

class TestGetPlan:
    def test_get_plan_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("plans", {
            "id": "plan-1",
            "name": "Pro",
            "slug": "pro",
            "price_monthly": 99,
        })

        resp = client.get("/api/plans/plan-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Pro"

    def test_get_plan_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("plans", None)

        resp = client.get("/api/plans/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/plans (admin only)
# ---------------------------------------------------------------------------

class TestCreatePlan:
    def test_create_plan_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("plans", [
            {
                "id": "new-plan",
                "name": "Enterprise",
                "slug": "enterprise",
                "price_monthly": 299,
                "is_active": True,
            }
        ])

        resp = admin_client.post("/api/plans", json={
            "name": "Enterprise",
            "slug": "enterprise",
            "price_monthly": 299,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Enterprise"

    def test_create_plan_forbidden_for_non_admin(self, client):
        resp = client.post("/api/plans", json={
            "name": "Enterprise",
            "slug": "enterprise",
        })
        assert resp.status_code == 403

    def test_create_plan_missing_required_fields(self, admin_client):
        resp = admin_client.post("/api/plans", json={
            "name": "Incomplete",
        })
        assert resp.status_code == 422

    def test_create_plan_negative_price(self, admin_client):
        resp = admin_client.post("/api/plans", json={
            "name": "Bad Plan",
            "slug": "bad",
            "price_monthly": -10,
        })
        assert resp.status_code == 422

    def test_create_plan_unauthenticated(self, unauth_client):
        resp = unauth_client.post("/api/plans", json={
            "name": "Test",
            "slug": "test",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/plans/{id} (admin only)
# ---------------------------------------------------------------------------

class TestUpdatePlan:
    def test_update_plan_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("plans", [
            {"id": "plan-1", "name": "Pro Updated", "price_monthly": 149},
        ])

        resp = admin_client.patch("/api/plans/plan-1", json={
            "name": "Pro Updated",
            "price_monthly": 149,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Pro Updated"

    def test_update_plan_forbidden_for_non_admin(self, client):
        resp = client.patch("/api/plans/plan-1", json={"name": "Updated"})
        assert resp.status_code == 403

    def test_update_plan_empty_body(self, admin_client):
        resp = admin_client.patch("/api/plans/plan-1", json={})
        assert resp.status_code == 400

    def test_update_plan_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("plans", [])

        resp = admin_client.patch("/api/plans/nonexistent", json={
            "name": "Updated",
        })
        assert resp.status_code == 404

    def test_update_plan_negative_price(self, admin_client):
        resp = admin_client.patch("/api/plans/plan-1", json={
            "price_monthly": -5,
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/plans/{id} (admin only — soft delete)
# ---------------------------------------------------------------------------

class TestDeletePlan:
    def test_delete_plan_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("plans", [
            {"id": "plan-1", "is_active": False},
        ])

        resp = admin_client.delete("/api/plans/plan-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_active"] is False

    def test_delete_plan_forbidden_for_non_admin(self, client):
        resp = client.delete("/api/plans/plan-1")
        assert resp.status_code == 403

    def test_delete_plan_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("plans", [])

        resp = admin_client.delete("/api/plans/nonexistent")
        assert resp.status_code == 404
