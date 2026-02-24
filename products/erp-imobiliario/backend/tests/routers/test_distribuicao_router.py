"""
Tests for Distribuicao (Lead Distribution) router — /api/distribuicao
Covers config get/update, manual/auto lead assignment, and queue info.
"""
import pytest


class TestObterConfig:
    def test_get_config_exists(self, client):
        client._mock_supabase.set_table_data("distribuicao_config", [
            {"id": "cfg-1", "modo": "round_robin",
             "corretores_ativos": ["u1", "u2"], "proximo_corretor_idx": 0,
             "regras": {}},
        ])
        resp = client.get("/api/distribuicao/config")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["modo"] == "round_robin"

    def test_get_config_default_when_empty(self, client):
        client._mock_supabase.set_table_data("distribuicao_config", [])
        resp = client.get("/api/distribuicao/config")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["modo"] == "manual"
        assert data["corretores_ativos"] == []


class TestAtualizarConfig:
    def test_update_modo(self, client):
        client._mock_supabase.set_table_data("distribuicao_config", [{
            "id": "cfg-1", "modo": "round_robin",
        }])
        resp = client.patch("/api/distribuicao/config", json={
            "modo": "round_robin",
        })
        assert resp.status_code == 200

    def test_update_corretores_ativos(self, client):
        client._mock_supabase.set_table_data("distribuicao_config", [{
            "id": "cfg-1", "modo": "round_robin",
            "corretores_ativos": ["u1", "u2", "u3"],
        }])
        resp = client.patch("/api/distribuicao/config", json={
            "corretores_ativos": ["u1", "u2", "u3"],
        })
        assert resp.status_code == 200

    def test_update_regras(self, client):
        client._mock_supabase.set_table_data("distribuicao_config", [{
            "id": "cfg-1", "modo": "por_regiao",
            "regras": {"regioes": {"zona_sul": "u1"}},
        }])
        resp = client.patch("/api/distribuicao/config", json={
            "regras": {"regioes": {"zona_sul": "u1"}},
        })
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/distribuicao/config", json={})
        assert resp.status_code == 400

    def test_update_invalid_modo(self, client):
        resp = client.patch("/api/distribuicao/config", json={
            "modo": "invalido",
        })
        assert resp.status_code == 422


class TestAtribuirLead:
    def test_atribuir_manual(self, client):
        client._mock_supabase.set_table_data("clientes", {
            "id": "c1", "nome": "João", "usuario_id": "u1",
        })
        resp = client.post("/api/distribuicao/atribuir", json={
            "cliente_id": "c1",
            "corretor_id": "u1",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["atribuido"] is True
        assert data["modo"] == "manual"

    def test_atribuir_auto(self, client):
        client._mock_supabase.set_table_data("distribuicao_config", [
            {"id": "cfg-1", "org_id": "test-user-123", "modo": "round_robin",
             "corretores_ativos": ["u1", "u2"], "proximo_corretor_idx": 0},
        ])
        client._mock_supabase.set_table_data("clientes", {
            "id": "c1", "nome": "Lead Novo",
        })
        resp = client.post("/api/distribuicao/atribuir", json={
            "cliente_id": "c1",
        })
        assert resp.status_code == 200

    def test_atribuir_missing_cliente_id(self, client):
        resp = client.post("/api/distribuicao/atribuir", json={})
        assert resp.status_code == 422


class TestObterFila:
    def test_fila_with_config(self, client):
        client._mock_supabase.set_table_data("distribuicao_config", [
            {"id": "cfg-1", "modo": "round_robin",
             "corretores_ativos": ["u1", "u2"], "proximo_corretor_idx": 0,
             "regras": {}},
        ])
        client._mock_supabase.set_table_data("profiles", [
            {"id": "u1", "nome": "Corretor A", "email": "a@test.com"},
            {"id": "u2", "nome": "Corretor B", "email": "b@test.com"},
        ])
        resp = client.get("/api/distribuicao/fila")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["modo"] == "round_robin"
        assert "proximo_corretor_id" in data

    def test_fila_default_when_no_config(self, client):
        client._mock_supabase.set_table_data("distribuicao_config", [])
        resp = client.get("/api/distribuicao/fila")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["modo"] == "manual"
        assert data["proximo_corretor_id"] is None
