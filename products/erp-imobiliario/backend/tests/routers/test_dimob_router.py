"""
Tests for DIMOB (Tax Compliance) router — /api/dimob
Covers preview, validate, and generate endpoints.
"""
import pytest
from unittest.mock import MagicMock, PropertyMock


def _patch_user_metadata(client):
    """
    Add user_metadata to the mock user so the DIMOB router can
    access user.user_metadata.get("org_id").
    """
    mock_user = client._mock_supabase.auth.get_user.return_value.user
    mock_user.user_metadata = {"org_id": "org-test-123"}


class TestPreview:
    def test_preview_success(self, client):
        _patch_user_metadata(client)
        client._mock_supabase.set_table_data("profiles", [
            {"id": "p1", "nome": "Imobiliária Teste", "email": "contato@imob.com",
             "cnpj": "12345678000199", "razao_social": "Imobiliária Teste LTDA"},
        ])
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "Comprador A", "cpf": "11122233344",
             "valor_estimado": 500000, "etapa_atual": "venda_fechada",
             "updated_at": "2025-06-15T10:00:00Z", "email": "a@test.com"},
        ])
        client._mock_supabase.set_table_data("locacoes", [])
        resp = client.get("/api/dimob/preview?ano=2025")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["ano"] == 2025
        assert "total_vendas" in data

    def test_preview_no_data(self, client):
        _patch_user_metadata(client)
        client._mock_supabase.set_table_data("profiles", [])
        client._mock_supabase.set_table_data("clientes", [])
        client._mock_supabase.set_table_data("locacoes", [])
        resp = client.get("/api/dimob/preview?ano=2025")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_vendas"] == 0

    def test_preview_missing_ano(self, client):
        _patch_user_metadata(client)
        resp = client.get("/api/dimob/preview")
        assert resp.status_code == 422

    def test_preview_invalid_ano(self, client):
        _patch_user_metadata(client)
        resp = client.get("/api/dimob/preview?ano=1999")
        assert resp.status_code == 422


class TestValidate:
    def test_validate_success(self, client):
        _patch_user_metadata(client)
        client._mock_supabase.set_table_data("profiles", [
            {"id": "p1", "nome": "Imobiliária", "email": "contato@imob.com",
             "cnpj": "12345678000199", "razao_social": "Imobiliária LTDA"},
        ])
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "Comprador A", "cpf": "11122233344",
             "valor_estimado": 500000, "etapa_atual": "venda_fechada",
             "updated_at": "2025-06-15T10:00:00Z", "email": "a@test.com"},
        ])
        client._mock_supabase.set_table_data("locacoes", [])
        resp = client.get("/api/dimob/validate?ano=2025")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["ano"] == 2025
        assert "valido" in data
        assert "avisos" in data

    def test_validate_missing_ano(self, client):
        _patch_user_metadata(client)
        resp = client.get("/api/dimob/validate")
        assert resp.status_code == 422


class TestGenerate:
    def test_generate_success(self, client):
        _patch_user_metadata(client)
        client._mock_supabase.set_table_data("profiles", [
            {"id": "p1", "nome": "Imobiliária Teste", "email": "contato@imob.com",
             "cnpj": "12345678000199", "razao_social": "Imobiliária Teste LTDA"},
        ])
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "Comprador A", "cpf": "11122233344",
             "valor_estimado": 500000, "etapa_atual": "venda_fechada",
             "updated_at": "2025-03-10T10:00:00Z", "email": "a@test.com"},
        ])
        client._mock_supabase.set_table_data("locacoes", [])
        resp = client.post("/api/dimob/generate?ano=2025")
        assert resp.status_code == 200
        assert "xml" in resp.headers.get("content-type", "")

    def test_generate_empty_data(self, client):
        _patch_user_metadata(client)
        client._mock_supabase.set_table_data("profiles", [])
        client._mock_supabase.set_table_data("clientes", [])
        client._mock_supabase.set_table_data("locacoes", [])
        resp = client.post("/api/dimob/generate?ano=2025")
        assert resp.status_code == 200

    def test_generate_missing_ano(self, client):
        _patch_user_metadata(client)
        resp = client.post("/api/dimob/generate")
        assert resp.status_code == 422

    def test_generate_invalid_ano(self, client):
        _patch_user_metadata(client)
        resp = client.post("/api/dimob/generate?ano=1999")
        assert resp.status_code == 422
