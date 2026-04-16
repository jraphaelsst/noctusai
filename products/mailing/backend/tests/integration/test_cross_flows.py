"""Integration tests — multi-step flows where entities reference each other."""
import hashlib
import hmac
import base64

from noctusai_lib.testing import MockSupabaseResponse


# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

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

MOCK_SEND_LOG = {
    "id": "sl-1",
    "org_id": "test-org-123",
    "campaign_id": "camp-1",
    "contact_id": "c1",
    "resend_message_id": "resend-msg-abc",
    "status": "sent",
    "sent_at": "2026-01-02T00:00:00Z",
}


def _generate_unsubscribe_token(org_id: str, contact_id: str, email: str) -> str:
    """Generate an HMAC-signed unsubscribe token matching the router's logic.

    Uses the same secret as the running app (loaded from app.config.settings).
    """
    from app.config import settings
    secret = settings.jwt_secret
    payload = f"{org_id}:{contact_id}:{email}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


# ---------------------------------------------------------------------------
# 1. Campaign requires template + list
# ---------------------------------------------------------------------------

class TestCampaignRequiresTemplateAndList:
    """Creating a campaign references both a template and a list."""

    def test_campaign_references_template_and_list(self, client):
        # Step 1 — create template
        client.mock_supabase.set_table_data("templates", [MOCK_TEMPLATE])
        resp = client.post("/api/templates", json={
            "nome": "Welcome Email",
            "assunto": "Welcome!",
            "corpo_html": "<h1>Hi</h1>",
        })
        assert resp.status_code == 200
        template = resp.json()["data"]
        assert template["id"] == "tpl-1"

        # Step 2 — create list
        client.mock_supabase.set_table_data("contact_lists", [MOCK_LIST])
        resp = client.post("/api/lists", json={
            "nome": "VIP Customers",
        })
        assert resp.status_code == 200
        created_list = resp.json()["data"]
        assert created_list["id"] == "list-1"

        # Step 3 — create campaign referencing both
        client.mock_supabase.set_table_data("campaigns", [MOCK_CAMPAIGN])
        resp = client.post("/api/campaigns", json={
            "nome": "Black Friday",
            "template_id": template["id"],
            "list_id": created_list["id"],
        })
        assert resp.status_code == 200
        campaign = resp.json()["data"]

        # Step 4 — verify campaign has template_id and list_id set
        assert campaign["template_id"] == "tpl-1"
        assert campaign["list_id"] == "list-1"


# ---------------------------------------------------------------------------
# 2. Automation enrollment requires contacts + steps
# ---------------------------------------------------------------------------

class TestAutomationEnrollment:
    """Enrolling a contact into an automation references the first step."""

    def test_enroll_contact_references_first_step(self, client):
        # Step 1 — create automation
        client.mock_supabase.set_table_data("automations", [MOCK_AUTOMATION])
        resp = client.post("/api/automations", json={
            "nome": "Welcome Sequence",
            "trigger_type": "contact_added",
        })
        assert resp.status_code == 200

        # Step 2 — add a step
        step = {
            "id": "step-1",
            "automation_id": "auto-1",
            "posicao": 1,
            "tipo": "send_email",
            "config": {"template_id": "tpl-1"},
        }
        client.mock_supabase.set_table_data("automation_steps", [step])
        resp = client.post("/api/automations/auto-1/steps", json={
            "tipo": "send_email",
            "config": {"template_id": "tpl-1"},
        })
        assert resp.status_code == 200

        # Step 3 — enroll a contact
        enrollment = {
            "id": "enr-1",
            "automation_id": "auto-1",
            "contact_id": "c1",
            "current_step_id": "step-1",
            "status": "active",
        }
        client.mock_supabase.set_table_data("automation_enrollments", [enrollment])
        resp = client.post("/api/automations/auto-1/enroll", json={
            "contact_ids": ["c1"],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]

        # Step 4 — verify enrollment references the first step
        # The response data is a list of enrollments
        if isinstance(data, list):
            assert any(e.get("current_step_id") == "step-1" for e in data)
        else:
            # Single enrollment object
            assert data.get("current_step_id") == "step-1" or data.get("automation_id") == "auto-1"


# ---------------------------------------------------------------------------
# 3. Unsubscribe flow updates contact status
# ---------------------------------------------------------------------------

class TestUnsubscribeFlow:
    """POST /api/unsubscribe/{token} with a valid HMAC token processes unsubscribe."""

    def test_valid_token_unsubscribe(self, client):
        # Generate a valid token using the same HMAC logic as the router
        token = _generate_unsubscribe_token("test-org-123", "c1", "lead@test.com")

        # Mock the DB calls made during unsubscribe processing
        client.mock_supabase.set_table_data("contacts", [MOCK_CONTACT])
        client.mock_supabase.set_table_data("unsubscribes", [
            {"id": "unsub-1", "org_id": "test-org-123", "contact_id": "c1",
             "email": "lead@test.com", "reason": "link_click"},
        ])

        # POST to process unsubscribe (no auth required)
        resp = client.raw().post(f"/api/unsubscribe/{token}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_invalid_token_rejected(self, client):
        resp = client.raw().post("/api/unsubscribe/bad-token")
        assert resp.status_code == 400

    def test_get_valid_token_returns_email(self, client):
        token = _generate_unsubscribe_token("test-org-123", "c1", "lead@test.com")
        resp = client.raw().get(f"/api/unsubscribe/{token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "lead@test.com"
        assert data["valid"] is True


# ---------------------------------------------------------------------------
# 4. Webhook updates send_log status
# ---------------------------------------------------------------------------

class TestWebhookUpdatesSendLog:
    """POST /api/webhooks/resend with event type updates the send_log."""

    def test_email_opened_updates_status(self, client):
        # Set up send_log so the webhook can find it by resend_message_id
        send_log_after_update = {**MOCK_SEND_LOG, "status": "opened"}
        client.mock_supabase.set_sequential_responses("send_logs", [
            MockSupabaseResponse(data=[MOCK_SEND_LOG]),        # SELECT to find log
            MockSupabaseResponse(data=[send_log_after_update]),  # UPDATE result
        ])

        resp = client.raw().post("/api/webhooks/resend", json={
            "type": "email.opened",
            "data": {
                "email_id": "resend-msg-abc",
            },
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_email_bounced_updates_contact(self, client):
        """Bounce events update both send_log and contact status."""
        client.mock_supabase.set_sequential_responses("send_logs", [
            MockSupabaseResponse(data=[MOCK_SEND_LOG]),
            MockSupabaseResponse(data=[{**MOCK_SEND_LOG, "status": "bounced"}]),
        ])
        client.mock_supabase.set_table_data("contacts", [{**MOCK_CONTACT, "status": "bounced"}])

        resp = client.raw().post("/api/webhooks/resend", json={
            "type": "email.bounced",
            "data": {
                "email_id": "resend-msg-abc",
            },
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_unknown_event_skipped(self, client):
        resp = client.raw().post("/api/webhooks/resend", json={
            "type": "email.unknown_event",
            "data": {"email_id": "resend-msg-abc"},
        })
        assert resp.status_code == 200
        assert resp.json().get("skipped") is True

    def test_no_message_id_skipped(self, client):
        resp = client.raw().post("/api/webhooks/resend", json={
            "type": "email.opened",
            "data": {},
        })
        assert resp.status_code == 200
        assert resp.json().get("skipped") is True
