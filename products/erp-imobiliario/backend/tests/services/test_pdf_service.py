"""
Unit tests for PDF Service — document generation, formatting helpers, text fallback.
"""
import pytest
from unittest.mock import patch

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# _format_currency
# ---------------------------------------------------------------------------

class TestFormatCurrency:

    def test_basic_value(self):
        from app.services.pdf_service import _format_currency
        assert _format_currency(1500.00) == "R$ 1.500,00"

    def test_large_value(self):
        from app.services.pdf_service import _format_currency
        assert _format_currency(2500000.00) == "R$ 2.500.000,00"

    def test_zero(self):
        from app.services.pdf_service import _format_currency
        assert _format_currency(0) == "R$ 0,00"

    def test_cents(self):
        from app.services.pdf_service import _format_currency
        assert _format_currency(99.99) == "R$ 99,99"

    def test_with_decimal(self):
        from app.services.pdf_service import _format_currency
        assert _format_currency(1234.56) == "R$ 1.234,56"


# ---------------------------------------------------------------------------
# _format_date
# ---------------------------------------------------------------------------

class TestFormatDate:

    def test_iso_date(self):
        from app.services.pdf_service import _format_date
        assert _format_date("2026-03-15") == "15/03/2026"

    def test_iso_datetime(self):
        from app.services.pdf_service import _format_date
        assert _format_date("2026-03-15T10:30:00") == "15/03/2026"

    def test_iso_datetime_with_z(self):
        from app.services.pdf_service import _format_date
        assert _format_date("2026-03-15T10:30:00Z") == "15/03/2026"

    def test_none_returns_na(self):
        from app.services.pdf_service import _format_date
        assert _format_date(None) == "N/A"

    def test_empty_string_returns_na(self):
        from app.services.pdf_service import _format_date
        assert _format_date("") == "N/A"

    def test_malformed_date_returns_truncated(self):
        from app.services.pdf_service import _format_date
        # Fallback: returns first 10 chars
        assert _format_date("not-a-date-at-all") == "not-a-date"


# ---------------------------------------------------------------------------
# PDFService — text-based fallback
# ---------------------------------------------------------------------------

class TestPDFServiceTextFallback:
    """Tests the text-based fallback mode (no reportlab)."""

    def _make_service_without_reportlab(self):
        """Create a PDFService instance that thinks reportlab is unavailable."""
        from app.services.pdf_service import PDFService
        svc = PDFService()
        svc._has_reportlab = False
        return svc

    def test_gerar_contrato_returns_bytes(self):
        svc = self._make_service_without_reportlab()

        contrato = {
            "id": "cont-123-abcdef",
            "tipo": "venda",
            "status": "ativo",
            "valor_total": 500000.0,
            "data_inicio": "2026-01-01",
            "data_fim": "2027-01-01",
        }

        result = svc.gerar_contrato(contrato)

        assert isinstance(result, bytes)
        text = result.decode("utf-8")
        assert "CONTRATO DE VENDA" in text
        assert "R$ 500.000,00" in text
        assert "01/01/2026" in text
        assert "01/01/2027" in text

    def test_gerar_contrato_with_parcelas(self):
        svc = self._make_service_without_reportlab()

        contrato = {
            "tipo": "aluguel",
            "valor_total": 24000.0,
        }
        parcelas = [
            {"numero": 1, "valor": 2000.0, "data_vencimento": "2026-02-01", "status": "pago"},
            {"numero": 2, "valor": 2000.0, "data_vencimento": "2026-03-01", "status": "pendente"},
        ]

        result = svc.gerar_contrato(contrato, parcelas)
        text = result.decode("utf-8")

        assert "PARCELAS:" in text
        assert "#1" in text
        assert "#2" in text
        assert "R$ 2.000,00" in text

    def test_gerar_contrato_with_observacoes(self):
        svc = self._make_service_without_reportlab()

        contrato = {
            "tipo": "venda",
            "valor_total": 100000.0,
            "observacoes": "Incluir vaga de garagem.",
        }

        result = svc.gerar_contrato(contrato)
        text = result.decode("utf-8")
        assert "Incluir vaga de garagem." in text

    def test_gerar_contrato_without_parcelas(self):
        svc = self._make_service_without_reportlab()

        contrato = {"tipo": "venda", "valor_total": 100000.0}
        result = svc.gerar_contrato(contrato)
        text = result.decode("utf-8")

        assert "PARCELAS:" not in text
        assert "Assinatura do Contratante" in text
        assert "Assinatura do Contratado" in text

    def test_gerar_proposta_returns_bytes(self):
        svc = self._make_service_without_reportlab()

        proposta = {
            "id": "prop-456-abcdef",
            "status": "enviada",
            "valor_proposta": 750000.0,
            "created_at": "2026-03-01T10:00:00Z",
        }

        result = svc.gerar_proposta(proposta)

        assert isinstance(result, bytes)
        text = result.decode("utf-8")
        assert "PROPOSTA COMERCIAL" in text
        assert "R$ 750.000,00" in text
        assert "01/03/2026" in text

    def test_gerar_proposta_with_condicoes(self):
        svc = self._make_service_without_reportlab()

        proposta = {
            "id": "prop-789",
            "valor_proposta": 300000.0,
            "condicoes": "Entrada de 20% + 48x",
        }

        result = svc.gerar_proposta(proposta)
        text = result.decode("utf-8")
        assert "Entrada de 20% + 48x" in text

    def test_gerar_relatorio_financeiro_returns_bytes(self):
        svc = self._make_service_without_reportlab()

        dados = {
            "receita_total": 150000.0,
            "despesa_total": 50000.0,
            "saldo": 100000.0,
            "previsao_receita": 200000.0,
        }

        result = svc.gerar_relatorio_financeiro(dados)

        assert isinstance(result, bytes)
        text = result.decode("utf-8")
        assert "RELATÓRIO FINANCEIRO" in text
        assert "R$ 150.000,00" in text
        assert "R$ 50.000,00" in text
        assert "R$ 100.000,00" in text

    def test_gerar_dimob_returns_bytes(self):
        svc = self._make_service_without_reportlab()

        dados = {
            "ano": 2025,
            "secoes": [
                {
                    "titulo": "Vendas Realizadas",
                    "itens": ["Apto 101 - R$ 500.000", "Casa 22 - R$ 300.000"],
                },
                {
                    "titulo": "Aluguéis",
                    "itens": ["Sala 5 - R$ 3.000/mês"],
                },
            ],
        }

        result = svc.gerar_dimob(dados)

        assert isinstance(result, bytes)
        text = result.decode("utf-8")
        assert "DIMOB" in text
        assert "2025" in text
        assert "Vendas Realizadas" in text
        assert "Apto 101" in text
        assert "Aluguéis" in text

    def test_gerar_dimob_empty_secoes(self):
        svc = self._make_service_without_reportlab()

        dados = {"ano": 2025, "secoes": []}
        result = svc.gerar_dimob(dados)
        text = result.decode("utf-8")

        assert "DIMOB" in text
        assert "2025" in text


# ---------------------------------------------------------------------------
# PDFService — routing to correct implementation
# ---------------------------------------------------------------------------

class TestPDFServiceRouting:
    """Verify that the public methods route to the correct implementation."""

    def test_gerar_contrato_uses_texto_when_no_reportlab(self):
        from app.services.pdf_service import PDFService

        svc = PDFService()
        svc._has_reportlab = False

        result = svc.gerar_contrato({"tipo": "venda", "valor_total": 100})
        # Text fallback returns UTF-8 encoded string, not PDF binary
        text = result.decode("utf-8")
        assert "CONTRATO DE VENDA" in text

    def test_gerar_proposta_uses_texto_when_no_reportlab(self):
        from app.services.pdf_service import PDFService

        svc = PDFService()
        svc._has_reportlab = False

        result = svc.gerar_proposta({"valor_proposta": 100})
        text = result.decode("utf-8")
        assert "PROPOSTA COMERCIAL" in text

    def test_gerar_financeiro_uses_texto_when_no_reportlab(self):
        from app.services.pdf_service import PDFService

        svc = PDFService()
        svc._has_reportlab = False

        result = svc.gerar_relatorio_financeiro({
            "receita_total": 0, "despesa_total": 0, "saldo": 0, "previsao_receita": 0
        })
        text = result.decode("utf-8")
        assert "RELATÓRIO FINANCEIRO" in text

    def test_gerar_dimob_uses_texto_when_no_reportlab(self):
        from app.services.pdf_service import PDFService

        svc = PDFService()
        svc._has_reportlab = False

        result = svc.gerar_dimob({"ano": 2025, "secoes": []})
        text = result.decode("utf-8")
        assert "DIMOB" in text

    def test_default_values_when_data_missing(self):
        """Ensure missing keys fall back to 0/N/A gracefully."""
        from app.services.pdf_service import PDFService

        svc = PDFService()
        svc._has_reportlab = False

        # All generation methods should handle empty dicts without crashing
        result_contrato = svc.gerar_contrato({})
        assert isinstance(result_contrato, bytes)

        result_proposta = svc.gerar_proposta({})
        assert isinstance(result_proposta, bytes)

        result_financeiro = svc.gerar_relatorio_financeiro({})
        assert isinstance(result_financeiro, bytes)

        result_dimob = svc.gerar_dimob({})
        assert isinstance(result_dimob, bytes)
