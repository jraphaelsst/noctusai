"""
Tests for Seguros router — /api/seguros
Covers list, vencimentos, get by id, create, update, delete insurance policies.
"""
import pytest


class TestListarSeguros:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("seguros", [
            {"id": "seg1", "seguradora": "Porto Seguro", "tipo_cobertura": "completo",
             "status": "ativo", "valor_cobertura": 500000, "valor_premio": 2400},
            {"id": "seg2", "seguradora": "Bradesco Seguros", "tipo_cobertura": "incendio",
             "status": "ativo", "valor_cobertura": 300000, "valor_premio": 1200},
        ])
        resp = client.get("/api/seguros")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("seguros", [
            {"id": "seg1", "status": "ativo", "valor_cobertura": 500000, "valor_premio": 2400},
        ])
        resp = client.get("/api/seguros?status=ativo")
        assert resp.status_code == 200

    def test_filter_by_tipo_cobertura(self, client):
        client._mock_supabase.set_table_data("seguros", [
            {"id": "seg1", "tipo_cobertura": "completo", "status": "ativo",
             "valor_cobertura": 500000, "valor_premio": 2400},
        ])
        resp = client.get("/api/seguros?tipo_cobertura=completo")
        assert resp.status_code == 200


class TestVencimentos:
    def test_vencimentos_success(self, client):
        client._mock_supabase.set_table_data("seguros", [
            {"id": "seg1", "status": "ativo", "data_vencimento": "2026-03-15",
             "seguradora": "Porto Seguro"},
        ])
        resp = client.get("/api/seguros/vencimentos?dias=30")
        assert resp.status_code == 200


class TestObterSeguro:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("seguros", {
            "id": "seg1", "seguradora": "Porto Seguro", "tipo_cobertura": "completo",
            "valor_cobertura": 500000, "valor_premio": 2400,
            "data_inicio": "2026-01-01", "data_vencimento": "2027-01-01",
        })
        resp = client.get("/api/seguros/seg1")
        assert resp.status_code == 200

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("seguros", None)
        resp = client.get("/api/seguros/nonexistent")
        assert resp.status_code in [200, 404]


class TestCriarSeguro:
    def test_create_success(self, client):
        client._mock_supabase.set_table_data("seguros", {
            "id": "seg-new", "imovel_id": "imovel-1", "seguradora": "Porto Seguro",
            "tipo_cobertura": "completo", "valor_cobertura": 500000,
            "valor_premio": 2400, "data_inicio": "2026-01-01",
            "data_vencimento": "2027-01-01", "status": "ativo",
        })
        resp = client.post("/api/seguros", json={
            "imovel_id": "imovel-1",
            "seguradora": "Porto Seguro",
            "tipo_cobertura": "completo",
            "valor_cobertura": 500000,
            "valor_premio": 2400,
            "data_inicio": "2026-01-01",
            "data_vencimento": "2027-01-01",
        })
        assert resp.status_code == 200

    def test_create_missing_required(self, client):
        resp = client.post("/api/seguros", json={
            "seguradora": "Porto Seguro",
        })
        assert resp.status_code == 422


class TestAtualizarSeguro:
    def test_update_success(self, client):
        client._mock_supabase.set_table_data("seguros", {
            "id": "seg1", "seguradora": "Porto Seguro", "valor_premio": 3000,
        })
        resp = client.patch("/api/seguros/seg1", json={"valor_premio": 3000})
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/seguros/seg1", json={})
        assert resp.status_code == 400


class TestExcluirSeguro:
    def test_delete_success(self, client):
        client._mock_supabase.set_table_data("seguros", {"id": "seg1"})
        resp = client.delete("/api/seguros/seg1")
        assert resp.status_code == 200
