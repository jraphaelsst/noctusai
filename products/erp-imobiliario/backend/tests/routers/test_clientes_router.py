"""
Tests for the Clientes CRUD router.
Covers create, read, update, delete, archive, move pipeline stage.
"""
import pytest


class TestListarClientes:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "João", "email": "joao@test.com", "arquivado": False},
            {"id": "c2", "nome": "Maria", "email": "maria@test.com", "arquivado": False},
        ])
        resp = client.get("/api/clientes")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["total"] == 2

    def test_search_by_name(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "João Silva", "email": None, "telefone": None},
            {"id": "c2", "nome": "Maria Santos", "email": None, "telefone": None},
        ])
        resp = client.get("/api/clientes?busca=joão")
        assert resp.json()["pagination"]["total"] == 1

    def test_search_by_email(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "Test", "email": "special@company.com",
             "telefone": None, "interesse": None, "observacoes": None},
        ])
        resp = client.get("/api/clientes?busca=special")
        assert resp.json()["pagination"]["total"] == 1

    def test_search_no_results(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "Test", "email": "test@test.com",
             "telefone": None, "interesse": None, "observacoes": None},
        ])
        resp = client.get("/api/clientes?busca=xyz999")
        assert resp.json()["pagination"]["total"] == 0

    def test_filter_by_etapa(self, client):
        resp = client.get("/api/clientes?etapa=qualificacao")
        assert resp.status_code == 200

    def test_filter_by_origem(self, client):
        resp = client.get("/api/clientes?origem=website")
        assert resp.status_code == 200


class TestCriarCliente:
    def test_create_success(self, client):
        client._mock_supabase.set_table_data("clientes", {"id": "new-c", "nome": "Novo"})
        resp = client.post("/api/clientes", json={"nome": "Novo Cliente"})
        assert resp.status_code == 200

    def test_create_with_all_fields(self, client):
        client._mock_supabase.set_table_data("clientes", {"id": "full-c", "nome": "Full"})
        resp = client.post("/api/clientes", json={
            "nome": "Full Client",
            "email": "full@test.com",
            "telefone": "11999999999",
            "origem": "indicação",
            "interesse": "Apartamento 3 quartos",
            "observacoes": "Urgente",
            "probabilidade": 80,
            "valor_estimado": 500000,
        })
        assert resp.status_code == 200

    def test_create_missing_nome(self, client):
        resp = client.post("/api/clientes", json={"email": "noname@test.com"})
        assert resp.status_code == 422


class TestAtualizarCliente:
    def test_update_nome(self, client):
        client._mock_supabase.set_table_data("clientes", {"id": "upd-c", "nome": "Updated"})
        resp = client.patch("/api/clientes/upd-c", json={"nome": "Updated Name"})
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/clientes/upd-c", json={})
        assert resp.status_code == 400


class TestExcluirCliente:
    def test_delete(self, client):
        resp = client.delete("/api/clientes/del-c")
        assert resp.status_code == 200


class TestArquivarCliente:
    def test_toggle_archive(self, client):
        client._mock_supabase.set_table_data("clientes", {"arquivado": False, "nome": "Test"})
        resp = client.post("/api/clientes/c1/arquivar")
        assert resp.status_code == 200


class TestMoverEtapa:
    def test_mover_success(self, client):
        client._mock_supabase.set_table_data("clientes", {"id": "c1", "etapa_atual": "visitas"})
        resp = client.post("/api/clientes/c1/mover-etapa", json={"para_etapa": "visitas"})
        assert resp.status_code == 200

    def test_mover_invalid_etapa(self, client):
        resp = client.post("/api/clientes/c1/mover-etapa", json={"para_etapa": "invalid_stage"})
        assert resp.status_code == 400

    def test_mover_with_motivo(self, client):
        client._mock_supabase.set_table_data("clientes", {"id": "c1", "etapa_atual": "proposta"})
        resp = client.post("/api/clientes/c1/mover-etapa", json={
            "para_etapa": "proposta", "motivo": "Enviou proposta formal"
        })
        assert resp.status_code == 200

    def test_mover_with_position(self, client):
        client._mock_supabase.set_table_data("clientes", {"id": "c1", "etapa_atual": "negociacao"})
        resp = client.post("/api/clientes/c1/mover-etapa", json={
            "para_etapa": "negociacao", "novo_indice": 0
        })
        assert resp.status_code == 200
