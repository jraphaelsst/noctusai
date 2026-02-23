"""
Tests for Funil (pipeline/kanban) router — /api/funil
"""
import pytest


class TestGetFunil:
    def test_get_funil(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "João", "etapa_atual": "qualificacao",
             "kanban_pos": 0, "valor_estimado": 100000, "email": None, "telefone": None},
            {"id": "c2", "nome": "Maria", "etapa_atual": "proposta",
             "kanban_pos": 0, "valor_estimado": 200000, "email": None, "telefone": None},
        ])
        resp = client.get("/api/funil")
        assert resp.status_code == 200
        colunas = resp.json()["data"]
        assert len(colunas) == 5  # 5 etapas
        etapas = [c["etapa"] for c in colunas]
        assert "qualificacao" in etapas
        assert "proposta" in etapas

    def test_funil_empty(self, client):
        client._mock_supabase.set_table_data("clientes", [])
        resp = client.get("/api/funil")
        colunas = resp.json()["data"]
        assert all(c["total"] == 0 for c in colunas)


class TestFunilGrouping:
    def test_funil_grouping_correct(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "A", "etapa_atual": "qualificacao",
             "kanban_pos": 0, "valor_estimado": 50000, "email": None, "telefone": None},
            {"id": "c2", "nome": "B", "etapa_atual": "qualificacao",
             "kanban_pos": 1, "valor_estimado": 100000, "email": None, "telefone": None},
        ])
        resp = client.get("/api/funil")
        colunas = resp.json()["data"]
        qualificacao = next(c for c in colunas if c["etapa"] == "qualificacao")
        assert qualificacao["total"] == 2
        assert qualificacao["valorTotal"] == 150000


class TestFunilSearch:
    def test_funil_search_filters(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "João Silva", "etapa_atual": "qualificacao",
             "kanban_pos": 0, "valor_estimado": 0, "email": None, "telefone": None},
            {"id": "c2", "nome": "Maria Santos", "etapa_atual": "qualificacao",
             "kanban_pos": 0, "valor_estimado": 0, "email": None, "telefone": None},
        ])
        resp = client.get("/api/funil?busca=joão")
        colunas = resp.json()["data"]
        total_cards = sum(c["total"] for c in colunas)
        assert total_cards == 1
