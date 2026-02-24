"""
Tests for Relatorios (Reports) router — /api/relatorios
Covers ranking, funnel conversion, monthly activity, and CSV export.
"""
import pytest


class TestRankingCorretores:
    def test_ranking_success(self, client):
        client._mock_supabase.set_table_data("profiles", [
            {"id": "u1", "nome": "Corretor A", "email": "a@test.com"},
            {"id": "u2", "nome": "Corretor B", "email": "b@test.com"},
        ])
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "usuario_id": "u1", "etapa_atual": "fechado",
             "valor_estimado": 500000, "created_at": "2026-01-10T10:00:00Z"},
            {"id": "c2", "usuario_id": "u2", "etapa_atual": "qualificacao",
             "valor_estimado": 200000, "created_at": "2026-02-01T10:00:00Z"},
        ])
        client._mock_supabase.set_table_data("atividades", [
            {"id": "a1", "usuario_id": "u1", "created_at": "2026-01-11T10:00:00Z"},
            {"id": "a2", "usuario_id": "u1", "created_at": "2026-01-12T10:00:00Z"},
        ])
        resp = client.get("/api/relatorios/ranking-corretores")
        assert resp.status_code == 200

    def test_ranking_with_periodo(self, client):
        client._mock_supabase.set_table_data("profiles", [
            {"id": "u1", "nome": "Corretor A", "email": "a@test.com"},
        ])
        client._mock_supabase.set_table_data("clientes", [])
        client._mock_supabase.set_table_data("atividades", [])
        resp = client.get("/api/relatorios/ranking-corretores?periodo=90")
        assert resp.status_code == 200

    def test_ranking_empty_profiles(self, client):
        client._mock_supabase.set_table_data("profiles", [])
        client._mock_supabase.set_table_data("clientes", [])
        client._mock_supabase.set_table_data("atividades", [])
        resp = client.get("/api/relatorios/ranking-corretores")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data == []


class TestConversaoFunil:
    def test_conversao_success(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "etapa_atual": "qualificacao", "arquivado": False},
            {"id": "c2", "etapa_atual": "visitas", "arquivado": False},
            {"id": "c3", "etapa_atual": "proposta", "arquivado": False},
            {"id": "c4", "etapa_atual": "fechado", "arquivado": False},
        ])
        resp = client.get("/api/relatorios/conversao-funil")
        assert resp.status_code == 200

    def test_conversao_empty(self, client):
        client._mock_supabase.set_table_data("clientes", [])
        resp = client.get("/api/relatorios/conversao-funil")
        assert resp.status_code == 200


class TestAtividadeMensal:
    def test_atividade_mensal_success(self, client):
        client._mock_supabase.set_table_data("atividades", [
            {"id": "a1", "created_at": "2026-02-10T10:00:00Z"},
            {"id": "a2", "created_at": "2026-01-15T10:00:00Z"},
        ])
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "etapa_atual": "qualificacao",
             "created_at": "2026-02-01T10:00:00Z"},
            {"id": "c2", "etapa_atual": "fechado",
             "created_at": "2026-01-20T10:00:00Z"},
        ])
        resp = client.get("/api/relatorios/atividade-mensal")
        assert resp.status_code == 200

    def test_atividade_mensal_custom_meses(self, client):
        client._mock_supabase.set_table_data("atividades", [])
        client._mock_supabase.set_table_data("clientes", [])
        resp = client.get("/api/relatorios/atividade-mensal?meses=12")
        assert resp.status_code == 200

    def test_atividade_mensal_empty(self, client):
        client._mock_supabase.set_table_data("atividades", [])
        client._mock_supabase.set_table_data("clientes", [])
        resp = client.get("/api/relatorios/atividade-mensal")
        assert resp.status_code == 200


class TestExportCSV:
    def test_export_ranking_csv(self, client):
        client._mock_supabase.set_table_data("profiles", [
            {"id": "u1", "nome": "Corretor A", "email": "a@test.com"},
        ])
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "usuario_id": "u1", "etapa_atual": "fechado",
             "valor_estimado": 300000, "created_at": "2026-01-05T10:00:00Z"},
        ])
        client._mock_supabase.set_table_data("atividades", [])
        resp = client.get("/api/relatorios/export/csv?tipo=ranking-corretores")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_export_conversao_csv(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "etapa_atual": "qualificacao", "arquivado": False},
        ])
        resp = client.get("/api/relatorios/export/csv?tipo=conversao-funil")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_export_atividade_csv(self, client):
        client._mock_supabase.set_table_data("atividades", [])
        client._mock_supabase.set_table_data("clientes", [])
        resp = client.get("/api/relatorios/export/csv?tipo=atividade-mensal")
        assert resp.status_code == 200

    def test_export_invalid_tipo(self, client):
        resp = client.get("/api/relatorios/export/csv?tipo=invalido")
        assert resp.status_code == 400
