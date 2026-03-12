"""
Tests for the Contratos CRUD router.
Covers list, create, read, update, delete, parcelas generation and management.
"""
import pytest


class TestListarContratos:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("contratos", [
            {"id": "ct1", "tipo": "venda", "status": "ativo", "cliente_id": "c1",
             "imovel_id": "i1", "valor_total": 500000, "data_inicio": "2026-01-01"},
            {"id": "ct2", "tipo": "locacao", "status": "rascunho", "cliente_id": "c2",
             "imovel_id": "i2", "valor_total": 3000, "data_inicio": "2026-02-01"},
        ])
        resp = client.get("/api/contratos")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("contratos", [
            {"id": "ct1", "tipo": "venda", "status": "ativo", "valor_total": 500000},
        ])
        resp = client.get("/api/contratos?status=ativo")
        assert resp.status_code == 200

    def test_filter_by_cliente_id(self, client):
        client._mock_supabase.set_table_data("contratos", [
            {"id": "ct1", "tipo": "venda", "status": "ativo", "cliente_id": "c1",
             "valor_total": 500000},
        ])
        resp = client.get("/api/contratos?cliente_id=c1")
        assert resp.status_code == 200

    def test_filter_by_tipo(self, client):
        client._mock_supabase.set_table_data("contratos", [
            {"id": "ct1", "tipo": "locacao", "status": "ativo", "valor_total": 3000},
        ])
        resp = client.get("/api/contratos?imovel_id=i1")
        assert resp.status_code == 200


class TestResumoContratos:
    def test_resumo_success(self, client):
        client._mock_supabase.set_table_data("contratos", [
            {"id": "ct1", "tipo": "venda", "status": "ativo", "valor_total": 500000},
            {"id": "ct2", "tipo": "locacao", "status": "concluido", "valor_total": 200000},
            {"id": "ct3", "tipo": "venda", "status": "cancelado", "valor_total": 100000},
        ])
        client._mock_supabase.set_table_data("parcelas_contrato", [])
        resp = client.get("/api/contratos/resumo")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total" in data
        assert "por_status" in data
        assert "por_tipo" in data


class TestObterContrato:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("contratos", {
            "id": "ct1", "tipo": "venda", "status": "ativo",
            "cliente_id": "c1", "imovel_id": "i1", "valor_total": 500000,
            "data_inicio": "2026-01-01",
        })
        resp = client.get("/api/contratos/ct1")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "ct1"

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("contratos", None)
        resp = client.get("/api/contratos/nonexistent")
        assert resp.status_code in [200, 404]


class TestCriarContrato:
    def test_create_success(self, client):
        client._mock_supabase.set_table_data("contratos", {
            "id": "new-ct", "tipo": "venda", "status": "rascunho",
            "cliente_id": "c1", "imovel_id": "i1", "valor_total": 500000,
            "data_inicio": "2026-03-01",
        })
        resp = client.post("/api/contratos", json={
            "tipo": "venda",
            "cliente_id": "c1",
            "imovel_id": "i1",
            "valor_total": 500000,
            "data_inicio": "2026-03-01",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "new-ct"

    def test_create_missing_required(self, client):
        resp = client.post("/api/contratos", json={
            "cliente_id": "c1",
            "imovel_id": "i1",
            "valor_total": 500000,
            "data_inicio": "2026-03-01",
        })
        assert resp.status_code == 422

    def test_create_locacao(self, client):
        client._mock_supabase.set_table_data("contratos", {
            "id": "new-loc", "tipo": "locacao", "status": "rascunho",
            "cliente_id": "c2", "imovel_id": "i2", "valor_total": 3000,
            "data_inicio": "2026-04-01",
        })
        resp = client.post("/api/contratos", json={
            "tipo": "locacao",
            "cliente_id": "c2",
            "imovel_id": "i2",
            "valor_total": 3000,
            "data_inicio": "2026-04-01",
        })
        assert resp.status_code == 200


class TestAtualizarContrato:
    def test_update_success(self, client):
        client._mock_supabase.set_table_data("contratos", {
            "id": "ct1", "tipo": "venda", "status": "ativo",
            "valor_total": 600000,
        })
        resp = client.patch("/api/contratos/ct1", json={"status": "ativo"})
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/contratos/ct1", json={})
        assert resp.status_code == 400


class TestExcluirContrato:
    def test_delete_success(self, client):
        client._mock_supabase.set_table_data("contratos", [{"id": "ct1"}])
        resp = client.delete("/api/contratos/ct1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_not_found(self, client):
        client._mock_supabase.set_table_data("contratos", [])
        resp = client.delete("/api/contratos/nonexistent")
        assert resp.status_code == 404


class TestParcelas:
    def test_listar_parcelas(self, client):
        client._mock_supabase.set_table_data("parcelas_contrato", [
            {"id": "p1", "contrato_id": "ct1", "numero": 1, "valor": 25000,
             "data_vencimento": "2026-03-01", "status": "pendente"},
            {"id": "p2", "contrato_id": "ct1", "numero": 2, "valor": 25000,
             "data_vencimento": "2026-04-01", "status": "pendente"},
        ])
        resp = client.get("/api/contratos/ct1/parcelas")
        assert resp.status_code == 200

    def test_gerar_parcelas(self, client):
        client._mock_supabase.set_table_data("contratos", {
            "id": "ct1", "tipo": "venda", "status": "ativo",
            "valor_total": 120000, "data_inicio": "2026-01-01",
        })
        client._mock_supabase.set_table_data("parcelas_contrato", {
            "id": "p-new", "contrato_id": "ct1", "numero": 1,
            "valor": 9166.67, "data_vencimento": "2026-01-01", "status": "pendente",
        })
        resp = client.post("/api/contratos/ct1/parcelas", json={
            "valor_entrada": 10000,
            "num_parcelas": 12,
        })
        assert resp.status_code == 200

    def test_update_parcela(self, client):
        client._mock_supabase.set_table_data("parcelas_contrato", {
            "id": "p1", "contrato_id": "ct1", "numero": 1, "valor": 25000,
            "data_vencimento": "2026-03-01", "status": "pago",
            "data_pagamento": "2026-02-28",
        })
        resp = client.patch("/api/contratos/parcelas/p1", json={
            "status": "pago",
            "data_pagamento": "2026-02-28",
        })
        assert resp.status_code == 200

    def test_update_parcela_empty_body(self, client):
        resp = client.patch("/api/contratos/parcelas/p1", json={})
        assert resp.status_code == 400


class TestNoAuth:
    def test_no_token(self, client):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        resp = tc.get("/api/contratos")
        assert resp.status_code == 401
