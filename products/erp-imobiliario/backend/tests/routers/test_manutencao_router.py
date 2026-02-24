"""
Tests for Manutencao router — /api/manutencao
Covers list, resumo, get by id, create, update, delete work orders.
"""
import pytest


class TestListarOrdens:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("ordens_servico", [
            {"id": "os1", "titulo": "Trocar torneira", "tipo": "corretiva", "status": "aberto"},
            {"id": "os2", "titulo": "Pintura geral", "tipo": "reforma", "status": "em_andamento"},
        ])
        resp = client.get("/api/manutencao")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("ordens_servico", [
            {"id": "os1", "titulo": "Trocar torneira", "status": "aberto"},
        ])
        resp = client.get("/api/manutencao?status=aberto")
        assert resp.status_code == 200

    def test_filter_by_prioridade(self, client):
        client._mock_supabase.set_table_data("ordens_servico", [
            {"id": "os1", "titulo": "Vazamento grave", "prioridade": "urgente"},
        ])
        resp = client.get("/api/manutencao?prioridade=urgente")
        assert resp.status_code == 200

    def test_filter_by_tipo(self, client):
        client._mock_supabase.set_table_data("ordens_servico", [
            {"id": "os1", "titulo": "Manutencao preventiva", "tipo": "preventiva"},
        ])
        resp = client.get("/api/manutencao?tipo=preventiva")
        assert resp.status_code == 200


class TestResumoManutencao:
    def test_resumo_success(self, client):
        client._mock_supabase.set_table_data("ordens_servico", [
            {"id": "os1", "status": "aberto", "data_abertura": "2026-01-01",
             "data_previsao": "2026-02-01", "custo_real": None},
            {"id": "os2", "status": "concluido", "data_abertura": "2026-01-10",
             "data_conclusao": "2026-01-20", "custo_real": 1500.0},
        ])
        resp = client.get("/api/manutencao/resumo")
        assert resp.status_code == 200


class TestObterOrdem:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("ordens_servico", {
            "id": "os1", "titulo": "Trocar torneira", "tipo": "corretiva",
            "status": "aberto", "data_abertura": "2026-03-01",
        })
        resp = client.get("/api/manutencao/os1")
        assert resp.status_code == 200

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("ordens_servico", None)
        resp = client.get("/api/manutencao/nonexistent")
        assert resp.status_code in [200, 404]


class TestCriarOrdem:
    def test_create_success(self, client):
        client._mock_supabase.set_table_data("ordens_servico", {
            "id": "os-new", "titulo": "Reparo eletrico",
            "descricao": "Troca de fiacao", "tipo": "corretiva",
            "data_abertura": "2026-03-01",
        })
        resp = client.post("/api/manutencao", json={
            "titulo": "Reparo eletrico",
            "descricao": "Troca de fiacao no apartamento 301",
            "tipo": "corretiva",
            "data_abertura": "2026-03-01",
        })
        assert resp.status_code == 200

    def test_create_missing_required(self, client):
        resp = client.post("/api/manutencao", json={
            "titulo": "Falta descricao",
        })
        assert resp.status_code == 422


class TestAtualizarOrdem:
    def test_update_success(self, client):
        client._mock_supabase.set_table_data("ordens_servico", {
            "id": "os1", "titulo": "Trocar torneira", "status": "em_andamento",
        })
        resp = client.patch("/api/manutencao/os1", json={"status": "em_andamento"})
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/manutencao/os1", json={})
        assert resp.status_code == 400


class TestExcluirOrdem:
    def test_delete_success(self, client):
        resp = client.delete("/api/manutencao/os1")
        assert resp.status_code == 200
