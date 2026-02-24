"""
Unit tests for BIService — sales, leads, broker performance, property, and financial analytics.
"""
import pytest

from tests.conftest import MockSupabaseClient


# ---------------------------------------------------------------------------
# get_vendas_analytics
# ---------------------------------------------------------------------------

class TestGetVendasAnalytics:

    def _svc(self):
        from app.services.bi_service import BIService
        return BIService(MockSupabaseClient(), "u1")

    def test_empty_data(self):
        svc = self._svc()

        result = svc.get_vendas_analytics([], [])

        assert result["total_vendas"] == 0
        assert result["valor_total"] == 0
        assert result["ticket_medio"] == 0.0
        assert result["taxa_conversao"] == 0.0
        assert result["tempo_medio_fechamento"] == 0.0
        assert result["vendas_por_mes"] == []

    def test_basic_sales_calculation(self):
        svc = self._svc()

        propostas = [
            {"status": "aceita", "valor_proposta": 200000, "created_at": "2026-01-15T10:00:00Z", "updated_at": "2026-01-25T10:00:00Z"},
            {"status": "aceita", "valor_proposta": 300000, "created_at": "2026-01-20T10:00:00Z", "updated_at": "2026-02-10T10:00:00Z"},
            {"status": "pendente", "valor_proposta": 150000, "created_at": "2026-01-25T10:00:00Z"},
            {"status": "recusada", "valor_proposta": 100000, "created_at": "2026-02-01T10:00:00Z"},
        ]

        result = svc.get_vendas_analytics(propostas, [])

        assert result["total_vendas"] == 2
        assert result["total_propostas"] == 4
        assert result["valor_total"] == 500000
        assert result["ticket_medio"] == 250000.0
        assert result["taxa_conversao"] == 50.0

    def test_tempo_medio_fechamento(self):
        svc = self._svc()

        propostas = [
            {
                "status": "aceita",
                "valor_proposta": 100000,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-11T00:00:00Z",  # 10 days
            },
            {
                "status": "aceita",
                "valor_proposta": 100000,
                "created_at": "2026-02-01T00:00:00Z",
                "updated_at": "2026-02-21T00:00:00Z",  # 20 days
            },
        ]

        result = svc.get_vendas_analytics(propostas, [])

        assert result["tempo_medio_fechamento"] == 15.0  # (10 + 20) / 2

    def test_vendas_por_mes_grouping(self):
        svc = self._svc()

        propostas = [
            {"status": "aceita", "valor_proposta": 100000, "created_at": "2026-01-10T00:00:00Z", "updated_at": "2026-01-20T00:00:00Z"},
            {"status": "aceita", "valor_proposta": 200000, "created_at": "2026-01-20T00:00:00Z", "updated_at": "2026-01-25T00:00:00Z"},
            {"status": "aceita", "valor_proposta": 150000, "created_at": "2026-02-05T00:00:00Z", "updated_at": "2026-02-10T00:00:00Z"},
        ]

        result = svc.get_vendas_analytics(propostas, [])

        assert len(result["vendas_por_mes"]) == 2
        jan = result["vendas_por_mes"][0]
        fev = result["vendas_por_mes"][1]
        assert jan["mes"] == "2026-01"
        assert jan["quantidade"] == 2
        assert jan["valor_total"] == 300000.0
        assert fev["mes"] == "2026-02"
        assert fev["quantidade"] == 1

    def test_period_filter(self):
        svc = self._svc()

        propostas = [
            {"status": "aceita", "valor_proposta": 100000, "created_at": "2025-12-01T00:00:00Z", "updated_at": "2025-12-10T00:00:00Z"},
            {"status": "aceita", "valor_proposta": 200000, "created_at": "2026-01-15T00:00:00Z", "updated_at": "2026-01-20T00:00:00Z"},
            {"status": "aceita", "valor_proposta": 300000, "created_at": "2026-03-01T00:00:00Z", "updated_at": "2026-03-10T00:00:00Z"},
        ]

        result = svc.get_vendas_analytics(
            propostas, [],
            periodo_inicio="2026-01-01",
            periodo_fim="2026-02-28",
        )

        assert result["total_vendas"] == 1
        assert result["total_propostas"] == 1

    def test_invalid_dates_skipped_for_tempo(self):
        svc = self._svc()

        propostas = [
            {"status": "aceita", "valor_proposta": 100000, "created_at": "not-a-date", "updated_at": "also-not"},
        ]

        result = svc.get_vendas_analytics(propostas, [])

        assert result["tempo_medio_fechamento"] == 0.0


# ---------------------------------------------------------------------------
# get_captacao_analytics
# ---------------------------------------------------------------------------

class TestGetCaptacaoAnalytics:

    def _svc(self):
        from app.services.bi_service import BIService
        return BIService(MockSupabaseClient(), "u1")

    def test_empty_clients(self):
        svc = self._svc()

        result = svc.get_captacao_analytics([])

        assert result["total_leads"] == 0
        assert result["leads_por_origem"] == []
        assert result["leads_por_mes"] == []
        assert result["taxa_conversao_por_origem"] == []

    def test_leads_por_origem(self):
        svc = self._svc()

        clientes = [
            {"origem": "Portal", "created_at": "2026-01-01T00:00:00Z"},
            {"origem": "Portal", "created_at": "2026-01-02T00:00:00Z"},
            {"origem": "Indicacao", "created_at": "2026-01-03T00:00:00Z"},
            {"created_at": "2026-01-04T00:00:00Z"},  # no origin -> "Desconhecida"
        ]

        result = svc.get_captacao_analytics(clientes)

        assert result["total_leads"] == 4
        origens = {o["origem"]: o["quantidade"] for o in result["leads_por_origem"]}
        assert origens["Portal"] == 2
        assert origens["Indicacao"] == 1
        assert origens["Desconhecida"] == 1

    def test_leads_por_mes(self):
        svc = self._svc()

        clientes = [
            {"origem": "Portal", "created_at": "2026-01-15T00:00:00Z"},
            {"origem": "Portal", "created_at": "2026-01-20T00:00:00Z"},
            {"origem": "Portal", "created_at": "2026-02-05T00:00:00Z"},
        ]

        result = svc.get_captacao_analytics(clientes)

        meses = {m["mes"]: m["quantidade"] for m in result["leads_por_mes"]}
        assert meses["2026-01"] == 2
        assert meses["2026-02"] == 1

    def test_conversion_rate_by_origin(self):
        svc = self._svc()

        clientes = [
            {"origem": "Portal", "etapa_atual": "fechamento", "created_at": "2026-01-01T00:00:00Z"},
            {"origem": "Portal", "etapa_atual": "qualificacao", "created_at": "2026-01-02T00:00:00Z"},
            {"origem": "Indicacao", "etapa_atual": "venda", "created_at": "2026-01-03T00:00:00Z"},
            {"origem": "Indicacao", "etapa_atual": "contrato", "created_at": "2026-01-04T00:00:00Z"},
        ]

        result = svc.get_captacao_analytics(clientes)

        conversion_map = {c["origem"]: c for c in result["taxa_conversao_por_origem"]}
        assert conversion_map["Portal"]["taxa_conversao"] == 50.0
        assert conversion_map["Indicacao"]["taxa_conversao"] == 100.0


# ---------------------------------------------------------------------------
# get_corretores_analytics
# ---------------------------------------------------------------------------

class TestGetCorretoresAnalytics:

    def _svc(self):
        from app.services.bi_service import BIService
        return BIService(MockSupabaseClient(), "u1")

    def test_empty_data(self):
        svc = self._svc()

        result = svc.get_corretores_analytics([], [])

        assert result == []

    def test_broker_ranking(self):
        svc = self._svc()

        propostas = [
            {"corretor_id": "b1", "status": "aceita", "valor_proposta": 200000},
            {"corretor_id": "b1", "status": "pendente", "valor_proposta": 100000},
            {"corretor_id": "b2", "status": "aceita", "valor_proposta": 500000},
        ]

        result = svc.get_corretores_analytics(propostas, [])

        assert len(result) == 2
        # b2 should be first (500k > 200k)
        assert result[0]["corretor_id"] == "b2"
        assert result[0]["vendas"] == 1
        assert result[0]["valor_total"] == 500000.0

        assert result[1]["corretor_id"] == "b1"
        assert result[1]["vendas"] == 1
        assert result[1]["atendimentos"] == 2
        assert result[1]["taxa_conversao"] == 50.0

    def test_commission_aggregation(self):
        svc = self._svc()

        propostas = [
            {"corretor_id": "b1", "status": "aceita", "valor_proposta": 100000},
        ]

        comissoes = [
            {
                "splits": [
                    {"corretor_id": "b1", "valor": 5000, "corretor_nome": "Joao"},
                    {"corretor_id": "b2", "valor": 3000, "corretor_nome": "Maria"},
                ]
            },
        ]

        result = svc.get_corretores_analytics(propostas, comissoes)

        b1_data = next(r for r in result if r["corretor_id"] == "b1")
        assert b1_data["comissao_total"] == 5000.0
        # b2 is in comissoes but not in propostas, so not in result
        assert not any(r["corretor_id"] == "b2" for r in result)

    def test_proposals_without_corretor_id_ignored(self):
        svc = self._svc()

        propostas = [
            {"corretor_id": None, "status": "aceita", "valor_proposta": 100000},
            {"status": "aceita", "valor_proposta": 200000},  # no corretor_id key
        ]

        result = svc.get_corretores_analytics(propostas, [])

        assert result == []


# ---------------------------------------------------------------------------
# get_imoveis_analytics
# ---------------------------------------------------------------------------

class TestGetImoveisAnalytics:

    def _svc(self):
        from app.services.bi_service import BIService
        return BIService(MockSupabaseClient(), "u1")

    def test_empty_data(self):
        svc = self._svc()

        result = svc.get_imoveis_analytics([])

        assert result["total_ativos"] == 0
        assert result["media_dias_mercado"] == 0.0
        assert result["preco_m2_medio"] == 0.0
        assert result["distribuicao_tipo"] == []
        assert result["distribuicao_status"] == []
        assert result["imoveis_por_bairro"] == []

    def test_price_per_sqm(self):
        svc = self._svc()

        ativos = [
            {"valor": 200000, "area_total": 100, "status": "ativo", "tipo_imovel": "apartamento", "bairro": "Centro"},
            {"valor": 400000, "area_total": 200, "status": "ativo", "tipo_imovel": "casa", "bairro": "Jardins"},
        ]

        result = svc.get_imoveis_analytics(ativos)

        # 200000/100 = 2000, 400000/200 = 2000
        assert result["preco_m2_medio"] == 2000.0

    def test_type_distribution(self):
        svc = self._svc()

        ativos = [
            {"status": "ativo", "tipo_imovel": "apartamento", "valor": 0, "bairro": "A"},
            {"status": "ativo", "tipo_imovel": "apartamento", "valor": 0, "bairro": "A"},
            {"status": "ativo", "tipo_imovel": "casa", "valor": 0, "bairro": "B"},
        ]

        result = svc.get_imoveis_analytics(ativos)

        tipos_map = {t["tipo"]: t["quantidade"] for t in result["distribuicao_tipo"]}
        assert tipos_map["apartamento"] == 2
        assert tipos_map["casa"] == 1

    def test_zero_area_excluded_from_price(self):
        svc = self._svc()

        ativos = [
            {"valor": 200000, "area_total": 0, "status": "ativo", "tipo_imovel": "terreno", "bairro": "X"},
        ]

        result = svc.get_imoveis_analytics(ativos)

        assert result["preco_m2_medio"] == 0.0


# ---------------------------------------------------------------------------
# get_financeiro_analytics
# ---------------------------------------------------------------------------

class TestGetFinanceiroAnalytics:

    def _svc(self):
        from app.services.bi_service import BIService
        return BIService(MockSupabaseClient(), "u1")

    def test_empty_data(self):
        svc = self._svc()

        result = svc.get_financeiro_analytics([])

        assert result["receita_total"] == 0.0
        assert result["despesa_total"] == 0.0
        assert result["saldo"] == 0.0
        assert result["previsao_receita"] == 0.0
        assert result["despesas_por_categoria"] == []
        assert result["receitas_por_mes"] == []

    def test_receita_and_despesa_calculation(self):
        svc = self._svc()

        lancamentos = [
            {"tipo": "receita", "status": "pago", "valor": 5000, "data_pagamento": "2026-01-15", "data_vencimento": "2026-01-10"},
            {"tipo": "receita", "status": "pago", "valor": 3000, "data_pagamento": "2026-02-15", "data_vencimento": "2026-02-10"},
            {"tipo": "receita", "status": "pendente", "valor": 2000, "data_vencimento": "2026-03-10"},
            {"tipo": "despesa", "status": "pago", "valor": 1000, "categoria": "Manutencao", "data_vencimento": "2026-01-20"},
            {"tipo": "despesa", "status": "pago", "valor": 500, "categoria": "Administrativo", "data_vencimento": "2026-01-25"},
        ]

        result = svc.get_financeiro_analytics(lancamentos)

        assert result["receita_total"] == 8000.0
        assert result["despesa_total"] == 1500.0
        assert result["saldo"] == 6500.0
        assert result["previsao_receita"] == 2000.0

    def test_despesas_por_categoria(self):
        svc = self._svc()

        lancamentos = [
            {"tipo": "despesa", "status": "pago", "valor": 1000, "categoria": "Manutencao", "data_vencimento": "2026-01-01"},
            {"tipo": "despesa", "status": "pago", "valor": 2000, "categoria": "Manutencao", "data_vencimento": "2026-01-02"},
            {"tipo": "despesa", "status": "pago", "valor": 500, "categoria": "Administrativo", "data_vencimento": "2026-01-03"},
        ]

        result = svc.get_financeiro_analytics(lancamentos)

        cats = {c["categoria"]: c["valor"] for c in result["despesas_por_categoria"]}
        assert cats["Manutencao"] == 3000.0
        assert cats["Administrativo"] == 500.0

    def test_period_filter(self):
        svc = self._svc()

        lancamentos = [
            {"tipo": "receita", "status": "pago", "valor": 1000, "data_vencimento": "2025-12-01"},
            {"tipo": "receita", "status": "pago", "valor": 2000, "data_vencimento": "2026-01-15"},
            {"tipo": "receita", "status": "pago", "valor": 3000, "data_vencimento": "2026-03-01"},
        ]

        result = svc.get_financeiro_analytics(
            lancamentos,
            periodo_inicio="2026-01-01",
            periodo_fim="2026-02-28",
        )

        assert result["receita_total"] == 2000.0


# ---------------------------------------------------------------------------
# _filter_by_periodo (private helper)
# ---------------------------------------------------------------------------

class TestFilterByPeriodo:

    def _svc(self):
        from app.services.bi_service import BIService
        return BIService(MockSupabaseClient(), "u1")

    def test_no_filters_returns_all(self):
        svc = self._svc()

        items = [{"created_at": "2026-01-01"}, {"created_at": "2026-06-01"}]

        result = svc._filter_by_periodo(items, None, None)

        assert len(result) == 2

    def test_start_filter_only(self):
        svc = self._svc()

        items = [
            {"created_at": "2025-12-01"},
            {"created_at": "2026-01-15"},
            {"created_at": "2026-02-01"},
        ]

        result = svc._filter_by_periodo(items, "2026-01-01", None)

        assert len(result) == 2

    def test_end_filter_only(self):
        svc = self._svc()

        items = [
            {"created_at": "2025-12-01"},
            {"created_at": "2026-01-15"},
            {"created_at": "2026-02-01"},
        ]

        result = svc._filter_by_periodo(items, None, "2026-01-31")

        assert len(result) == 2

    def test_both_filters(self):
        svc = self._svc()

        items = [
            {"created_at": "2025-12-01"},
            {"created_at": "2026-01-15"},
            {"created_at": "2026-02-01"},
            {"created_at": "2026-03-01"},
        ]

        result = svc._filter_by_periodo(items, "2026-01-01", "2026-02-28")

        assert len(result) == 2

    def test_items_without_date_field_are_excluded(self):
        svc = self._svc()

        items = [
            {"created_at": "2026-01-15"},
            {"other_field": "no date"},
        ]

        result = svc._filter_by_periodo(items, "2026-01-01", "2026-12-31")

        assert len(result) == 1

    def test_custom_date_field(self):
        svc = self._svc()

        items = [
            {"data_vencimento": "2026-01-15"},
            {"data_vencimento": "2026-03-01"},
        ]

        result = svc._filter_by_periodo(
            items, "2026-01-01", "2026-02-28",
            date_field="data_vencimento",
        )

        assert len(result) == 1
