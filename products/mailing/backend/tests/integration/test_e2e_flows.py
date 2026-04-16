"""E2E tests — full user journeys through the Mailing API."""
from noctusai_lib.testing import MockSupabaseResponse


# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

MOCK_CONTACT = {
    "id": "c1",
    "org_id": "test-org-123",
    "email": "lead@test.com",
    "nome": "Lead Test",
    "empresa": "Test Inc",
    "tags": ["vip"],
    "status": "active",
    "source": "manual",
    "created_at": "2026-01-01T00:00:00Z",
}

MOCK_TEMPLATE = {
    "id": "tpl-1",
    "org_id": "test-org-123",
    "nome": "Welcome Email",
    "assunto": "Welcome!",
    "html": "<h1>Hi {{nome}}</h1>",
    "categoria": "onboarding",
    "status": "ativo",
    "created_at": "2026-01-01T00:00:00Z",
}

MOCK_LIST = {
    "id": "list-1",
    "org_id": "test-org-123",
    "nome": "VIP Customers",
    "descricao": "Top tier",
    "total_contacts": 10,
    "created_at": "2026-01-01T00:00:00Z",
}

MOCK_CAMPAIGN = {
    "id": "camp-1",
    "org_id": "test-org-123",
    "nome": "Black Friday",
    "template_id": "tpl-1",
    "list_id": "list-1",
    "status": "rascunho",
    "total_recipients": 0,
    "total_sent": 0,
    "total_failed": 0,
    "created_by": "test-user-123",
    "created_at": "2026-01-01T00:00:00Z",
}

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

MOCK_STEP_EMAIL_1 = {
    "id": "step-1",
    "automation_id": "auto-1",
    "posicao": 1,
    "tipo": "send_email",
    "config": {"template_id": "tpl-1"},
}

MOCK_STEP_WAIT = {
    "id": "step-2",
    "automation_id": "auto-1",
    "posicao": 2,
    "tipo": "wait",
    "config": {"duration_hours": 24},
}

MOCK_STEP_EMAIL_2 = {
    "id": "step-3",
    "automation_id": "auto-1",
    "posicao": 3,
    "tipo": "send_email",
    "config": {"template_id": "tpl-1"},
}


# ---------------------------------------------------------------------------
# 1. Contact lifecycle
# ---------------------------------------------------------------------------

class TestContactLifecycle:
    """Create -> Get -> Update -> Delete -> 404."""

    def test_full_lifecycle(self, client):
        # CREATE
        client.mock_supabase.set_table_data("contacts", [MOCK_CONTACT])
        resp = client.post("/api/contacts", json={
            "email": "lead@test.com",
            "nome": "Lead Test",
        })
        assert resp.status_code == 200
        contact = resp.json()["data"]
        assert contact["email"] == "lead@test.com"
        contact_id = contact["id"]

        # GET
        client.mock_supabase.set_table_data("contacts", [MOCK_CONTACT])
        resp = client.get(f"/api/contacts/{contact_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == contact_id

        # UPDATE
        updated = {**MOCK_CONTACT, "nome": "Updated Name"}
        client.mock_supabase.set_table_data("contacts", [updated])
        resp = client.patch(f"/api/contacts/{contact_id}", json={"nome": "Updated Name"})
        assert resp.status_code == 200

        # DELETE
        client.mock_supabase.set_table_data("contacts", [MOCK_CONTACT])
        resp = client.delete(f"/api/contacts/{contact_id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # VERIFY 404 after delete
        client.mock_supabase.set_table_data("contacts", [])
        resp = client.get(f"/api/contacts/{contact_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 2. Campaign lifecycle
# ---------------------------------------------------------------------------

class TestCampaignLifecycle:
    """Template -> List -> Campaign -> Get (stats) -> Schedule -> Cancel."""

    def test_full_lifecycle(self, client):
        # CREATE TEMPLATE
        client.mock_supabase.set_table_data("templates", [MOCK_TEMPLATE])
        resp = client.post("/api/templates", json={
            "nome": "Welcome Email",
            "assunto": "Welcome!",
            "corpo_html": "<h1>Hi</h1>",
        })
        assert resp.status_code == 200

        # CREATE LIST
        client.mock_supabase.set_table_data("contact_lists", [MOCK_LIST])
        resp = client.post("/api/lists", json={"nome": "VIP Customers"})
        assert resp.status_code == 200

        # CREATE CAMPAIGN with template + list
        client.mock_supabase.set_table_data("campaigns", [MOCK_CAMPAIGN])
        resp = client.post("/api/campaigns", json={
            "nome": "Black Friday",
            "template_id": "tpl-1",
            "list_id": "list-1",
        })
        assert resp.status_code == 200
        campaign = resp.json()["data"]
        campaign_id = campaign["id"]

        # GET CAMPAIGN — verify stats included
        client.mock_supabase.set_table_data("campaigns", [MOCK_CAMPAIGN])
        client.mock_supabase.set_table_data("send_logs", [])
        resp = client.get(f"/api/campaigns/{campaign_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "stats" in data

        # SCHEDULE CAMPAIGN
        scheduled = {**MOCK_CAMPAIGN, "status": "agendada"}
        client.mock_supabase.set_table_data("campaigns", [scheduled])
        resp = client.post(f"/api/campaigns/{campaign_id}/schedule", json={
            "scheduled_at": "2026-12-25T09:00:00Z",
        })
        assert resp.status_code == 200

        # CANCEL CAMPAIGN
        cancelled = {**MOCK_CAMPAIGN, "status": "cancelada"}
        client.mock_supabase.set_table_data("campaigns", [cancelled])
        resp = client.post(f"/api/campaigns/{campaign_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelada"


# ---------------------------------------------------------------------------
# 3. Automation lifecycle
# ---------------------------------------------------------------------------

class TestAutomationLifecycle:
    """Create -> Add 3 steps -> Get (verify steps) -> Activate -> Pause."""

    def test_full_lifecycle(self, client):
        # CREATE AUTOMATION
        client.mock_supabase.set_table_data("automations", [MOCK_AUTOMATION])
        resp = client.post("/api/automations", json={
            "nome": "Welcome Sequence",
            "trigger_type": "contact_added",
        })
        assert resp.status_code == 200

        # ADD STEP 1 — send_email
        client.mock_supabase.set_table_data("automation_steps", [MOCK_STEP_EMAIL_1])
        resp = client.post("/api/automations/auto-1/steps", json={
            "tipo": "send_email",
            "config": {"template_id": "tpl-1"},
        })
        assert resp.status_code == 200

        # ADD STEP 2 — wait
        client.mock_supabase.set_table_data("automation_steps", [MOCK_STEP_WAIT])
        resp = client.post("/api/automations/auto-1/steps", json={
            "tipo": "wait",
            "config": {"duration_hours": 24},
        })
        assert resp.status_code == 200

        # ADD STEP 3 — send_email
        client.mock_supabase.set_table_data("automation_steps", [MOCK_STEP_EMAIL_2])
        resp = client.post("/api/automations/auto-1/steps", json={
            "tipo": "send_email",
            "config": {"template_id": "tpl-1"},
        })
        assert resp.status_code == 200

        # GET AUTOMATION — verify steps included
        all_steps = [MOCK_STEP_EMAIL_1, MOCK_STEP_WAIT, MOCK_STEP_EMAIL_2]
        client.mock_supabase.set_table_data("automations", [MOCK_AUTOMATION])
        client.mock_supabase.set_table_data("automation_steps", all_steps)
        resp = client.get("/api/automations/auto-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "steps" in data
        assert len(data["steps"]) == 3

        # ACTIVATE
        activated = {**MOCK_AUTOMATION, "status": "ativa"}
        client.mock_supabase.set_table_data("automations", [activated])
        resp = client.post("/api/automations/auto-1/activate")
        assert resp.status_code == 200

        # PAUSE
        paused = {**MOCK_AUTOMATION, "status": "pausada"}
        client.mock_supabase.set_table_data("automations", [paused])
        resp = client.post("/api/automations/auto-1/pause")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "pausada"


# ---------------------------------------------------------------------------
# 4. Auth boundary — all protected endpoints return 401 without auth
# ---------------------------------------------------------------------------

class TestAuthBoundary:
    """Every protected endpoint must return 401 when no Authorization header is sent."""

    # Contacts
    def test_get_contacts_401(self, client):
        assert client.raw().get("/api/contacts").status_code == 401

    def test_post_contacts_401(self, client):
        assert client.raw().post("/api/contacts", json={"email": "x@y.com"}).status_code == 401

    # Lists
    def test_get_lists_401(self, client):
        assert client.raw().get("/api/lists").status_code == 401

    def test_post_lists_401(self, client):
        assert client.raw().post("/api/lists", json={"nome": "X"}).status_code == 401

    # Templates
    def test_get_templates_401(self, client):
        assert client.raw().get("/api/templates").status_code == 401

    def test_post_templates_401(self, client):
        assert client.raw().post("/api/templates", json={
            "nome": "X", "assunto": "Y", "corpo_html": "<p>Z</p>",
        }).status_code == 401

    # Campaigns
    def test_get_campaigns_401(self, client):
        assert client.raw().get("/api/campaigns").status_code == 401

    def test_post_campaigns_401(self, client):
        assert client.raw().post("/api/campaigns", json={
            "nome": "X", "template_id": "t1", "list_id": "l1",
        }).status_code == 401

    # Automations
    def test_get_automations_401(self, client):
        assert client.raw().get("/api/automations").status_code == 401

    def test_post_automations_401(self, client):
        assert client.raw().post("/api/automations", json={
            "nome": "X", "trigger_type": "contact_added",
        }).status_code == 401

    # Analytics
    def test_get_analytics_dashboard_401(self, client):
        assert client.raw().get("/api/analytics/dashboard").status_code == 401

    # Settings
    def test_get_settings_domains_401(self, client):
        assert client.raw().get("/api/settings/domains").status_code == 401


# ---------------------------------------------------------------------------
# 5. Public endpoints — accessible without auth
# ---------------------------------------------------------------------------

class TestPublicEndpoints:
    """Public endpoints must work without auth headers."""

    def test_webhooks_resend_no_auth(self, client):
        """POST /api/webhooks/resend returns 200 even with empty payload."""
        resp = client.raw().post("/api/webhooks/resend", json={})
        assert resp.status_code == 200

    def test_unsubscribe_bad_token_400(self, client):
        """GET /api/unsubscribe/{token} returns 400 for invalid token, not 401."""
        resp = client.raw().get("/api/unsubscribe/invalid-token-here")
        assert resp.status_code == 400

    def test_health_no_auth(self, client):
        """GET /api/health returns 200 without auth."""
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
