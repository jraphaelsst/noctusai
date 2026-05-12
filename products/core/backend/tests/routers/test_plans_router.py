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
            {"id": "plan-1", "nome": "Free", "slug": "free", "price_monthly": 0, "ativo": True},
            {"id": "plan-2", "nome": "Pro", "slug": "pro", "price_monthly": 99, "ativo": True},
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
            "nome": "Pro",
            "slug": "pro",
            "price_monthly": 99,
        })

        resp = client.get("/api/plans/plan-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nome"] == "Pro"

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
        # First execute: slug duplicate check → empty (no conflict)
        # Second execute: insert result
        mock_sb.set_table_responses("plans", [
            [],
            [
                {
                    "id": "new-plan",
                    "nome": "Enterprise",
                    "slug": "enterprise",
                    "price_monthly": 299,
                    "ativo": True,
                }
            ],
        ])

        resp = admin_client.post("/api/plans", json={
            "nome": "Enterprise",
            "slug": "enterprise",
            "price_monthly": 299,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nome"] == "Enterprise"

    def test_create_plan_forbidden_for_non_admin(self, client):
        resp = client.post("/api/plans", json={
            "nome": "Enterprise",
            "slug": "enterprise",
        })
        assert resp.status_code == 403

    def test_create_plan_missing_required_fields(self, admin_client):
        resp = admin_client.post("/api/plans", json={
            "nome": "Incomplete",
        })
        assert resp.status_code == 422

    def test_create_plan_negative_price(self, admin_client):
        resp = admin_client.post("/api/plans", json={
            "nome": "Bad Plan",
            "slug": "bad",
            "price_monthly": -10,
        })
        assert resp.status_code == 422

    def test_create_plan_unauthenticated(self, unauth_client):
        resp = unauth_client.post("/api/plans", json={
            "nome": "Test",
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
            {"id": "plan-1", "nome": "Pro Updated", "price_monthly": 149},
        ])

        resp = admin_client.patch("/api/plans/plan-1", json={
            "nome": "Pro Updated",
            "price_monthly": 149,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nome"] == "Pro Updated"

    def test_update_plan_forbidden_for_non_admin(self, client):
        resp = client.patch("/api/plans/plan-1", json={"nome": "Updated"})
        assert resp.status_code == 403

    def test_update_plan_empty_body(self, admin_client):
        resp = admin_client.patch("/api/plans/plan-1", json={})
        assert resp.status_code == 400

    def test_update_plan_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("plans", [])

        resp = admin_client.patch("/api/plans/nonexistent", json={
            "nome": "Updated",
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
            {"id": "plan-1", "ativo": False},
        ])

        resp = admin_client.delete("/api/plans/plan-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["ativo"] is False

    def test_delete_plan_forbidden_for_non_admin(self, client):
        resp = client.delete("/api/plans/plan-1")
        assert resp.status_code == 403

    def test_delete_plan_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("plans", [])

        resp = admin_client.delete("/api/plans/nonexistent")
        assert resp.status_code == 404
