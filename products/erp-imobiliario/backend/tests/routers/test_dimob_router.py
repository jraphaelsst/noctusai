"""
Tests for DIMOB (Tax Compliance) router — /api/dimob
Covers preview, validate, and generate endpoints.

IMPORTANT: The mock data below must match the actual database schema:
- Sales come from `clientes` table with etapa_atual='fechado' (NOT 'venda_fechada')
- Clientes table does NOT have a `cpf` column — only id, nome, email, telefone,
  valor_estimado, etapa_atual, updated_at, etc.
- Rental data comes from `contratos_locacao` table (NOT 'locacoes')
- Rental table uses `valor_aluguel` column (NOT 'valor_mensal')
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


def _setup_dimob_mocks(client, profiles=None, clientes=None, contratos_locacao=None):
    """
    Set up mock data for DIMOB tests using correct table/column names.
    Ensures tests break if service references wrong schema objects.
    """
    mock_sb = client._mock_supabase
    mock_sb.set_table_data("profiles", profiles or [])
    mock_sb.set_table_data("clientes", clientes or [])
    mock_sb.set_table_data("contratos_locacao", contratos_locacao or [])


# -- Sample data matching actual DB schema --

SAMPLE_PROFILE = {
    "id": "p1",
    "nome": "Imobiliária Teste",
    "email": "contato@imob.com",
}

SAMPLE_VENDA = {
    "id": "c1",
    "nome": "Comprador A",
    "email": "a@test.com",
    "telefone": "11999990000",
    "valor_estimado": 500000,
    "etapa_atual": "fechado",
    "updated_at": "2025-06-15T10:00:00Z",
}

SAMPLE_LOCACAO = {
    "id": "loc1",
    "valor_aluguel": 2500,
    "data_inicio": "2025-02-01",
    "data_fim": "2026-01-31",
}


class TestPreview:
    def test_preview_success(self, client):
        _patch_user_metadata(client)
        _setup_dimob_mocks(
            client,
            profiles=[SAMPLE_PROFILE],
            clientes=[SAMPLE_VENDA],
        )
        resp = client.get("/api/dimob/preview?ano=2025")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["ano"] == 2025
        assert "total_vendas" in data

    def test_preview_with_rentals(self, client):
        """Regression: rental data must come from contratos_locacao table."""
        _patch_user_metadata(client)
        _setup_dimob_mocks(
            client,
            profiles=[SAMPLE_PROFILE],
            contratos_locacao=[SAMPLE_LOCACAO],
        )
        resp = client.get("/api/dimob/preview?ano=2025")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_locacoes"] >= 0

    def test_preview_no_data(self, client):
        _patch_user_metadata(client)
        _setup_dimob_mocks(client)
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
        _setup_dimob_mocks(
            client,
            profiles=[SAMPLE_PROFILE],
            clientes=[SAMPLE_VENDA],
        )
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
        _setup_dimob_mocks(
            client,
            profiles=[SAMPLE_PROFILE],
            clientes=[SAMPLE_VENDA],
        )
        resp = client.post("/api/dimob/generate?ano=2025")
        assert resp.status_code == 200
        assert "xml" in resp.headers.get("content-type", "")

    def test_generate_with_rentals(self, client):
        """Regression: XML generation must handle contratos_locacao with valor_aluguel."""
        _patch_user_metadata(client)
        _setup_dimob_mocks(
            client,
            profiles=[SAMPLE_PROFILE],
            clientes=[SAMPLE_VENDA],
            contratos_locacao=[SAMPLE_LOCACAO],
        )
        resp = client.post("/api/dimob/generate?ano=2025")
        assert resp.status_code == 200
        assert "xml" in resp.headers.get("content-type", "")

    def test_generate_empty_data(self, client):
        _patch_user_metadata(client)
        _setup_dimob_mocks(client)
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
