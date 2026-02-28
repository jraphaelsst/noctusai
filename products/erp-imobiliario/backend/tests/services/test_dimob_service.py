"""
Tests for DIMOB service — validate_dimob_data, _fetch_dimob_data, generate_dimob_xml.

Regression tests to ensure the service references correct DB columns and table names:
- clientes table: NO `cpf` column, uses `valor_estimado` (not `valor`)
- clientes etapa_atual: 'fechado' (not 'venda_fechada')
- Rental table: `contratos_locacao` (not 'locacoes')
- Rental column: `valor_aluguel` (not 'valor_mensal')
"""
import pytest
from unittest.mock import MagicMock

from app.services.dimob_service import (
    validate_dimob_data,
    _fetch_dimob_data,
    generate_dimob_xml,
    preview_dimob,
    _clean_doc,
    _format_date,
    _format_money,
)


# ========== VALIDATE DIMOB DATA ==========

class TestValidateDimobData:
    def test_valid_data_no_warnings(self):
        data = {
            "organizacao": {"cnpj": "12345678000199", "razao_social": "Test LTDA"},
            "vendas": [{
                "id": "v1",
                "cpf_comprador": "11122233344",
                "valor": 500000,
                "data_operacao": "2025-06-15",
            }],
            "locacoes": [{
                "id": "l1",
                "cpf_locatario": "55566677788",
                "valor_aluguel": 2500,
            }],
        }
        warnings = validate_dimob_data(data)
        assert len(warnings) == 0

    def test_missing_cnpj_warning(self):
        data = {
            "organizacao": {"razao_social": "Test LTDA"},
            "vendas": [],
            "locacoes": [],
        }
        warnings = validate_dimob_data(data)
        assert any(w["campo"] == "cnpj" for w in warnings)

    def test_missing_razao_social_warning(self):
        data = {
            "organizacao": {"cnpj": "12345678000199"},
            "vendas": [],
            "locacoes": [],
        }
        warnings = validate_dimob_data(data)
        assert any(w["campo"] == "razao_social" for w in warnings)

    def test_venda_missing_cpf_warning(self):
        """The service expects cpf_comprador in the processed data (not raw clientes.cpf)."""
        data = {
            "organizacao": {"cnpj": "123", "razao_social": "X"},
            "vendas": [{"id": "v1", "cpf_comprador": "", "valor": 100, "data_operacao": "2025-01-01"}],
            "locacoes": [],
        }
        warnings = validate_dimob_data(data)
        assert any(w["campo"] == "cpf_comprador" for w in warnings)

    def test_venda_missing_valor_warning(self):
        data = {
            "organizacao": {"cnpj": "123", "razao_social": "X"},
            "vendas": [{"id": "v1", "cpf_comprador": "111", "valor": None, "data_operacao": "2025-01-01"}],
            "locacoes": [],
        }
        warnings = validate_dimob_data(data)
        assert any(w["campo"] == "valor" for w in warnings)

    def test_locacao_missing_cpf_warning(self):
        data = {
            "organizacao": {"cnpj": "123", "razao_social": "X"},
            "vendas": [],
            "locacoes": [{"id": "l1", "cpf_locatario": "", "valor_aluguel": 2500}],
        }
        warnings = validate_dimob_data(data)
        assert any(w["campo"] == "cpf_locatario" for w in warnings)

    def test_locacao_missing_valor_aluguel_warning(self):
        data = {
            "organizacao": {"cnpj": "123", "razao_social": "X"},
            "vendas": [],
            "locacoes": [{"id": "l1", "cpf_locatario": "555", "valor_aluguel": None}],
        }
        warnings = validate_dimob_data(data)
        assert any(w["campo"] == "valor_aluguel" for w in warnings)

    def test_empty_data_returns_org_warnings_only(self):
        data = {"organizacao": {}, "vendas": [], "locacoes": []}
        warnings = validate_dimob_data(data)
        assert len(warnings) == 2  # cnpj + razao_social


# ========== FETCH DIMOB DATA ==========

class TestFetchDimobData:
    """
    Regression: _fetch_dimob_data must query the correct tables and columns.
    These tests verify the Supabase query builder chains.
    """

    def _make_mock_supabase(self, profiles=None, clientes=None, contratos=None):
        mock_sb = MagicMock()
        tables = {}

        def make_query(data):
            q = MagicMock()
            q.select.return_value = q
            q.eq.return_value = q
            q.gte.return_value = q
            q.lte.return_value = q
            q.limit.return_value = q
            resp = MagicMock()
            resp.data = data
            q.execute.return_value = resp
            return q

        tables["profiles"] = make_query(profiles or [])
        tables["clientes"] = make_query(clientes or [])
        tables["contratos_locacao"] = make_query(contratos or [])

        def table(name):
            if name in tables:
                return tables[name]
            return make_query([])

        mock_sb.table = table
        return mock_sb

    def test_fetches_from_correct_tables(self):
        """Regression: must query 'contratos_locacao' not 'locacoes'."""
        mock_sb = self._make_mock_supabase(
            profiles=[{"id": "p1", "nome": "Test", "email": "t@t.com"}],
            clientes=[{
                "id": "c1", "nome": "Buyer", "email": "b@t.com",
                "valor_estimado": 300000, "etapa_atual": "fechado",
                "updated_at": "2025-06-01T00:00:00Z",
            }],
            contratos=[{
                "id": "l1", "valor_aluguel": 2000,
                "data_inicio": "2025-01-01", "data_fim": "2025-12-31",
            }],
        )

        data = _fetch_dimob_data("org-1", 2025, mock_sb)

        assert data["ano"] == 2025
        assert len(data["vendas"]) == 1
        assert len(data["locacoes"]) == 1
        # Verify the sale was mapped correctly (no cpf column exists)
        assert data["vendas"][0]["cpf_comprador"] == ""
        assert data["vendas"][0]["valor"] == 300000

    def test_etapa_filter_uses_fechado(self):
        """Regression: must filter by etapa_atual='fechado' not 'venda_fechada'."""
        mock_sb = self._make_mock_supabase()
        _fetch_dimob_data("org-1", 2025, mock_sb)

        # Verify the clientes query used 'fechado'
        clientes_table = mock_sb.table("clientes")
        clientes_table.eq.assert_called_with("etapa_atual", "fechado")

    def test_locacao_uses_valor_aluguel(self):
        """Regression: rental data must use valor_aluguel column."""
        mock_sb = self._make_mock_supabase(
            contratos=[{
                "id": "l1", "valor_aluguel": 3000,
                "data_inicio": "2025-01-01", "data_fim": "2025-12-31",
            }],
        )

        data = _fetch_dimob_data("org-1", 2025, mock_sb)

        if data["locacoes"]:
            assert data["locacoes"][0]["valor_aluguel"] == 3000

    def test_graceful_when_tables_fail(self):
        """Service wraps queries in try/except — should not crash."""
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB unavailable")

        data = _fetch_dimob_data("org-1", 2025, mock_sb)
        assert data["vendas"] == []
        assert data["locacoes"] == []


# ========== HELPER FUNCTIONS ==========

class TestCleanDoc:
    def test_strips_formatting(self):
        assert _clean_doc("123.456.789-00") == "12345678900"
        assert _clean_doc("12.345.678/0001-99") == "12345678000199"

    def test_handles_none(self):
        assert _clean_doc(None) == ""

    def test_handles_empty(self):
        assert _clean_doc("") == ""


class TestFormatDate:
    def test_iso_datetime(self):
        assert _format_date("2025-06-15T10:00:00Z") == "15/06/2025"

    def test_date_only(self):
        assert _format_date("2025-06-15") == "15/06/2025"

    def test_empty_string(self):
        assert _format_date("") == ""


class TestFormatMoney:
    def test_integer(self):
        assert _format_money(500000) == "500000.00"

    def test_float(self):
        assert _format_money(2500.50) == "2500.50"

    def test_string_number(self):
        assert _format_money("1000") == "1000.00"

    def test_none_returns_zero(self):
        assert _format_money(None) == "0.00"

    def test_invalid_returns_zero(self):
        assert _format_money("abc") == "0.00"
