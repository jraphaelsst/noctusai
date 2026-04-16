"""
Tests for Health check endpoint — provided by seed framework.
"""


class TestHealthCheck:
    def test_health_returns_ok(self, client):
        """Health endpoint returns status ok with product info."""
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["product"] == "{{PRODUCT_NAME}}"
        assert data["version"] == "0.1.0"
