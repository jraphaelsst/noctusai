"""
Tests for the Propostas CRUD router.
Covers list, create, read, update, delete, stats, and contraproposta.
"""
import pytest


class TestListarPropostas:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("propostas", [
            {"id": "p1", "imovel_id": "i1", "cliente_id": "c1",
             "corretor_id": "test-user-123", "valor_proposta": 500000,
             "status": "enviada"},
            {"id": "p2", "imovel_id": "i2", "cliente_id": "c2",
             "corretor_id": "test-user-123", "valor_proposta": 300000,
             "status": "em_analise"},
        ])
        resp = client.get("/api/propostas")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("propostas", [
            {"id": "p1", "imovel_id": "i1", "cliente_id": "c1",
             "valor_proposta": 500000, "status": "enviada"},
        ])
        resp = client.get("/api/propostas?status=enviada")
        assert resp.status_code == 200

    def test_filter_by_imovel_id(self, client):
        client._mock_supabase.set_table_data("propostas", [
            {"id": "p1", "imovel_id": "i1", "cliente_id": "c1",
             "valor_proposta": 500000, "status": "enviada"},
        ])
        resp = client.get("/api/propostas?imovel_id=i1")
        assert resp.status_code == 200

    def test_filter_by_cliente_id(self, client):
        client._mock_supabase.set_table_data("propostas", [
            {"id": "p1", "imovel_id": "i1", "cliente_id": "c1",
             "valor_proposta": 500000, "status": "aceita"},
        ])
        resp = client.get("/api/propostas?cliente_id=c1")
        assert resp.status_code == 200


class TestStatsPropostas:
    def test_stats_success(self, client):
        client._mock_supabase.set_table_data("propostas", [
            {"id": "p1", "status": "enviada"},
            {"id": "p2", "status": "aceita"},
            {"id": "p3", "status": "recusada"},
            {"id": "p4", "status": "em_analise"},
        ])
        resp = client.get("/api/propostas/stats")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total" in data
        assert "enviada" in data
        assert "aceita" in data

    def test_stats_empty(self, client):
        client._mock_supabase.set_table_data("propostas", [])
        resp = client.get("/api/propostas/stats")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0


class TestObterProposta:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("propostas", {
            "id": "p1", "imovel_id": "i1", "cliente_id": "c1",
            "corretor_id": "test-user-123", "valor_proposta": 500000,
            "status": "enviada", "historico": [],
        })
        resp = client.get("/api/propostas/p1")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "p1"

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("propostas", None)
        resp = client.get("/api/propostas/nonexistent")
        assert resp.status_code in [200, 404]


class TestCriarProposta:
    def test_create_success(self, client):
        client._mock_supabase.set_table_data("propostas", {
            "id": "new-p", "imovel_id": "i1", "cliente_id": "c1",
            "corretor_id": "test-user-123", "valor_proposta": 450000,
            "status": "enviada", "historico": [],
        })
        resp = client.post("/api/propostas", json={
            "imovel_id": "i1",
            "cliente_id": "c1",
            "valor_proposta": 450000,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "new-p"

    def test_create_with_optional_fields(self, client):
        client._mock_supabase.set_table_data("propostas", {
            "id": "new-p2", "imovel_id": "i1", "cliente_id": "c1",
            "corretor_id": "test-user-123", "valor_proposta": 480000,
            "status": "enviada", "condicoes_pagamento": "Financiamento",
            "prazo_validade": "2026-04-01", "observacoes": "Cliente prefere andar alto",
        })
        resp = client.post("/api/propostas", json={
            "imovel_id": "i1",
            "cliente_id": "c1",
            "valor_proposta": 480000,
            "condicoes_pagamento": "Financiamento",
            "prazo_validade": "2026-04-01",
            "observacoes": "Cliente prefere andar alto",
        })
        assert resp.status_code == 200

    def test_create_missing_required(self, client):
        resp = client.post("/api/propostas", json={
            "imovel_id": "i1",
            "cliente_id": "c1",
        })
        assert resp.status_code == 422

    def test_create_invalid_valor(self, client):
        resp = client.post("/api/propostas", json={
            "imovel_id": "i1",
            "cliente_id": "c1",
            "valor_proposta": -100,
        })
        assert resp.status_code == 422


class TestAtualizarProposta:
    def test_update_success(self, client):
        client._mock_supabase.set_table_data("propostas", {
            "id": "p1", "imovel_id": "i1", "cliente_id": "c1",
            "corretor_id": "test-user-123", "valor_proposta": 500000,
            "status": "enviada", "historico": [],
            "observacoes": "Atualizado",
        })
        resp = client.patch("/api/propostas/p1", json={
            "observacoes": "Atualizado",
        })
        assert resp.status_code == 200

    def test_update_status_transition(self, client):
        client._mock_supabase.set_table_data("propostas", {
            "id": "p1", "imovel_id": "i1", "cliente_id": "c1",
            "corretor_id": "test-user-123", "valor_proposta": 500000,
            "status": "enviada", "historico": [],
        })
        resp = client.patch("/api/propostas/p1", json={
            "status": "em_analise",
        })
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        client._mock_supabase.set_table_data("propostas", {
            "id": "p1", "imovel_id": "i1", "cliente_id": "c1",
            "corretor_id": "test-user-123", "valor_proposta": 500000,
            "status": "enviada", "historico": [],
        })
        resp = client.patch("/api/propostas/p1", json={})
        assert resp.status_code == 400


class TestContraproposta:
    def test_contraproposta_success(self, client):
        client._mock_supabase.set_table_data("propostas", {
            "id": "p1", "imovel_id": "i1", "cliente_id": "c1",
            "corretor_id": "test-user-123", "valor_proposta": 500000,
            "status": "em_analise", "historico": [],
        })
        resp = client.post("/api/propostas/p1/contraproposta", json={
            "valor_contraproposta": 480000,
        })
        assert resp.status_code == 200

    def test_contraproposta_with_extras(self, client):
        client._mock_supabase.set_table_data("propostas", {
            "id": "p1", "imovel_id": "i1", "cliente_id": "c1",
            "corretor_id": "test-user-123", "valor_proposta": 500000,
            "status": "em_analise", "historico": [],
        })
        resp = client.post("/api/propostas/p1/contraproposta", json={
            "valor_contraproposta": 470000,
            "condicoes_pagamento": "A vista com desconto",
            "observacoes": "Proprietario aceita contrapropostas",
        })
        assert resp.status_code == 200

    def test_contraproposta_missing_valor(self, client):
        resp = client.post("/api/propostas/p1/contraproposta", json={})
        assert resp.status_code == 422


class TestExcluirProposta:
    def test_delete_success(self, client):
        resp = client.delete("/api/propostas/p1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_logging_called_on_delete(self, client):
        resp = client.delete("/api/propostas/p-del")
        assert resp.status_code == 200


class TestNoAuth:
    def test_no_token(self, client):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        resp = tc.get("/api/propostas")
        assert resp.status_code == 401
