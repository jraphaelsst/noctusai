"""
Tests for the Filiais (Multi-branch Management) router.
Covers list, create, get, update, deactivate, and consolidated report endpoints.
"""
import pytest


class TestListarFiliais:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("filiais", [
            {"id": "f1", "nome": "Filial Centro", "codigo": "FC01", "is_active": True},
            {"id": "f2", "nome": "Filial Norte", "codigo": "FN01", "is_active": True},
        ])
        resp = client.get("/api/filiais")
        assert resp.status_code == 200

    def test_list_empty(self, client):
        client._mock_supabase.set_table_data("filiais", [])
        resp = client.get("/api/filiais")
        assert resp.status_code == 200

    def test_list_filter_active(self, client):
        client._mock_supabase.set_table_data("filiais", [
            {"id": "f1", "nome": "Filial Centro", "codigo": "FC01", "is_active": True},
        ])
        resp = client.get("/api/filiais?is_active=true")
        assert resp.status_code == 200

    def test_list_filter_inactive(self, client):
        client._mock_supabase.set_table_data("filiais", [])
        resp = client.get("/api/filiais?is_active=false")
        assert resp.status_code == 200

    def test_list_pagination(self, client):
        client._mock_supabase.set_table_data("filiais", [])
        resp = client.get("/api/filiais?page=2&page_size=10")
        assert resp.status_code == 200


class TestCriarFilial:
    def test_create_success(self, client):
        client._mock_supabase.set_table_data("filiais", {
            "id": "f-new",
            "nome": "Nova Filial",
            "codigo": "NF01",
            "is_active": True,
        })
        resp = client.post("/api/filiais", json={
            "nome": "Nova Filial",
            "codigo": "NF01",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "f-new"

    def test_create_with_all_fields(self, client):
        client._mock_supabase.set_table_data("filiais", {
            "id": "f-full",
            "nome": "Filial Completa",
            "codigo": "FX01",
            "endereco": "Rua das Flores, 123",
            "cidade": "Sao Paulo",
            "estado": "SP",
            "telefone": "11999999999",
            "responsavel_id": "user-123",
            "is_active": True,
        })
        resp = client.post("/api/filiais", json={
            "nome": "Filial Completa",
            "codigo": "FX01",
            "endereco": "Rua das Flores, 123",
            "cidade": "Sao Paulo",
            "estado": "SP",
            "telefone": "11999999999",
            "responsavel_id": "user-123",
        })
        assert resp.status_code == 200

    def test_create_missing_nome(self, client):
        resp = client.post("/api/filiais", json={
            "codigo": "NF01",
        })
        assert resp.status_code == 422

    def test_create_missing_codigo(self, client):
        resp = client.post("/api/filiais", json={
            "nome": "Nova Filial",
        })
        assert resp.status_code == 422

    def test_create_empty_nome(self, client):
        resp = client.post("/api/filiais", json={
            "nome": "",
            "codigo": "NF01",
        })
        assert resp.status_code == 422

    def test_create_empty_codigo(self, client):
        resp = client.post("/api/filiais", json={
            "nome": "Nova Filial",
            "codigo": "",
        })
        assert resp.status_code == 422


class TestObterFilial:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("filiais", {
            "id": "f1",
            "nome": "Filial Centro",
            "codigo": "FC01",
            "is_active": True,
        })
        client._mock_supabase.set_table_data("ativos", [])
        client._mock_supabase.set_table_data("clientes", [])
        resp = client.get("/api/filiais/f1")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "f1"

    def test_get_not_found(self, client):
        client._mock_supabase.set_table_data("filiais", None)
        resp = client.get("/api/filiais/nonexistent")
        assert resp.status_code == 404


class TestAtualizarFilial:
    def test_update_nome(self, client):
        client._mock_supabase.set_table_data("filiais", {
            "id": "f1",
            "nome": "Nome Atualizado",
            "codigo": "FC01",
        })
        resp = client.patch("/api/filiais/f1", json={
            "nome": "Nome Atualizado",
        })
        assert resp.status_code == 200

    def test_update_multiple_fields(self, client):
        client._mock_supabase.set_table_data("filiais", {
            "id": "f1",
            "nome": "Updated",
            "cidade": "Rio de Janeiro",
            "estado": "RJ",
        })
        resp = client.patch("/api/filiais/f1", json={
            "nome": "Updated",
            "cidade": "Rio de Janeiro",
            "estado": "RJ",
        })
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/filiais/f1", json={})
        assert resp.status_code == 400

    def test_update_not_found(self, client):
        client._mock_supabase.set_table_data("filiais", None)
        resp = client.patch("/api/filiais/nonexistent", json={
            "nome": "Updated",
        })
        assert resp.status_code == 404

    def test_update_toggle_active(self, client):
        client._mock_supabase.set_table_data("filiais", {
            "id": "f1",
            "is_active": False,
        })
        resp = client.patch("/api/filiais/f1", json={
            "is_active": False,
        })
        assert resp.status_code == 200


class TestDesativarFilial:
    def test_deactivate_success(self, client):
        client._mock_supabase.set_table_data("filiais", {
            "id": "f1",
            "is_active": False,
        })
        resp = client.delete("/api/filiais/f1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_deactivate_not_found(self, client):
        client._mock_supabase.set_table_data("filiais", None)
        resp = client.delete("/api/filiais/nonexistent")
        assert resp.status_code == 404


class TestConsolidadoFiliais:
    def test_consolidado_success(self, client):
        client._mock_supabase.set_table_data("filiais", [
            {"id": "f1", "nome": "Filial Centro", "is_active": True},
            {"id": "f2", "nome": "Filial Norte", "is_active": True},
        ])
        client._mock_supabase.set_table_data("ativos", [])
        client._mock_supabase.set_table_data("clientes", [])
        resp = client.get("/api/filiais/consolidado")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "filiais" in data
        assert "totais" in data
        assert data["totais"]["filiais"] == 2

    def test_consolidado_empty(self, client):
        client._mock_supabase.set_table_data("filiais", [])
        resp = client.get("/api/filiais/consolidado")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["totais"]["filiais"] == 0
        assert data["totais"]["imoveis"] == 0
        assert data["totais"]["clientes"] == 0
