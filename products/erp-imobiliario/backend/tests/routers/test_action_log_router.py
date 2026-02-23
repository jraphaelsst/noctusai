"""
Tests for Action Log router — /api/logs
"""
import pytest


class TestListarLogs:
    def test_list_logs(self, client):
        client._mock_supabase.set_table_data("user_actions_log", [
            {"id": "l1", "usuario_id": "u1", "tipo_acao": "criar",
             "tipo_entidade": "cliente", "descricao": "Criou cliente"},
        ])
        client._mock_supabase.set_table_data("profiles", [
            {"id": "u1", "nome": "Admin", "email": "admin@test.com"},
        ])
        resp = client.get("/api/logs")
        assert resp.status_code == 200

    def test_list_logs_filtered_by_user(self, client):
        resp = client.get("/api/logs?usuario_id=u1")
        assert resp.status_code == 200

    def test_list_logs_filtered_by_date(self, client):
        resp = client.get("/api/logs?data_inicio=2026-01-01T00:00:00Z&data_fim=2026-12-31T23:59:59Z")
        assert resp.status_code == 200
