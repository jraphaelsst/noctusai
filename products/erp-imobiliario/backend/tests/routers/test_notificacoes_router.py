"""
Tests for Notificacoes router — /api/notificacoes

Notifications now read from the core `public.notifications` table via
get_core_client(). Tests mock this to return the same MockSupabaseClient
used by the test harness, with data keyed by table name "notifications".
"""
import pytest
from unittest.mock import patch

# Patch target — get_core_client is imported in the router module
_CORE_CLIENT_PATCH = "app.routers.notificacoes.get_core_client"

# Core table uses English field names
SAMPLE_NOTIFICATIONS = [
    {"id": "n1", "type": "novo_lead", "title": "Novo lead recebido",
     "message": "Lead João chegou", "read": False, "created_at": "2026-02-27T10:00:00",
     "metadata": {}, "user_id": "test-user-123", "org_id": "test-org-123"},
    {"id": "n2", "type": "proposta_aceita", "title": "Proposta aceita",
     "message": None, "read": True, "created_at": "2026-02-26T10:00:00",
     "metadata": {}, "user_id": "test-user-123", "org_id": "test-org-123"},
]


class TestListarNotificacoes:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("notifications", SAMPLE_NOTIFICATIONS)
        with patch(_CORE_CLIENT_PATCH, return_value=client._mock_supabase):
            resp = client.get("/api/notificacoes")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        # Verify PT field mapping
        assert data[0]["titulo"] == "Novo lead recebido"
        assert data[0]["tipo"] == "novo_lead"
        assert data[0]["is_read"] is False

    def test_list_unread_only(self, client):
        client._mock_supabase.set_table_data("notifications", [SAMPLE_NOTIFICATIONS[0]])
        with patch(_CORE_CLIENT_PATCH, return_value=client._mock_supabase):
            resp = client.get("/api/notificacoes?apenas_nao_lidas=true")
        assert resp.status_code == 200

    def test_pagination(self, client):
        client._mock_supabase.set_table_data("notifications", [])
        with patch(_CORE_CLIENT_PATCH, return_value=client._mock_supabase):
            resp = client.get("/api/notificacoes?page=1&page_size=5")
        assert resp.status_code == 200


class TestContagemNaoLidas:
    def test_contagem(self, client):
        client._mock_supabase.set_table_data("notifications", [])
        with patch(_CORE_CLIENT_PATCH, return_value=client._mock_supabase):
            resp = client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        assert "nao_lidas" in resp.json().get("data", {})


class TestMarcarComoLida:
    def test_mark_single(self, client):
        client._mock_supabase.set_table_data("notifications", [
            {"id": "n1", "type": "novo_lead", "title": "Novo lead",
             "read": True, "created_at": "2026-02-27T10:00:00",
             "metadata": {}, "user_id": "test-user-123", "org_id": "test-org-123"},
        ])
        with patch(_CORE_CLIENT_PATCH, return_value=client._mock_supabase):
            resp = client.patch("/api/notificacoes/n1/ler")
        assert resp.status_code == 200

    def test_mark_nonexistent(self, client):
        client._mock_supabase.set_table_data("notifications", [])
        with patch(_CORE_CLIENT_PATCH, return_value=client._mock_supabase):
            resp = client.patch("/api/notificacoes/nonexistent/ler")
        assert resp.status_code in [200, 404]


class TestMarcarTodasComoLidas:
    def test_mark_all(self, client):
        client._mock_supabase.set_table_data("notifications", [
            {"id": "n1", "read": True},
            {"id": "n2", "read": True},
        ])
        with patch(_CORE_CLIENT_PATCH, return_value=client._mock_supabase):
            resp = client.post("/api/notificacoes/ler-todas")
        assert resp.status_code == 200


class TestPreferencias:
    def test_listar_preferencias(self, client):
        client._mock_supabase.set_table_data("notificacao_preferencias", [
            {"id": "p1", "canal": "app", "tipo_evento": "novo_lead", "ativo": True},
        ])
        resp = client.get("/api/notificacoes/preferencias")
        assert resp.status_code == 200

    def test_atualizar_preferencia(self, client):
        client._mock_supabase.set_table_data("notificacao_preferencias", [
            {"id": "p1", "canal": "email", "tipo_evento": "proposta_aceita", "ativo": False},
        ])
        resp = client.patch("/api/notificacoes/preferencias", json={
            "canal": "email",
            "tipo_evento": "proposta_aceita",
            "ativo": False,
        })
        assert resp.status_code == 200

    def test_invalid_canal(self, client):
        resp = client.patch("/api/notificacoes/preferencias", json={
            "canal": "sms",
            "tipo_evento": "novo_lead",
            "ativo": True,
        })
        assert resp.status_code == 422
