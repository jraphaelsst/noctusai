"""Router-level tests for /api/admin/llm-spend (Phase 18 X4)."""


class TestSpendStatusEndpoint:
    # The READ's access matrix (platform admin any org, org owner/admin own org
    # only) lives in test_admin_llm_spend_access.py, against the trusted seams.
    def test_non_admin_rejected(self, client):
        # The conftest `client` session is an authenticated non-admin.
        resp = client.get("/api/admin/llm-spend/11111111-1111-1111-1111-111111111111")
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
