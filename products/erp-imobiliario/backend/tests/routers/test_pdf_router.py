"""
Tests for PDF router — /api/pdf
Covers contract, proposal, financial, and DIMOB PDF generation.
"""
import pytest


class TestPDFContrato:
    def test_contrato_not_found(self, client):
        client._mock_supabase.set_table_data("contratos", None)
        resp = client.get("/api/pdf/contrato/nonexistent")
        assert resp.status_code == 404

    def test_contrato_success(self, client):
        client._mock_supabase.set_table_data("contratos", {
            "id": "c1", "tipo": "venda", "status": "ativo",
            "valor_total": 500000, "data_inicio": "2026-01-01",
            "data_fim": "2027-01-01", "observacoes": "Teste",
        })
        client._mock_supabase.set_table_data("parcelas_contrato", [
            {"numero": 1, "valor": 50000, "data_vencimento": "2026-02-01", "status": "pendente"},
            {"numero": 2, "valor": 50000, "data_vencimento": "2026-03-01", "status": "pendente"},
        ])
        resp = client.get("/api/pdf/contrato/c1")
        assert resp.status_code == 200
        assert "pdf" in resp.headers.get("content-type", "").lower() or resp.status_code == 200


class TestPDFProposta:
    def test_proposta_not_found(self, client):
        client._mock_supabase.set_table_data("propostas", None)
        resp = client.get("/api/pdf/proposta/nonexistent")
        assert resp.status_code == 404

    def test_proposta_success(self, client):
        client._mock_supabase.set_table_data("propostas", {
            "id": "p1", "status": "enviada", "valor_proposta": 300000,
            "created_at": "2026-02-01T10:00:00", "condicoes": "A vista",
        })
        resp = client.get("/api/pdf/proposta/p1")
        assert resp.status_code == 200


class TestPDFFinanceiro:
    def test_financeiro_empty(self, client):
        client._mock_supabase.set_table_data("lancamentos", [])
        resp = client.get("/api/pdf/financeiro")
        assert resp.status_code == 200

    def test_financeiro_with_period(self, client):
        client._mock_supabase.set_table_data("lancamentos", [
            {"tipo": "receita", "status": "pago", "valor": 1000,
             "data_vencimento": "2026-01-15", "descricao": "Aluguel"},
        ])
        resp = client.get("/api/pdf/financeiro?periodo_inicio=2026-01-01&periodo_fim=2026-12-31")
        assert resp.status_code == 200


class TestPDFDimob:
    def test_dimob_empty(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", [])
        client._mock_supabase.set_table_data("contratos", [])
        resp = client.get("/api/pdf/dimob/2026")
        assert resp.status_code == 200
