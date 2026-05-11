"""Tests for campaigns router."""

MOCK_CAMPAIGN = {
    "id": "camp-1",
    "org_id": "test-org-123",
    "nome": "Black Friday",
    "template_id": "t1",
    "list_id": "l1",
    "status": "rascunho",
    "total_recipients": 0,
    "total_sent": 0,
    "total_failed": 0,
    "created_by": "test-user-123",
    "created_at": "2026-01-01T00:00:00Z",
}


class TestListCampaigns:
    def test_list(self, client):
        client.mock_supabase.set_table_data("campaigns", [MOCK_CAMPAIGN])
        resp = client.get("/api/campaigns")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_no_auth(self, client):
        resp = client.raw().get("/api/campaigns")
        assert resp.status_code == 401


class TestCreateCampaign:
    def test_create(self, client):
        client.mock_supabase.set_table_data("campaigns", [MOCK_CAMPAIGN])
        resp = client.post("/api/campaigns", json={
            "nome": "Black Friday",
            "template_id": "t1",
            "list_id": "l1",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["nome"] == "Black Friday"

    def test_create_rejects_unknown_field_with_422(self, client):
        """StrictHttpModel migration guard — unknown keys 422 (was silently dropped).

        Pre-migration (`pydantic.BaseModel`, `extra="ignore"`) silently dropped
        `bogus_field`. Post-migration (`StrictHttpModel`, `extra="forbid"`) the
        schema rejects with 422 and names the offending `loc`. Defends against
        the silent-drop misroute class (`KB § PATTERNS/pydantic-strict-http.md`).
        """
        client.mock_supabase.set_table_data("campaigns", [MOCK_CAMPAIGN])
        resp = client.post("/api/campaigns", json={
            "nome": "Black Friday",
            "template_id": "t1",
            "list_id": "l1",
            "bogus_field": "should-422",
        })
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert any(
            "bogus_field" in str(err.get("loc", ""))
            for err in body.get("detail", [])
        )


class TestGetCampaign:
    def test_get_with_stats(self, client):
        client.mock_supabase.set_table_data("campaigns", [MOCK_CAMPAIGN])
        client.mock_supabase.set_table_data("send_logs", [])
        resp = client.get("/api/campaigns/camp-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "stats" in data

    def test_not_found(self, client):
        client.mock_supabase.set_table_data("campaigns", [])
        resp = client.get("/api/campaigns/nonexistent")
        assert resp.status_code == 404


class TestCampaignActions:
    def test_schedule(self, client):
        client.mock_supabase.set_table_data("campaigns", [{**MOCK_CAMPAIGN, "status": "agendada"}])
        resp = client.post("/api/campaigns/camp-1/schedule", json={
            "scheduled_at": "2026-12-25T09:00:00Z",
        })
        assert resp.status_code == 200

    def test_delete_rascunho(self, client):
        client.mock_supabase.set_table_data("campaigns", [MOCK_CAMPAIGN])
        resp = client.delete("/api/campaigns/camp-1")
        assert resp.status_code == 200
