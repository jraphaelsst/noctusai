"""
Tests for the Notificação Preferências router — /api/notificacoes/preferencias

2026-09-20 wiring audit, task 8: `erp.notificacao_preferencias` existed
since migration 001 with nothing reading or writing it — the FE panel's
24 channel switches always rendered "on" and persisted nothing. These
tests pin the two routes now backing that panel.
"""
from __future__ import annotations


class TestListarPreferencias:
    def test_returns_stored_rows(self, client):
        # "test-user-123" is `MockUser`'s default id — the mocked auth
        # user this fixture's requests carry.
        client._mock_supabase.set_table_data("notificacao_preferencias", [
            {"user_id": "test-user-123", "canal": "email", "tipo_evento": "novo_lead", "ativo": False},
            {"user_id": "test-user-123", "canal": "app", "tipo_evento": "novo_lead", "ativo": True},
        ])
        resp = client.get("/api/notificacoes/preferencias")
        assert resp.status_code == 200
        rows = resp.json()["data"]
        assert {(r["canal"], r["tipo_evento"], r["ativo"]) for r in rows} == {
            ("email", "novo_lead", False),
            ("app", "novo_lead", True),
        }

    def test_returns_empty_list_when_nothing_saved(self, client):
        client._mock_supabase.set_table_data("notificacao_preferencias", [])
        resp = client.get("/api/notificacoes/preferencias")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestAtualizarPreferencia:
    def test_upsert_success(self, client):
        client._mock_supabase.set_table_data("notificacao_preferencias", {
            "org_id": "org-1",
            "user_id": "user-1",
            "canal": "whatsapp",
            "tipo_evento": "pagamento_atrasado",
            "ativo": False,
        })
        resp = client.patch("/api/notificacoes/preferencias", json={
            "canal": "whatsapp",
            "tipo_evento": "pagamento_atrasado",
            "ativo": False,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["canal"] == "whatsapp"
        assert resp.json()["data"]["ativo"] is False

    def test_rejects_unknown_canal(self, client):
        resp = client.patch("/api/notificacoes/preferencias", json={
            "canal": "sms",
            "tipo_evento": "novo_lead",
            "ativo": True,
        })
        assert resp.status_code == 422

    def test_rejects_missing_fields(self, client):
        resp = client.patch("/api/notificacoes/preferencias", json={"canal": "app"})
        assert resp.status_code == 422
