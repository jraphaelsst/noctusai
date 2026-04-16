"""Tests for Mailing Product — framework endpoints + domain routes exist."""


class TestHealthCheck:
    def test_health_returns_ok(self, client):
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["product"] == "Mailing"

    def test_framework_team_exists(self, client):
        resp = client.raw().get("/api/team")
        assert resp.status_code == 401

    def test_framework_notificacoes_exists(self, client):
        resp = client.raw().get("/api/notificacoes")
        assert resp.status_code == 401


class TestDomainRoutesExist:
    """Verify all domain endpoints are registered (auth-gated)."""

    def test_contacts_exists(self, client):
        resp = client.raw().get("/api/contacts")
        assert resp.status_code == 401

    def test_lists_exists(self, client):
        resp = client.raw().get("/api/lists")
        assert resp.status_code == 401

    def test_templates_exists(self, client):
        resp = client.raw().get("/api/templates")
        assert resp.status_code == 401

    def test_campaigns_exists(self, client):
        resp = client.raw().get("/api/campaigns")
        assert resp.status_code == 401

    def test_automations_exists(self, client):
        resp = client.raw().get("/api/automations")
        assert resp.status_code == 401

    def test_analytics_exists(self, client):
        resp = client.raw().get("/api/analytics/dashboard")
        assert resp.status_code == 401

    def test_settings_domains_exists(self, client):
        resp = client.raw().get("/api/settings/domains")
        assert resp.status_code == 401

    def test_webhooks_resend_no_auth_needed(self, client):
        resp = client.raw().post("/api/webhooks/resend", json={})
        assert resp.status_code == 200

    def test_unsubscribe_no_auth_bad_token(self, client):
        resp = client.raw().get("/api/unsubscribe/invalid-token")
        assert resp.status_code == 400
