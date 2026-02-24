"""
Tests for BI (Business Intelligence) router — /api/bi
All endpoints are GET-only read analytics.
"""
import pytest


class TestVendas:
    def test_vendas_success(self, client):
        client._mock_supabase.set_table_data("propostas", [
            {"id": "p1", "status": "aceita", "valor_proposta": 500000,
             "created_at": "2026-03-01T10:00:00Z", "updated_at": "2026-03-15T10:00:00Z",
             "corretor_id": "u1"},
            {"id": "p2", "status": "pendente", "valor_proposta": 300000,
             "created_at": "2026-02-01T10:00:00Z", "updated_at": None,
             "corretor_id": "u1"},
        ])
        client._mock_supabase.set_table_data("lancamentos", [
            {"id": "l1", "tipo": "receita", "valor": 500000, "status": "pago",
             "data_vencimento": "2026-03-20"},
        ])
        resp = client.get("/api/bi/vendas")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_vendas" in data

    def test_vendas_with_period(self, client):
        client._mock_supabase.set_table_data("propostas", [
            {"id": "p1", "status": "aceita", "valor_proposta": 250000,
             "created_at": "2026-06-15T10:00:00Z", "updated_at": "2026-06-20T10:00:00Z",
             "corretor_id": "u1"},
        ])
        client._mock_supabase.set_table_data("lancamentos", [])
        resp = client.get("/api/bi/vendas?periodo_inicio=2026-01-01&periodo_fim=2026-12-31")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_vendas" in data
        assert "ticket_medio" in data

    def test_vendas_empty(self, client):
        client._mock_supabase.set_table_data("propostas", [])
        client._mock_supabase.set_table_data("lancamentos", [])
        resp = client.get("/api/bi/vendas")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_vendas"] == 0


class TestCaptacao:
    def test_captacao_success(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "João", "origem": "website",
             "etapa_atual": "qualificacao", "created_at": "2026-01-10T10:00:00Z"},
            {"id": "c2", "nome": "Maria", "origem": "indicação",
             "etapa_atual": "fechamento", "created_at": "2026-02-05T10:00:00Z"},
        ])
        resp = client.get("/api/bi/captacao")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_leads"] == 2
        assert "leads_por_origem" in data

    def test_captacao_empty(self, client):
        client._mock_supabase.set_table_data("clientes", [])
        resp = client.get("/api/bi/captacao")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_leads"] == 0


class TestCorretores:
    def test_corretores_success(self, client):
        client._mock_supabase.set_table_data("propostas", [
            {"id": "p1", "status": "aceita", "valor_proposta": 400000,
             "corretor_id": "u1", "created_at": "2026-01-10T10:00:00Z"},
            {"id": "p2", "status": "pendente", "valor_proposta": 200000,
             "corretor_id": "u1", "created_at": "2026-02-01T10:00:00Z"},
        ])
        client._mock_supabase.set_table_data("comissoes", [
            {"id": "com1", "splits": [
                {"corretor_id": "u1", "corretor_nome": "Corretor A", "valor": 24000},
            ]},
        ])
        resp = client.get("/api/bi/corretores")
        assert resp.status_code == 200

    def test_corretores_with_period(self, client):
        client._mock_supabase.set_table_data("propostas", [
            {"id": "p1", "status": "aceita", "valor_proposta": 300000,
             "corretor_id": "u1", "created_at": "2026-01-15T10:00:00Z"},
        ])
        client._mock_supabase.set_table_data("comissoes", [])
        resp = client.get("/api/bi/corretores?periodo=30d")
        assert resp.status_code == 200


class TestImoveis:
    def test_imoveis_success(self, client):
        client._mock_supabase.set_table_data("ativos", [
            {"id": "a1", "tipo_imovel": "apartamento", "status": "ativo",
             "valor": 500000, "area_total": 100, "bairro": "Centro",
             "created_at": "2026-01-01T10:00:00Z"},
            {"id": "a2", "tipo_imovel": "casa", "status": "vendido",
             "valor": 800000, "area_total": 200, "bairro": "Jardins",
             "created_at": "2025-06-01T10:00:00Z"},
        ])
        resp = client.get("/api/bi/imoveis")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_ativos"] == 2
        assert "distribuicao_tipo" in data

    def test_imoveis_empty(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        resp = client.get("/api/bi/imoveis")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_ativos"] == 0


class TestFinanceiro:
    def test_financeiro_success(self, client):
        client._mock_supabase.set_table_data("lancamentos", [
            {"id": "l1", "tipo": "receita", "valor": 10000, "status": "pago",
             "categoria": "comissao", "data_vencimento": "2026-01-15",
             "data_pagamento": "2026-01-15"},
            {"id": "l2", "tipo": "despesa", "valor": 3000, "status": "pago",
             "categoria": "escritorio", "data_vencimento": "2026-01-20",
             "data_pagamento": "2026-01-20"},
            {"id": "l3", "tipo": "receita", "valor": 5000, "status": "pendente",
             "categoria": "comissao", "data_vencimento": "2026-02-15"},
        ])
        resp = client.get("/api/bi/financeiro")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "receita_total" in data
        assert "despesa_total" in data
        assert "saldo" in data

    def test_financeiro_with_period(self, client):
        client._mock_supabase.set_table_data("lancamentos", [
            {"id": "l1", "tipo": "receita", "valor": 8000, "status": "pago",
             "categoria": "comissao", "data_vencimento": "2026-06-10",
             "data_pagamento": "2026-06-10"},
        ])
        resp = client.get("/api/bi/financeiro?periodo_inicio=2026-01-01&periodo_fim=2026-12-31")
        assert resp.status_code == 200

    def test_financeiro_empty(self, client):
        client._mock_supabase.set_table_data("lancamentos", [])
        resp = client.get("/api/bi/financeiro")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["receita_total"] == 0
        assert data["despesa_total"] == 0
