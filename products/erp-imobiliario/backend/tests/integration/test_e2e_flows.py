"""
Integration tests for ERP backend — framework standard routers.

The team and notification routers are now provided by the noctusai_seed
framework. These tests verify the framework routers are correctly mounted
and respond to basic requests.
"""
import pytest


class TestFrameworkHealthRouter:
    """Verify the seed framework health endpoint is mounted."""

    def test_health_endpoint(self, client):
        """GET /api/health -> returns product info."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["product"] == "ERP Imobiliario"
        assert body["version"] == "0.2.0"


class TestFrameworkTeamRouter:
    """Verify the seed framework team router is mounted."""

    def test_team_list_requires_auth(self, client):
        """GET /api/team -> returns 200 (auth provided by client fixture)."""
        resp = client.get("/api/team")
        assert resp.status_code == 200


class TestFrameworkNotificacoesRouter:
    """Verify the seed framework notificacoes router is mounted."""

    def test_notificacoes_list(self, client):
        """GET /api/notificacoes -> returns 200."""
        resp = client.get("/api/notificacoes")
        assert resp.status_code == 200

    def test_notificacoes_contagem(self, client):
        """GET /api/notificacoes/contagem -> returns count."""
        resp = client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        body = resp.json()
        assert "nao_lidas" in body
