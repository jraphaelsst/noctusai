"""
Tests for Recorrência router — /api/recorrencia
Covers rent generation, recurring entries, and overdue detection.
"""
import pytest


class TestGerarAlugueis:
    def test_gerar_alugueis_sem_contratos(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", [])
        resp = client.post("/api/recorrencia/alugueis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["gerados"] == 0

    def test_gerar_alugueis_com_contrato(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", [
            {"id": "cl1", "status": "ativo", "valor_aluguel": 2500,
             "dia_vencimento": 10, "cliente_id": "c1", "imovel_id": "i1"},
        ])
        client._mock_supabase.set_table_data("lancamentos", [])
        resp = client.post("/api/recorrencia/alugueis?referencia=2026-03")
        assert resp.status_code == 200

    def test_gerar_alugueis_com_referencia(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", [])
        resp = client.post("/api/recorrencia/alugueis?referencia=2026-06")
        assert resp.status_code == 200


class TestGerarLancamentosRecorrentes:
    def test_sem_recorrentes(self, client):
        client._mock_supabase.set_table_data("lancamentos", [])
        resp = client.post("/api/recorrencia/lancamentos")
        assert resp.status_code == 200

    def test_com_recorrente(self, client):
        client._mock_supabase.set_table_data("lancamentos", [
            {"id": "l1", "tipo": "despesa", "status": "pago", "valor": 500,
             "categoria": "condominio", "descricao": "Cond", "recorrente": True,
             "data_vencimento": "2026-01-10"},
        ])
        resp = client.post("/api/recorrencia/lancamentos")
        assert resp.status_code == 200


class TestVerificarInadimplencia:
    def test_sem_atrasados(self, client):
        client._mock_supabase.set_table_data("lancamentos", [])
        client._mock_supabase.set_table_data("parcelas_contrato", [])
        resp = client.post("/api/recorrencia/inadimplencia")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total_atualizados"] == 0
