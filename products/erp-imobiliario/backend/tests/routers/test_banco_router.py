"""
Tests for Banco router — /api/banco
Covers statement import, extratos listing, reconciliation, and remittance generation.
"""
import pytest


class TestImportarExtrato:
    def test_import_success(self, client):
        client._mock_supabase.set_table_data("extratos_bancarios", {
            "id": "ext-new", "banco": "001", "arquivo_nome": "extrato_001.csv",
            "total_registros": 2,
        })
        client._mock_supabase.set_table_data("movimentacoes_bancarias", [])
        resp = client.post("/api/banco/importar", json={
            "banco": "001",
            "agencia": "1234",
            "conta": "56789-0",
            "movimentacoes": [
                {"data": "2026-03-01", "descricao": "Deposito aluguel",
                 "valor": 2500.00, "tipo": "credito"},
                {"data": "2026-03-05", "descricao": "Taxa bancaria",
                 "valor": 35.00, "tipo": "debito"},
            ],
        })
        assert resp.status_code == 200


class TestListarExtratos:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("extratos_bancarios", [
            {"id": "ext1", "banco": "001", "arquivo_nome": "extrato_001.csv",
             "total_registros": 10},
            {"id": "ext2", "banco": "237", "arquivo_nome": "extrato_237.csv",
             "total_registros": 5},
        ])
        resp = client.get("/api/banco/extratos")
        assert resp.status_code == 200


class TestConciliacao:
    def test_get_pendentes(self, client):
        client._mock_supabase.set_table_data("movimentacoes_bancarias", [
            {"id": "mov1", "data": "2026-03-01", "descricao": "Deposito",
             "valor": 2500, "tipo": "credito", "conciliado": False},
        ])
        resp = client.get("/api/banco/conciliacao")
        assert resp.status_code == 200

    def test_conciliar_success(self, client):
        client._mock_supabase.set_table_data("movimentacoes_bancarias", {
            "id": "mov1", "conciliado": True, "lancamento_id": "lanc1",
        })
        client._mock_supabase.set_table_data("lancamentos", {"id": "lanc1"})
        resp = client.post("/api/banco/conciliar", json={
            "movimentacao_id": "mov1",
            "lancamento_id": "lanc1",
        })
        assert resp.status_code == 200


class TestRemessa:
    def test_gerar_remessa(self, client):
        client._mock_supabase.set_table_data("remessas", {
            "id": "rem-new", "tipo": "cnab240", "banco": "001",
            "total_titulos": 2, "valor_total": 3500.00, "status": "gerado",
        })
        resp = client.post("/api/banco/gerar-remessa", json={
            "tipo": "cnab240",
            "banco": "001",
            "titulos": [
                {"valor": 2000.00, "vencimento": "2026-04-01",
                 "sacado_nome": "Joao Silva", "sacado_cpf": "12345678901"},
                {"valor": 1500.00, "vencimento": "2026-04-15",
                 "sacado_nome": "Maria Santos", "sacado_cpf": "98765432100"},
            ],
        })
        assert resp.status_code == 200

    def test_get_retorno(self, client):
        client._mock_supabase.set_table_data("remessas", {
            "id": "rem1", "tipo": "cnab240", "banco": "001",
            "status": "processado", "total_titulos": 2, "valor_total": 3500.00,
        })
        resp = client.get("/api/banco/retorno/rem1")
        assert resp.status_code == 200
