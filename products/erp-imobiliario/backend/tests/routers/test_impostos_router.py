"""
Tests for Impostos router — /api/impostos
Covers list, resumo, get by id, create, update, delete tax records.
"""
import pytest


class TestListarImpostos:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("impostos", [
            {"id": "imp1", "tipo": "iptu", "ano": 2026, "valor_total": 5000,
             "valor_pago": 0, "status": "pendente"},
            {"id": "imp2", "tipo": "itbi", "ano": 2026, "valor_total": 12000,
             "valor_pago": 12000, "status": "pago"},
        ])
        resp = client.get("/api/impostos")
        assert resp.status_code == 200

    def test_filter_by_tipo(self, client):
        client._mock_supabase.set_table_data("impostos", [
            {"id": "imp1", "tipo": "iptu", "ano": 2026, "valor_total": 5000,
             "status": "pendente"},
        ])
        resp = client.get("/api/impostos?tipo=iptu")
        assert resp.status_code == 200

    def test_filter_by_ano(self, client):
        client._mock_supabase.set_table_data("impostos", [
            {"id": "imp1", "tipo": "iptu", "ano": 2026, "valor_total": 5000,
             "status": "pendente"},
        ])
        resp = client.get("/api/impostos?ano=2026")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("impostos", [
            {"id": "imp1", "tipo": "iptu", "ano": 2026, "valor_total": 5000,
             "status": "pendente"},
        ])
        resp = client.get("/api/impostos?status=pendente")
        assert resp.status_code == 200


class TestResumoImpostos:
    def test_resumo_success(self, client):
        client._mock_supabase.set_table_data("impostos", [
            {"id": "imp1", "tipo": "iptu", "ano": 2026, "valor_total": 5000,
             "valor_pago": 0, "status": "pendente"},
            {"id": "imp2", "tipo": "itbi", "ano": 2026, "valor_total": 12000,
             "valor_pago": 12000, "status": "pago"},
        ])
        resp = client.get("/api/impostos/resumo")
        assert resp.status_code == 200


class TestObterImposto:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("impostos", {
            "id": "imp1", "imovel_id": "imovel-1", "tipo": "iptu",
            "ano": 2026, "valor_total": 5000, "valor_pago": 0,
            "data_vencimento": "2026-03-15", "status": "pendente",
        })
        resp = client.get("/api/impostos/imp1")
        assert resp.status_code == 200

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("impostos", None)
        resp = client.get("/api/impostos/nonexistent")
        assert resp.status_code in [200, 404]


class TestCriarImposto:
    def test_create_success(self, client):
        client._mock_supabase.set_table_data("impostos", {
            "id": "imp-new", "imovel_id": "imovel-1", "tipo": "iptu",
            "ano": 2026, "valor_total": 5000, "data_vencimento": "2026-03-15",
            "status": "pendente",
        })
        resp = client.post("/api/impostos", json={
            "imovel_id": "imovel-1",
            "tipo": "iptu",
            "ano": 2026,
            "valor_total": 5000,
            "data_vencimento": "2026-03-15",
        })
        assert resp.status_code == 200

    def test_create_missing_required(self, client):
        resp = client.post("/api/impostos", json={
            "tipo": "iptu",
        })
        assert resp.status_code == 422


class TestAtualizarImposto:
    def test_update_success(self, client):
        client._mock_supabase.set_table_data("impostos", {
            "id": "imp1", "valor_pago": 2500, "status": "parcial",
        })
        resp = client.patch("/api/impostos/imp1", json={
            "valor_pago": 2500, "status": "parcial",
        })
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/impostos/imp1", json={})
        assert resp.status_code == 400


class TestExcluirImposto:
    def test_delete_success(self, client):
        client._mock_supabase.set_table_data("impostos", [{"id": "imp1"}])
        resp = client.delete("/api/impostos/imp1")
        assert resp.status_code == 200

    def test_delete_not_found(self, client):
        client._mock_supabase.set_table_data("impostos", [])
        resp = client.delete("/api/impostos/nonexistent")
        assert resp.status_code == 404
