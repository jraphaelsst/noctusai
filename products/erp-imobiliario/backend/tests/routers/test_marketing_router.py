"""
Tests for the Marketing router — /api/marketing
Covers campaigns CRUD, campaign send, and alert processing.
"""
import pytest
from unittest.mock import patch


class TestListarCampanhas:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("campanhas", [
            {"id": "c1", "nome": "Black Friday", "tipo": "email", "status": "ativa"},
            {"id": "c2", "nome": "Lancamento", "tipo": "whatsapp", "status": "rascunho"},
        ])
        resp = client.get("/api/marketing/campanhas")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("campanhas", [
            {"id": "c1", "nome": "Ativa", "tipo": "email", "status": "ativa"},
        ])
        resp = client.get("/api/marketing/campanhas?status=ativa")
        assert resp.status_code == 200

    def test_filter_by_tipo(self, client):
        client._mock_supabase.set_table_data("campanhas", [
            {"id": "c1", "nome": "WhatsApp", "tipo": "whatsapp", "status": "rascunho"},
        ])
        resp = client.get("/api/marketing/campanhas?tipo=whatsapp")
        assert resp.status_code == 200

    def test_pagination_params(self, client):
        client._mock_supabase.set_table_data("campanhas", [])
        resp = client.get("/api/marketing/campanhas?page=2&page_size=10")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page"] == 2


class TestCriarCampanha:
    def test_create_success(self, client):
        client._mock_supabase.set_table_data("campanhas", {
            "id": "new-c", "nome": "Nova Campanha", "tipo": "email",
            "status": "rascunho", "template": "Ola {nome}",
        })
        resp = client.post("/api/marketing/campanhas", json={
            "nome": "Nova Campanha",
            "tipo": "email",
            "template": "Ola {nome}",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "new-c"

    def test_create_with_filtros(self, client):
        client._mock_supabase.set_table_data("campanhas", {
            "id": "new-c2", "nome": "Filtrada", "tipo": "alerta_imovel",
            "template": "Novo imovel", "filtros": {"origem": "website"},
        })
        resp = client.post("/api/marketing/campanhas", json={
            "nome": "Filtrada",
            "tipo": "alerta_imovel",
            "template": "Novo imovel",
            "filtros": {"origem": "website"},
        })
        assert resp.status_code == 200

    def test_create_missing_nome(self, client):
        resp = client.post("/api/marketing/campanhas", json={
            "tipo": "email",
            "template": "Ola",
        })
        assert resp.status_code == 422

    def test_create_missing_tipo(self, client):
        resp = client.post("/api/marketing/campanhas", json={
            "nome": "Test",
            "template": "Ola",
        })
        assert resp.status_code == 422

    def test_create_missing_template(self, client):
        resp = client.post("/api/marketing/campanhas", json={
            "nome": "Test",
            "tipo": "email",
        })
        assert resp.status_code == 422

    def test_create_invalid_tipo(self, client):
        resp = client.post("/api/marketing/campanhas", json={
            "nome": "Test",
            "tipo": "sms",
            "template": "Ola",
        })
        assert resp.status_code == 422


class TestObterCampanha:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("campanhas", {
            "id": "c1", "nome": "Black Friday", "tipo": "email", "status": "ativa",
        })
        client._mock_supabase.set_table_data("envios_email", [])
        resp = client.get("/api/marketing/campanhas/c1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "c1"
        assert "stats" in data

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("campanhas", None)
        resp = client.get("/api/marketing/campanhas/nonexistent")
        assert resp.status_code == 404


class TestAtualizarCampanha:
    def test_update_nome(self, client):
        client._mock_supabase.set_table_data("campanhas", {
            "id": "c1", "nome": "Updated", "tipo": "email", "status": "ativa",
        })
        resp = client.patch("/api/marketing/campanhas/c1", json={"nome": "Updated"})
        assert resp.status_code == 200

    def test_update_status(self, client):
        client._mock_supabase.set_table_data("campanhas", {
            "id": "c1", "nome": "Test", "tipo": "email", "status": "pausada",
        })
        resp = client.patch("/api/marketing/campanhas/c1", json={"status": "pausada"})
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/marketing/campanhas/c1", json={})
        assert resp.status_code == 400

    def test_update_not_found(self, client):
        client._mock_supabase.set_table_data("campanhas", None)
        resp = client.patch("/api/marketing/campanhas/nonexistent", json={"nome": "X"})
        assert resp.status_code == 404

    def test_update_invalid_status(self, client):
        resp = client.patch("/api/marketing/campanhas/c1", json={"status": "invalido"})
        assert resp.status_code == 422


class TestExcluirCampanha:
    def test_delete_success(self, client):
        client._mock_supabase.set_table_data("campanhas", {
            "id": "c1", "nome": "Test", "tipo": "email",
            "status": "rascunho", "template": "Ola",
        })
        client._mock_supabase.set_table_data("envios_email", [])
        resp = client.delete("/api/marketing/campanhas/c1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_message(self, client):
        client._mock_supabase.set_table_data("campanhas", {
            "id": "c1", "nome": "Test", "tipo": "email",
            "status": "rascunho", "template": "Ola",
        })
        client._mock_supabase.set_table_data("envios_email", [])
        resp = client.delete("/api/marketing/campanhas/c1")
        assert "sucesso" in resp.json()["message"].lower()

    def test_delete_not_found(self, client):
        resp = client.delete("/api/marketing/campanhas/nonexistent")
        assert resp.status_code == 404


class TestEnviarCampanha:
    def test_enviar_success(self, client):
        client._mock_supabase.set_table_data("campanhas", {
            "id": "c1", "nome": "Test", "tipo": "email",
            "status": "rascunho", "filtros": {},
        })
        client._mock_supabase.set_table_data("clientes", [
            {"id": "cl1", "email": "joao@test.com", "nome": "Joao"},
            {"id": "cl2", "email": "maria@test.com", "nome": "Maria"},
        ])
        client._mock_supabase.set_table_data("envios_email", [])
        resp = client.post("/api/marketing/campanhas/c1/enviar")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_destinatarios"] == 2

    def test_enviar_campanha_not_found(self, client):
        client._mock_supabase.set_table_data("campanhas", None)
        resp = client.post("/api/marketing/campanhas/nonexistent/enviar")
        assert resp.status_code == 404

    def test_enviar_campanha_invalid_status(self, client):
        client._mock_supabase.set_table_data("campanhas", {
            "id": "c1", "nome": "Test", "tipo": "email",
            "status": "concluida", "filtros": {},
        })
        resp = client.post("/api/marketing/campanhas/c1/enviar")
        assert resp.status_code == 400

    def test_enviar_no_clients_with_email(self, client):
        client._mock_supabase.set_table_data("campanhas", {
            "id": "c1", "nome": "Test", "tipo": "email",
            "status": "ativa", "filtros": {},
        })
        client._mock_supabase.set_table_data("clientes", [
            {"id": "cl1", "email": None, "nome": "Sem Email"},
        ])
        resp = client.post("/api/marketing/campanhas/c1/enviar")
        assert resp.status_code == 400


class TestProcessarAlertas:
    def test_alertas_success(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        client._mock_supabase.set_table_data("clientes", [])
        resp = client.get("/api/marketing/alertas")
        assert resp.status_code == 200
        assert "data" in resp.json()


class TestNoAuth:
    def test_no_token_campanhas(self, client):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        resp = tc.get("/api/marketing/campanhas")
        assert resp.status_code == 401
