"""Router-level tests for /api/admin/llm-spend (Phase 18 X4)."""
from unittest.mock import AsyncMock, patch


class TestSpendStatusEndpoint:
    def test_admin_can_read_status(self, admin_client):
        with patch(
            "app.routers.admin_llm_spend.compute_status",
            new_callable=AsyncMock,
            return_value={
                "spent_brl": 250.0, "budget_brl": 1000.0, "used_pct": 0.25,
                "status": "ok", "soft_pct": 0.8, "hard_pct": 1.0,
            },
        ):
            resp = admin_client.get("/api/admin/llm-spend/org-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["spent_brl"] == 250.0
        assert data["status"] == "ok"
        assert data["org_id"] == "org-1"

    def test_non_admin_rejected(self, client):
        resp = client.get("/api/admin/llm-spend/org-1")
        assert resp.status_code == 403


class TestUpdateBudgetEndpoint:
    def test_admin_can_set_budget(self, admin_client):
        resp = admin_client.put(
            "/api/admin/llm-spend/org-1/budget",
            json={"monthly_brl": 1500.0},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["monthly_brl"] == 1500.0
        assert data["org_id"] == "org-1"
        assert data["ok"] is True

    def test_zero_clears_budget(self, admin_client):
        resp = admin_client.put(
            "/api/admin/llm-spend/org-1/budget",
            json={"monthly_brl": 0},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["monthly_brl"] == 0

    def test_negative_rejected(self, admin_client):
        resp = admin_client.put(
            "/api/admin/llm-spend/org-1/budget",
            json={"monthly_brl": -1},
        )
        assert resp.status_code == 422

    def test_non_admin_rejected(self, client):
        resp = client.put(
            "/api/admin/llm-spend/org-1/budget",
            json={"monthly_brl": 1000.0},
        )
        assert resp.status_code == 403
