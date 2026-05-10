"""Tests for Mailing Product — framework endpoints + domain routes exist.

`TestHealthCheck` inherits from `noctusai_lib.testing.HealthCheckSuite`
(lifted from N=4 byte-identical copies; see `seed/lib/backend/noctusai_lib/
testing/framework_test_suites.py`). The framework-team / framework-
notificacoes probes stay here as they are absorbed by the e2e
`AuthBoundarySuite` only when products adopt that suite — mailing keeps a
custom auth-boundary covering its mailing-specific endpoints.
"""
from noctusai_lib.testing import HealthCheckSuite


class TestHealthCheck(HealthCheckSuite):
    expected_product_name = "Mailing"

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
