"""HTTP-boundary tests for the ``email_marketing`` module routers.

Exercises the FastAPI layer (auth wiring, validation, status codes,
seed-backed CRUD) through the real ``register()`` seam. Service-internal
logic (clustering, template var-extraction) is covered in
``test_services.py``.
"""
from __future__ import annotations

import hashlib
import hmac

from app.config import settings


class TestContactsRouter:
    def test_list_contacts_returns_paginated_shape(self, client):
        resp = client.get("/api/email-marketing/contacts")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "data" in body and "pagination" in body
        assert "total" in body["pagination"]

    def test_create_contact_validates_email(self, client):
        resp = client.post(
            "/api/email-marketing/contacts", json={"email": "not-an-email"}
        )
        assert resp.status_code == 422, resp.text

    def test_create_contact_rejects_unknown_field(self, client):
        # StrictHttpModel → extra="forbid" → 422 on unknown keys.
        resp = client.post(
            "/api/email-marketing/contacts",
            json={"email": "a@b.com", "bogus": 1},
        )
        assert resp.status_code == 422, resp.text

    def test_create_contact_happy_path(self, client):
        resp = client.post(
            "/api/email-marketing/contacts",
            json={"email": "lead@example.com", "nome": "Lead"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["email"] == "lead@example.com"

    def test_update_contact_accepts_email(self, client):
        # Regression: `email` was missing from `ContactUpdate` while the
        # Contatos edit form sent it. `extra="forbid"` turned that into a
        # 422 on EVERY contact edit in prod. Email is editable (a typo'd
        # address must be correctable), so the schema carries it.
        created = client.post(
            "/api/email-marketing/contacts",
            json={"email": "typo@example.com", "nome": "Lead"},
        )
        assert created.status_code == 200, created.text
        contact_id = created.json()["data"]["id"]

        resp = client.patch(
            f"/api/email-marketing/contacts/{contact_id}",
            json={"email": "correto@example.com", "nome": "Lead"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["email"] == "correto@example.com"

    def test_update_contact_validates_email(self, client):
        created = client.post(
            "/api/email-marketing/contacts",
            json={"email": "lead2@example.com"},
        )
        contact_id = created.json()["data"]["id"]
        resp = client.patch(
            f"/api/email-marketing/contacts/{contact_id}",
            json={"email": "not-an-email"},
        )
        assert resp.status_code == 422, resp.text

    def test_update_contact_still_rejects_unknown_field(self, client):
        # Widening the schema by one field must not loosen strictness.
        created = client.post(
            "/api/email-marketing/contacts",
            json={"email": "lead3@example.com"},
        )
        contact_id = created.json()["data"]["id"]
        resp = client.patch(
            f"/api/email-marketing/contacts/{contact_id}",
            json={"email": "lead3@example.com", "bogus": 1},
        )
        assert resp.status_code == 422, resp.text

    def test_unauthenticated_request_rejected(self, client):
        resp = client.raw().get("/api/email-marketing/contacts")
        assert resp.status_code == 401, resp.text


class TestListsRouter:
    def test_list_all_returns_envelope(self, client):
        resp = client.get("/api/email-marketing/lists")
        assert resp.status_code == 200, resp.text
        assert "data" in resp.json()

    def test_create_list_requires_nome(self, client):
        resp = client.post("/api/email-marketing/lists", json={})
        assert resp.status_code == 422, resp.text


class TestTemplatesRouter:
    def test_create_template_requires_fields(self, client):
        resp = client.post("/api/email-marketing/templates", json={"nome": "x"})
        assert resp.status_code == 422, resp.text

    def test_list_templates_ok(self, client):
        resp = client.get("/api/email-marketing/templates")
        assert resp.status_code == 200, resp.text


class TestCampaignsRouter:
    def test_list_campaigns_ok(self, client):
        resp = client.get("/api/email-marketing/campaigns")
        assert resp.status_code == 200, resp.text

    def test_get_unknown_campaign_404(self, client):
        resp = client.get("/api/email-marketing/campaigns/does-not-exist")
        assert resp.status_code == 404, resp.text

    def test_create_campaign_requires_template_and_list(self, client):
        resp = client.post(
            "/api/email-marketing/campaigns", json={"nome": "Promo"}
        )
        assert resp.status_code == 422, resp.text


class TestAnalyticsRouter:
    def test_dashboard_metrics_shape(self, client):
        resp = client.get("/api/email-marketing/analytics/dashboard")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        for key in ("total_contacts", "open_rate", "click_rate"):
            assert key in data


class TestUnsubscribeRouter:
    """Public, no-auth, HMAC-token verified (LGPD compliance surface)."""

    def test_invalid_token_rejected(self, client):
        resp = client.raw().get("/api/email-marketing/unsubscribe/garbage")
        assert resp.status_code == 400, resp.text

    def test_valid_token_round_trips(self, client):
        import base64

        org, cid, email = "org-1", "contact-1", "person@example.com"
        payload = f"{org}:{cid}:{email}"
        sig = hmac.new(
            settings.jwt_secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()[:16]
        token = base64.urlsafe_b64encode(
            f"{payload}:{sig}".encode()
        ).decode()
        resp = client.raw().get(
            f"/api/email-marketing/unsubscribe/{token}"
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["email"] == email


class TestWebhooksRouter:
    def test_resend_webhook_mounted(self, client):
        # bypass_when_unset=True → unsigned payload accepted (early-dev),
        # unknown event type skipped. Asserts the route exists + the 5-pin
        # webhook_endpoint dependency wired without 404/405.
        resp = client.raw().post(
            "/api/email-marketing/webhooks/resend",
            json={"type": "email.unknown", "data": {}},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get("skipped") is True


class TestAIRouter:
    def test_subjects_requires_body(self, client):
        resp = client.post("/api/email-marketing/ai/subjects", json={})
        assert resp.status_code == 422, resp.text

    def test_segment_contacts_route_mounted(self, client):
        # No LLM configured in tests → service degrades; the point here is
        # the consent-gated route resolves (not 404/405) and validates.
        resp = client.post(
            "/api/email-marketing/ai/segment-contacts", json={}
        )
        assert resp.status_code in (200, 403, 422, 503), resp.text
