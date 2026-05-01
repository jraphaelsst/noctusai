"""
Tests for the Comissoes CRUD router.
Covers list, create, read, update status, delete, resumo, and splits.
"""
import pytest

from tests.conftest import MockSupabaseResponse


class TestListarComissoes:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("comissoes", [
            {"id": "cm1", "valor_venda": 500000, "percentual_comissao": 6.0,
             "valor_comissao": 30000, "status": "pendente"},
            {"id": "cm2", "valor_venda": 300000, "percentual_comissao": 5.0,
             "valor_comissao": 15000, "status": "paga"},
        ])
        client._mock_supabase.set_table_data("comissoes_splits", [])
        resp = client.get("/api/comissoes")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("comissoes", [
            {"id": "cm1", "valor_venda": 500000, "percentual_comissao": 6.0,
             "valor_comissao": 30000, "status": "pendente"},
        ])
        client._mock_supabase.set_table_data("comissoes_splits", [])
        resp = client.get("/api/comissoes?status=pendente")
        assert resp.status_code == 200


class TestResumoComissoes:
    def test_resumo_success(self, client):
        client._mock_supabase.set_table_data("comissoes", [
            {"id": "cm1", "valor_comissao": 30000, "status": "pendente"},
            {"id": "cm2", "valor_comissao": 15000, "status": "paga"},
            {"id": "cm3", "valor_comissao": 20000, "status": "aprovada"},
        ])
        client._mock_supabase.set_table_data("comissoes_splits", [])
        resp = client.get("/api/comissoes/resumo")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "totais" in data
        assert "por_corretor" in data
        totais = data["totais"]
        assert "total_pendente" in totais
        assert "total_paga" in totais
        assert "total_geral" in totais
        assert "quantidade" in totais

    def test_resumo_empty(self, client):
        client._mock_supabase.set_table_data("comissoes", [])
        client._mock_supabase.set_table_data("comissoes_splits", [])
        resp = client.get("/api/comissoes/resumo")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["totais"]["quantidade"] == 0
        assert data["totais"]["total_geral"] == 0


class TestObterComissao:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("comissoes", {
            "id": "cm1", "valor_venda": 500000, "percentual_comissao": 6.0,
            "valor_comissao": 30000, "status": "pendente",
        })
        client._mock_supabase.set_table_data("comissoes_splits", [])
        resp = client.get("/api/comissoes/cm1")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "cm1"

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("comissoes", None)
        client._mock_supabase.set_table_data("comissoes_splits", [])
        resp = client.get("/api/comissoes/nonexistent")
        assert resp.status_code in [200, 404]


class TestCriarComissao:
    def test_create_success(self, client):
        client._mock_supabase.set_sequential_responses("comissoes", [
            MockSupabaseResponse(data=[{
                "id": "new-cm", "valor_venda": 400000, "percentual_comissao": 6.0,
                "valor_comissao": 24000, "status": "pendente",
            }]),
        ])
        client._mock_supabase.set_table_data("comissoes_splits", [])
        resp = client.post("/api/comissoes", json={
            "valor_venda": 400000,
            "percentual_comissao": 6.0,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "new-cm"

    def test_create_with_optional_fields(self, client):
        client._mock_supabase.set_table_data("comissoes", {
            "id": "new-cm2", "valor_venda": 350000, "percentual_comissao": 5.5,
            "valor_comissao": 19250, "status": "pendente",
            "venda_id": "v1", "imovel_id": "i1",
            "data_venda": "2026-02-20", "observacoes": "Comissao padrao",
        })
        client._mock_supabase.set_table_data("comissoes_splits", [])
        resp = client.post("/api/comissoes", json={
            "valor_venda": 350000,
            "percentual_comissao": 5.5,
            "venda_id": "v1",
            "imovel_id": "i1",
            "data_venda": "2026-02-20",
            "observacoes": "Comissao padrao",
        })
        assert resp.status_code == 200

    def test_create_missing_required(self, client):
        resp = client.post("/api/comissoes", json={
            "percentual_comissao": 6.0,
        })
        assert resp.status_code == 422

    def test_create_invalid_valor(self, client):
        resp = client.post("/api/comissoes", json={
            "valor_venda": -100,
            "percentual_comissao": 6.0,
        })
        assert resp.status_code == 422

    def test_create_with_splits(self, client):
        client._mock_supabase.set_table_data("comissoes", {
            "id": "new-cm3", "valor_venda": 500000, "percentual_comissao": 6.0,
            "valor_comissao": 30000, "status": "pendente",
        })
        client._mock_supabase.set_table_data("comissoes_splits", [
            {"id": "s1", "comissao_id": "new-cm3", "corretor_id": "u1",
             "corretor_nome": "Corretor A", "percentual": 60, "valor": 18000},
            {"id": "s2", "comissao_id": "new-cm3", "corretor_id": "u2",
             "corretor_nome": "Corretor B", "percentual": 40, "valor": 12000},
        ])
        resp = client.post("/api/comissoes", json={
            "valor_venda": 500000,
            "percentual_comissao": 6.0,
            "splits": [
                {"corretor_id": "u1", "corretor_nome": "Corretor A", "percentual": 60},
                {"corretor_id": "u2", "corretor_nome": "Corretor B", "percentual": 40},
            ],
        })
        assert resp.status_code == 200


class TestAtualizarComissao:
    def test_update_status_success(self, client):
        client._mock_supabase.set_table_data("comissoes", {
            "id": "cm1", "valor_venda": 500000, "percentual_comissao": 6.0,
            "valor_comissao": 30000, "status": "aprovada",
        })
        resp = client.patch("/api/comissoes/cm1", json={
            "status": "aprovada",
        })
        assert resp.status_code == 200

    def test_update_with_pagamento(self, client):
        client._mock_supabase.set_table_data("comissoes", {
            "id": "cm1", "valor_venda": 500000, "percentual_comissao": 6.0,
            "valor_comissao": 30000, "status": "paga",
            "data_pagamento": "2026-02-24",
        })
        resp = client.patch("/api/comissoes/cm1", json={
            "status": "paga",
            "data_pagamento": "2026-02-24",
        })
        assert resp.status_code == 200

    def test_update_missing_status(self, client):
        resp = client.patch("/api/comissoes/cm1", json={})
        assert resp.status_code == 422

    def test_update_invalid_status(self, client):
        resp = client.patch("/api/comissoes/cm1", json={
            "status": "invalido",
        })
        assert resp.status_code == 422


class TestExcluirComissao:
    def test_delete_success(self, client):
        client._mock_supabase.set_table_data("comissoes", {"id": "cm1"})
        resp = client.delete("/api/comissoes/cm1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_not_found(self, client):
        client._mock_supabase.set_table_data("comissoes", None)
        resp = client.delete("/api/comissoes/nonexistent")
        assert resp.status_code == 404


class TestNoAuth:
    def test_no_token(self, client):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        resp = tc.get("/api/comissoes")
        assert resp.status_code == 401
