"""
Tests for Health check endpoint — Mailing Product.
"""


class TestHealthCheck:
    def test_health_returns_ok(self, client):
        """Health endpoint returns status ok with product info."""
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["product"] == "Mailing"
        assert data["version"] == "0.1.0"

    def test_team_endpoint_exists(self, client):
        """Team endpoint is provided by the framework."""
        resp = client.raw().get("/api/team")
        assert resp.status_code == 401  # no auth = 401, but endpoint exists

    def test_notificacoes_endpoint_exists(self, client):
        """Notification endpoint is provided by the framework."""
        resp = client.raw().get("/api/notificacoes")
        assert resp.status_code == 401  # no auth = 401, but endpoint exists
