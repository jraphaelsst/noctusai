"""Tests for automations router."""

MOCK_AUTOMATION = {
    "id": "auto-1",
    "org_id": "test-org-123",
    "nome": "Welcome Sequence",
    "trigger_type": "contact_added",
    "trigger_config": {},
    "status": "rascunho",
    "created_by": "test-user-123",
    "created_at": "2026-01-01T00:00:00Z",
}

MOCK_STEP = {
    "id": "step-1",
    "automation_id": "auto-1",
    "posicao": 1,
    "tipo": "send_email",
    "config": {"template_id": "t1"},
}


class TestListAutomations:
    def test_list(self, client):
        client.mock_supabase.set_table_data("automations", [MOCK_AUTOMATION])
        resp = client.get("/api/automations")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_no_auth(self, client):
        resp = client.raw().get("/api/automations")
        assert resp.status_code == 401


class TestCreateAutomation:
    def test_create(self, client):
        client.mock_supabase.set_table_data("automations", [MOCK_AUTOMATION])
        resp = client.post("/api/automations", json={
            "nome": "Welcome Sequence",
            "trigger_type": "contact_added",
        })
        assert resp.status_code == 200


class TestAutomationSteps:
    def test_list_steps(self, client):
        client.mock_supabase.set_table_data("automation_steps", [MOCK_STEP])
        resp = client.get("/api/automations/auto-1/steps")
        assert resp.status_code == 200

    def test_add_step(self, client):
        client.mock_supabase.set_table_data("automation_steps", [MOCK_STEP])
        resp = client.post("/api/automations/auto-1/steps", json={
            "tipo": "wait",
            "config": {"duration_hours": 24},
        })
        assert resp.status_code == 200


class TestAutomationActions:
    def test_activate(self, client):
        client.mock_supabase.set_table_data("automations", [{**MOCK_AUTOMATION, "status": "ativa"}])
        resp = client.post("/api/automations/auto-1/activate")
        assert resp.status_code == 200

    def test_pause(self, client):
        client.mock_supabase.set_table_data("automations", [{**MOCK_AUTOMATION, "status": "pausada"}])
        resp = client.post("/api/automations/auto-1/pause")
        assert resp.status_code == 200
