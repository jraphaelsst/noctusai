"""
Tests for the Chaves (Key Control) router — /api/chaves
Covers key registration, CRUD, checkout (retirada), return (devolucao), and history.
"""
import pytest

from tests.conftest import MockSupabaseResponse


class TestListarChaves:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("chaves", [
            {"id": "ch1", "codigo": "AP101-A", "status": "disponivel", "imovel_id": "im-1"},
            {"id": "ch2", "codigo": "CS202-B", "status": "emprestada", "imovel_id": "im-2"},
        ])
        resp = client.get("/api/chaves")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("chaves", [
            {"id": "ch1", "codigo": "AP101-A", "status": "disponivel"},
        ])
        resp = client.get("/api/chaves?status=disponivel")
        assert resp.status_code == 200

    def test_filter_by_imovel_id(self, client):
        client._mock_supabase.set_table_data("chaves", [])
        resp = client.get("/api/chaves?imovel_id=im-1")
        assert resp.status_code == 200

    def test_pagination(self, client):
        client._mock_supabase.set_table_data("chaves", [])
        resp = client.get("/api/chaves?page=2&page_size=25")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page"] == 2


class TestCriarChave:
    def test_create_success(self, client):
        client._mock_supabase.set_sequential_responses("chaves", [
            MockSupabaseResponse(data=[{
                "id": "ch-new", "codigo": "AP101-A", "imovel_id": "im-1",
                "status": "disponivel", "descricao": "Chave principal",
            }]),
        ])
        resp = client.post("/api/chaves", json={
            "imovel_id": "im-1",
            "codigo": "AP101-A",
            "descricao": "Chave principal",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "ch-new"

    def test_create_minimal(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch-min", "codigo": "CS202", "imovel_id": "im-2",
            "status": "disponivel",
        })
        resp = client.post("/api/chaves", json={
            "imovel_id": "im-2",
            "codigo": "CS202",
        })
        assert resp.status_code == 200

    def test_create_with_observacoes(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch-obs", "codigo": "AP303", "imovel_id": "im-3",
            "status": "disponivel", "observacoes": "Chave reserva",
        })
        resp = client.post("/api/chaves", json={
            "imovel_id": "im-3",
            "codigo": "AP303",
            "observacoes": "Chave reserva",
        })
        assert resp.status_code == 200

    def test_create_missing_imovel_id(self, client):
        resp = client.post("/api/chaves", json={
            "codigo": "AP101-A",
        })
        assert resp.status_code == 422

    def test_create_missing_codigo(self, client):
        resp = client.post("/api/chaves", json={
            "imovel_id": "im-1",
        })
        assert resp.status_code == 422

    def test_create_empty_codigo(self, client):
        resp = client.post("/api/chaves", json={
            "imovel_id": "im-1",
            "codigo": "",
        })
        assert resp.status_code == 422


class TestObterChave:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch1", "codigo": "AP101-A", "status": "disponivel", "imovel_id": "im-1",
        })
        client._mock_supabase.set_table_data("chaves_historico", [])
        resp = client.get("/api/chaves/ch1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "ch1"
        assert "historico" in data

    def test_get_with_history(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch1", "codigo": "AP101-A", "status": "emprestada", "imovel_id": "im-1",
        })
        client._mock_supabase.set_table_data("chaves_historico", [
            {"id": "h1", "chave_id": "ch1", "acao": "retirada",
             "corretor_nome": "Ana", "corretor_id": "u1"},
        ])
        resp = client.get("/api/chaves/ch1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["historico"]) == 1

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("chaves", None)
        resp = client.get("/api/chaves/nonexistent")
        assert resp.status_code == 404


class TestAtualizarChave:
    def test_update_codigo(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch1", "codigo": "AP101-B", "status": "disponivel", "imovel_id": "im-1",
        })
        resp = client.patch("/api/chaves/ch1", json={"codigo": "AP101-B"})
        assert resp.status_code == 200

    def test_update_descricao(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch1", "codigo": "AP101-A", "descricao": "Atualizada",
        })
        resp = client.patch("/api/chaves/ch1", json={"descricao": "Atualizada"})
        assert resp.status_code == 200

    def test_update_status(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch1", "codigo": "AP101-A", "status": "perdida",
        })
        resp = client.patch("/api/chaves/ch1", json={"status": "perdida"})
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/chaves/ch1", json={})
        assert resp.status_code == 400

    def test_update_not_found(self, client):
        client._mock_supabase.set_table_data("chaves", None)
        resp = client.patch("/api/chaves/nonexistent", json={"codigo": "X"})
        assert resp.status_code == 404

    def test_update_invalid_status(self, client):
        resp = client.patch("/api/chaves/ch1", json={"status": "invalido"})
        assert resp.status_code == 422


class TestRetiradaChave:
    def test_retirada_success(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch1", "codigo": "AP101-A", "status": "disponivel", "imovel_id": "im-1",
        })
        client._mock_supabase.set_table_data("chaves_historico", [])
        resp = client.post("/api/chaves/ch1/retirada", json={
            "corretor_nome": "Ana Santos",
        })
        assert resp.status_code == 200

    def test_retirada_with_motivo(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch1", "codigo": "AP101-A", "status": "disponivel", "imovel_id": "im-1",
        })
        client._mock_supabase.set_table_data("chaves_historico", [])
        resp = client.post("/api/chaves/ch1/retirada", json={
            "corretor_nome": "Carlos Lima",
            "motivo": "Visita agendada com cliente",
        })
        assert resp.status_code == 200

    def test_retirada_chave_ja_emprestada(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch1", "codigo": "AP101-A", "status": "emprestada", "imovel_id": "im-1",
        })
        resp = client.post("/api/chaves/ch1/retirada", json={
            "corretor_nome": "Ana Santos",
        })
        assert resp.status_code == 409

    def test_retirada_chave_perdida(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch1", "codigo": "AP101-A", "status": "perdida", "imovel_id": "im-1",
        })
        resp = client.post("/api/chaves/ch1/retirada", json={
            "corretor_nome": "Ana Santos",
        })
        assert resp.status_code == 409

    def test_retirada_chave_not_found(self, client):
        client._mock_supabase.set_table_data("chaves", None)
        resp = client.post("/api/chaves/nonexistent/retirada", json={
            "corretor_nome": "Ana Santos",
        })
        assert resp.status_code == 404

    def test_retirada_missing_corretor_nome(self, client):
        resp = client.post("/api/chaves/ch1/retirada", json={})
        assert resp.status_code == 422


class TestDevolucaoChave:
    def test_devolucao_success(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch1", "codigo": "AP101-A", "status": "emprestada", "imovel_id": "im-1",
        })
        client._mock_supabase.set_table_data("chaves_historico", [])
        resp = client.post("/api/chaves/ch1/devolucao", json={
            "corretor_nome": "Ana Santos",
        })
        assert resp.status_code == 200

    def test_devolucao_with_motivo(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch1", "codigo": "AP101-A", "status": "emprestada", "imovel_id": "im-1",
        })
        client._mock_supabase.set_table_data("chaves_historico", [])
        resp = client.post("/api/chaves/ch1/devolucao", json={
            "corretor_nome": "Carlos Lima",
            "motivo": "Visita concluida",
        })
        assert resp.status_code == 200

    def test_devolucao_chave_ja_disponivel(self, client):
        client._mock_supabase.set_table_data("chaves", {
            "id": "ch1", "codigo": "AP101-A", "status": "disponivel", "imovel_id": "im-1",
        })
        resp = client.post("/api/chaves/ch1/devolucao", json={
            "corretor_nome": "Ana Santos",
        })
        assert resp.status_code == 409

    def test_devolucao_chave_not_found(self, client):
        client._mock_supabase.set_table_data("chaves", None)
        resp = client.post("/api/chaves/nonexistent/devolucao", json={
            "corretor_nome": "Ana Santos",
        })
        assert resp.status_code == 404

    def test_devolucao_missing_corretor_nome(self, client):
        resp = client.post("/api/chaves/ch1/devolucao", json={})
        assert resp.status_code == 422


class TestHistoricoChave:
    def test_historico_success(self, client):
        client._mock_supabase.set_table_data("chaves_historico", [
            {"id": "h1", "chave_id": "ch1", "acao": "retirada",
             "corretor_nome": "Ana", "corretor_id": "u1"},
            {"id": "h2", "chave_id": "ch1", "acao": "devolucao",
             "corretor_nome": "Ana", "corretor_id": "u1"},
        ])
        resp = client.get("/api/chaves/ch1/historico")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_historico_empty(self, client):
        client._mock_supabase.set_table_data("chaves_historico", [])
        resp = client.get("/api/chaves/ch1/historico")
        assert resp.status_code == 200

    def test_historico_pagination(self, client):
        client._mock_supabase.set_table_data("chaves_historico", [])
        resp = client.get("/api/chaves/ch1/historico?page=1&page_size=10")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page_size"] == 10


class TestNoAuth:
    def test_no_token(self, client):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        resp = tc.get("/api/chaves")
        assert resp.status_code == 401
