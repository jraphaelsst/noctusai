"""
Tests for Notificacoes router — /api/notificacoes

After the seed framework migration, the notificacoes router is provided by
the noctusai_seed framework. These tests verify the framework router is
correctly mounted and responds to basic requests.
"""
import pytest


class TestListarNotificacoes:
    def test_list_all(self, client):
        """GET /api/notificacoes -> returns 200 with data."""
        client._mock_supabase.set_table_data("notifications", [
            {"id": "n1", "type": "novo_lead", "title": "Novo lead recebido",
             "message": "Lead Joao chegou", "is_read": False,
             "created_at": "2026-02-27T10:00:00",
             "metadata": {}, "user_id": "test-user-123", "org_id": "test-org-123"},
        ])
        resp = client.get("/api/notificacoes")
        assert resp.status_code == 200

    def test_pagination(self, client):
        """GET /api/notificacoes?page=1&page_size=5 -> returns 200."""
        client._mock_supabase.set_table_data("notifications", [])
        resp = client.get("/api/notificacoes?page=1&page_size=5")
        assert resp.status_code == 200


class TestContagemNaoLidas:
    def test_contagem(self, client):
        """GET /api/notificacoes/contagem -> returns count."""
        client._mock_supabase.set_table_data("notifications", [])
        resp = client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        body = resp.json()
        assert "nao_lidas" in body


class TestMarcarComoLida:
    def test_mark_single(self, client):
        """PATCH /api/notificacoes/{id}/ler -> returns 200."""
        client._mock_supabase.set_table_data("notifications", [
            {"id": "n1", "type": "novo_lead", "title": "Novo lead",
             "is_read": False, "created_at": "2026-02-27T10:00:00",
             "metadata": {}, "user_id": "test-user-123"},
        ])
        resp = client.patch("/api/notificacoes/n1/ler")
        assert resp.status_code == 200


class TestMarcarTodasComoLidas:
    def test_mark_all(self, client):
        """POST /api/notificacoes/ler-todas -> returns 200."""
        client._mock_supabase.set_table_data("notifications", [])
        resp = client.post("/api/notificacoes/ler-todas")
        assert resp.status_code == 200
