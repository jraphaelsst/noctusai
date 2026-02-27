"""
Tests for Notificacoes router — /api/notificacoes
Covers listing, marking as read, and preference management.
"""
import pytest


class TestListarNotificacoes:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("notificacoes", [
            {"id": "n1", "tipo": "novo_lead", "titulo": "Novo lead recebido",
             "is_read": False, "created_at": "2026-02-27T10:00:00"},
            {"id": "n2", "tipo": "proposta_aceita", "titulo": "Proposta aceita",
             "is_read": True, "created_at": "2026-02-26T10:00:00"},
        ])
        resp = client.get("/api/notificacoes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_list_unread_only(self, client):
        client._mock_supabase.set_table_data("notificacoes", [
            {"id": "n1", "tipo": "novo_lead", "titulo": "Novo lead",
             "is_read": False, "created_at": "2026-02-27T10:00:00"},
        ])
        resp = client.get("/api/notificacoes?apenas_nao_lidas=true")
        assert resp.status_code == 200

    def test_pagination(self, client):
        client._mock_supabase.set_table_data("notificacoes", [])
        resp = client.get("/api/notificacoes?page=1&page_size=5")
        assert resp.status_code == 200


class TestContagemNaoLidas:
    def test_contagem(self, client):
        client._mock_supabase.set_table_data("notificacoes", [])
        resp = client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        data = resp.json()
        assert "nao_lidas" in data.get("data", {})


class TestMarcarComoLida:
    def test_mark_single(self, client):
        client._mock_supabase.set_table_data("notificacoes", [
            {"id": "n1", "tipo": "novo_lead", "titulo": "Novo lead",
             "is_read": True, "created_at": "2026-02-27T10:00:00"},
        ])
        resp = client.patch("/api/notificacoes/n1/ler")
        assert resp.status_code == 200

    def test_mark_nonexistent(self, client):
        client._mock_supabase.set_table_data("notificacoes", [])
        resp = client.patch("/api/notificacoes/nonexistent/ler")
        assert resp.status_code in [200, 404]


class TestMarcarTodasComoLidas:
    def test_mark_all(self, client):
        client._mock_supabase.set_table_data("notificacoes", [
            {"id": "n1", "is_read": True},
            {"id": "n2", "is_read": True},
        ])
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
