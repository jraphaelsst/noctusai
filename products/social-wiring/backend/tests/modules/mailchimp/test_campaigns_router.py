"""Tests for the Mailchimp campaigns router — /api/mailchimp/campaigns."""
from __future__ import annotations


_CAMPAIGN_BODY = {
    "title": "Newsletter May",
    "subject_line": "Big news!",
    "from_name": "Acme Corp",
    "reply_to": "no-reply@acme.com",
}


class TestAuthRequired:
    def test_list_requires_auth(self, client):
        assert client.raw().get("/api/mailchimp/campaigns").status_code == 401

    def test_create_requires_auth(self, client):
        resp = client.raw().post("/api/mailchimp/campaigns", json=_CAMPAIGN_BODY)
        assert resp.status_code == 401

    def test_get_requires_auth(self, client):
        assert client.raw().get("/api/mailchimp/campaigns/c1").status_code == 401

    def test_patch_requires_auth(self, client):
        resp = client.raw().patch("/api/mailchimp/campaigns/c1", json={"title": "x"})
        assert resp.status_code == 401

    def test_delete_requires_auth(self, client):
        assert client.raw().delete("/api/mailchimp/campaigns/c1").status_code == 401

    def test_send_requires_auth(self, client):
        resp = client.raw().post("/api/mailchimp/campaigns/c1/actions/send", json={})
        assert resp.status_code == 401

    def test_schedule_requires_auth(self, client):
        resp = client.raw().post(
            "/api/mailchimp/campaigns/c1/actions/schedule",
            json={"schedule_time": "2026-07-01T10:00:00Z"},
        )
        assert resp.status_code == 401

    def test_unschedule_requires_auth(self, client):
        resp = client.raw().post(
            "/api/mailchimp/campaigns/c1/actions/unschedule", json={}
        )
        assert resp.status_code == 401

    def test_test_requires_auth(self, client):
        resp = client.raw().post(
            "/api/mailchimp/campaigns/c1/actions/test",
            json={"emails": ["a@b.com"]},
        )
        assert resp.status_code == 401


class TestNotConfigured:
    def test_503_when_not_connected(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.get("/api/mailchimp/campaigns")
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "mailchimp_not_configured"

    def test_503_when_no_audience(self, mailchimp_client):
        """No audience_id set → 503 for routes needing it."""
        c, store, fake = mailchimp_client
        # connect without audience
        c.put("/api/mailchimp/connection", json={"api_key": "k-us6"})
        resp = c.get("/api/mailchimp/campaigns")
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "mailchimp_not_configured"


class TestCampaignCrud:
    def test_create_campaign(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.post("/api/mailchimp/campaigns", json=_CAMPAIGN_BODY)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Newsletter May"
        assert data["status"] == "save"
        assert "id" in data

    def test_list_campaigns_envelope(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        c.post("/api/mailchimp/campaigns", json=_CAMPAIGN_BODY)
        resp = c.get("/api/mailchimp/campaigns")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data and "total" in data
        assert data["total"] >= 1

    def test_get_campaign(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        cid = c.post("/api/mailchimp/campaigns", json=_CAMPAIGN_BODY).json()["id"]
        resp = c.get(f"/api/mailchimp/campaigns/{cid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == cid

    def test_get_missing_campaign_returns_404(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.get("/api/mailchimp/campaigns/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_patch_campaign_title(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        cid = c.post("/api/mailchimp/campaigns", json=_CAMPAIGN_BODY).json()["id"]
        resp = c.patch(f"/api/mailchimp/campaigns/{cid}", json={"title": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"

    def test_delete_campaign(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        cid = c.post("/api/mailchimp/campaigns", json=_CAMPAIGN_BODY).json()["id"]
        resp = c.delete(f"/api/mailchimp/campaigns/{cid}")
        assert resp.status_code == 204

    def test_delete_missing_returns_404(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.delete("/api/mailchimp/campaigns/nonexistent")
        assert resp.status_code == 404


class TestCampaignActions:
    def test_send_returns_campaign_with_sent_status(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        cid = c.post("/api/mailchimp/campaigns", json=_CAMPAIGN_BODY).json()["id"]
        resp = c.post(f"/api/mailchimp/campaigns/{cid}/actions/send", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "sent"

    def test_schedule_returns_campaign_with_schedule_status(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        cid = c.post("/api/mailchimp/campaigns", json=_CAMPAIGN_BODY).json()["id"]
        resp = c.post(
            f"/api/mailchimp/campaigns/{cid}/actions/schedule",
            json={"schedule_time": "2026-07-01T10:00:00Z"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "schedule"

    def test_unschedule_returns_campaign_with_save_status(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        cid = c.post("/api/mailchimp/campaigns", json=_CAMPAIGN_BODY).json()["id"]
        c.post(
            f"/api/mailchimp/campaigns/{cid}/actions/schedule",
            json={"schedule_time": "2026-07-01T10:00:00Z"},
        )
        resp = c.post(f"/api/mailchimp/campaigns/{cid}/actions/unschedule", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "save"

    def test_send_test_returns_ok_true(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        cid = c.post("/api/mailchimp/campaigns", json=_CAMPAIGN_BODY).json()["id"]
        resp = c.post(
            f"/api/mailchimp/campaigns/{cid}/actions/test",
            json={"emails": ["test@example.com"]},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_create_with_template_id(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        tid = c.post("/api/mailchimp/templates", json={"name": "T", "html": "<p/>"}).json()["id"]
        body = {**_CAMPAIGN_BODY, "template_id": tid}
        resp = c.post("/api/mailchimp/campaigns", json=body)
        assert resp.status_code == 201
        data = resp.json()
        assert data["template_id"] == tid
