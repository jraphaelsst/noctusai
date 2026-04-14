"""Tests for the health check endpoint."""


class TestHealthCheck:
    """GET /api/health"""

    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["product"] == "Daily Life"

    def test_health_returns_version(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert data["version"] == "0.1.0"
