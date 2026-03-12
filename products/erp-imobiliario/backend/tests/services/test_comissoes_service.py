"""
Unit tests for ComissoesService — commission calculation, split validation, agent summaries.
"""
import pytest
from unittest.mock import MagicMock

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# calculate_commission
# ---------------------------------------------------------------------------

class TestCalculateCommission:

    def test_basic_percentage(self):
        from app.services.comissoes_service import ComissoesService

        assert ComissoesService.calculate_commission(500000.0, 6.0) == 30000.0

    def test_five_percent(self):
        from app.services.comissoes_service import ComissoesService

        assert ComissoesService.calculate_commission(1000000.0, 5.0) == 50000.0

    def test_fractional_percentage(self):
        from app.services.comissoes_service import ComissoesService

        assert ComissoesService.calculate_commission(200000.0, 3.5) == 7000.0

    def test_zero_value(self):
        from app.services.comissoes_service import ComissoesService

        assert ComissoesService.calculate_commission(0, 6.0) == 0.0

    def test_zero_percentage(self):
        from app.services.comissoes_service import ComissoesService

        assert ComissoesService.calculate_commission(500000.0, 0) == 0.0

    def test_rounding(self):
        from app.services.comissoes_service import ComissoesService

        # 333333.33 * 6% = 19999.9998 → rounded to 20000.00
        result = ComissoesService.calculate_commission(333333.33, 6.0)
        assert result == 20000.0

    def test_small_value(self):
        from app.services.comissoes_service import ComissoesService

        assert ComissoesService.calculate_commission(1000.0, 10.0) == 100.0

    def test_hundred_percent(self):
        from app.services.comissoes_service import ComissoesService

        assert ComissoesService.calculate_commission(50000.0, 100.0) == 50000.0


# ---------------------------------------------------------------------------
# calculate_splits
# ---------------------------------------------------------------------------

class TestCalculateSplits:

    def test_single_agent_100_percent(self):
        from app.services.comissoes_service import ComissoesService

        splits = ComissoesService.calculate_splits(30000.0, [
            {"corretor_id": "a1", "corretor_nome": "Ana", "percentual": 100.0},
        ])

        assert len(splits) == 1
        assert splits[0]["valor"] == 30000.0
        assert splits[0]["corretor_nome"] == "Ana"

    def test_two_agents_equal_split(self):
        from app.services.comissoes_service import ComissoesService

        splits = ComissoesService.calculate_splits(30000.0, [
            {"corretor_id": "a1", "corretor_nome": "Ana", "percentual": 50.0},
            {"corretor_id": "a2", "corretor_nome": "Bruno", "percentual": 50.0},
        ])

        assert len(splits) == 2
        assert splits[0]["valor"] == 15000.0
        assert splits[1]["valor"] == 15000.0

    def test_three_agents_unequal_split(self):
        from app.services.comissoes_service import ComissoesService

        splits = ComissoesService.calculate_splits(10000.0, [
            {"corretor_id": "a1", "corretor_nome": "Ana", "percentual": 50.0},
            {"corretor_id": "a2", "corretor_nome": "Bruno", "percentual": 30.0},
            {"corretor_id": "a3", "corretor_nome": "Carlos", "percentual": 20.0},
        ])

        assert len(splits) == 3
        assert splits[0]["valor"] == 5000.0
        assert splits[1]["valor"] == 3000.0
        assert splits[2]["valor"] == 2000.0

    def test_empty_splits_returns_empty(self):
        from app.services.comissoes_service import ComissoesService

        splits = ComissoesService.calculate_splits(30000.0, [])
        assert splits == []

    def test_percentages_not_summing_to_100_raises(self):
        from app.services.comissoes_service import ComissoesService

        with pytest.raises(ValueError, match="somar 100%"):
            ComissoesService.calculate_splits(30000.0, [
                {"corretor_id": "a1", "corretor_nome": "Ana", "percentual": 60.0},
                {"corretor_id": "a2", "corretor_nome": "Bruno", "percentual": 30.0},
            ])

    def test_percentages_over_100_raises(self):
        from app.services.comissoes_service import ComissoesService

        with pytest.raises(ValueError, match="somar 100%"):
            ComissoesService.calculate_splits(30000.0, [
                {"corretor_id": "a1", "corretor_nome": "Ana", "percentual": 60.0},
                {"corretor_id": "a2", "corretor_nome": "Bruno", "percentual": 50.0},
            ])

    def test_missing_corretor_id_raises(self):
        from app.services.comissoes_service import ComissoesService

        with pytest.raises(ValueError, match="corretor_id"):
            ComissoesService.calculate_splits(30000.0, [
                {"corretor_nome": "Ana", "percentual": 100.0},
            ])

    def test_missing_corretor_nome_raises(self):
        from app.services.comissoes_service import ComissoesService

        with pytest.raises(ValueError, match="corretor_nome"):
            ComissoesService.calculate_splits(30000.0, [
                {"corretor_id": "a1", "percentual": 100.0},
            ])

    def test_zero_percentual_raises(self):
        from app.services.comissoes_service import ComissoesService

        with pytest.raises(ValueError, match="maior que 0"):
            ComissoesService.calculate_splits(30000.0, [
                {"corretor_id": "a1", "corretor_nome": "Ana", "percentual": 0},
                {"corretor_id": "a2", "corretor_nome": "Bruno", "percentual": 100.0},
            ])

    def test_negative_percentual_raises(self):
        from app.services.comissoes_service import ComissoesService

        with pytest.raises(ValueError, match="maior que 0"):
            ComissoesService.calculate_splits(30000.0, [
                {"corretor_id": "a1", "corretor_nome": "Ana", "percentual": -10.0},
                {"corretor_id": "a2", "corretor_nome": "Bruno", "percentual": 110.0},
            ])

    def test_floating_point_tolerance(self):
        """Splits that sum to 100% within floating-point tolerance should pass."""
        from app.services.comissoes_service import ComissoesService

        # 33.33 + 33.33 + 33.34 = 100.0 exactly
        splits = ComissoesService.calculate_splits(9999.0, [
            {"corretor_id": "a1", "corretor_nome": "Ana", "percentual": 33.33},
            {"corretor_id": "a2", "corretor_nome": "Bruno", "percentual": 33.33},
            {"corretor_id": "a3", "corretor_nome": "Carlos", "percentual": 33.34},
        ])

        assert len(splits) == 3
        total_valor = sum(s["valor"] for s in splits)
        assert abs(total_valor - 9999.0) < 0.02  # rounding tolerance

    def test_split_values_rounded(self):
        from app.services.comissoes_service import ComissoesService

        splits = ComissoesService.calculate_splits(10000.0, [
            {"corretor_id": "a1", "corretor_nome": "Ana", "percentual": 33.33},
            {"corretor_id": "a2", "corretor_nome": "Bruno", "percentual": 33.33},
            {"corretor_id": "a3", "corretor_nome": "Carlos", "percentual": 33.34},
        ])

        for s in splits:
            # Every split value should have at most 2 decimal places
            assert s["valor"] == round(s["valor"], 2)


# ---------------------------------------------------------------------------
# get_agent_summary
# ---------------------------------------------------------------------------

class TestGetAgentSummary:

    def test_aggregates_by_agent(self):
        from app.services.comissoes_service import ComissoesService

        db = MockSupabaseClient()
        svc = ComissoesService(db, "user-1")

        mock_supabase = MockSupabaseClient(data=[
            {
                "corretor_id": "a1",
                "corretor_nome": "Ana",
                "valor": 5000.0,
                "comissao": {"status": "paga", "valor_comissao": 10000},
            },
            {
                "corretor_id": "a1",
                "corretor_nome": "Ana",
                "valor": 3000.0,
                "comissao": {"status": "pendente", "valor_comissao": 6000},
            },
            {
                "corretor_id": "a2",
                "corretor_nome": "Bruno",
                "valor": 7000.0,
                "comissao": {"status": "aprovada", "valor_comissao": 14000},
            },
        ])

        result = svc.get_agent_summary(mock_supabase)

        assert len(result) == 2

        ana = next(a for a in result if a["corretor_nome"] == "Ana")
        assert ana["total_paga"] == 5000.0
        assert ana["total_pendente"] == 3000.0
        assert ana["total_geral"] == 8000.0
        assert ana["quantidade"] == 2

        bruno = next(a for a in result if a["corretor_nome"] == "Bruno")
        assert bruno["total_aprovada"] == 7000.0
        assert bruno["total_geral"] == 7000.0
        assert bruno["quantidade"] == 1

    def test_empty_splits_returns_empty(self):
        from app.services.comissoes_service import ComissoesService

        db = MockSupabaseClient()
        svc = ComissoesService(db, "user-1")

        mock_supabase = MockSupabaseClient(data=[])
        result = svc.get_agent_summary(mock_supabase)

        assert result == []

    def test_handles_missing_comissao_gracefully(self):
        from app.services.comissoes_service import ComissoesService

        db = MockSupabaseClient()
        svc = ComissoesService(db, "user-1")

        mock_supabase = MockSupabaseClient(data=[
            {
                "corretor_id": "a1",
                "corretor_nome": "Ana",
                "valor": 2000.0,
                "comissao": None,
            },
        ])

        result = svc.get_agent_summary(mock_supabase)

        assert len(result) == 1
        assert result[0]["total_pendente"] == 2000.0  # defaults to pendente

    def test_values_are_rounded(self):
        from app.services.comissoes_service import ComissoesService

        db = MockSupabaseClient()
        svc = ComissoesService(db, "user-1")

        mock_supabase = MockSupabaseClient(data=[
            {
                "corretor_id": "a1",
                "corretor_nome": "Ana",
                "valor": 3333.333,
                "comissao": {"status": "paga", "valor_comissao": 10000},
            },
            {
                "corretor_id": "a1",
                "corretor_nome": "Ana",
                "valor": 3333.333,
                "comissao": {"status": "paga", "valor_comissao": 10000},
            },
        ])

        result = svc.get_agent_summary(mock_supabase)
        ana = result[0]

        # Values should be rounded to 2 decimal places
        assert ana["total_paga"] == round(ana["total_paga"], 2)
        assert ana["total_geral"] == round(ana["total_geral"], 2)

    def test_exception_returns_empty_list(self):
        """When the database query fails, the method should return an empty list."""
        from app.services.comissoes_service import ComissoesService

        db = MockSupabaseClient()
        svc = ComissoesService(db, "user-1")

        # Create a mock that raises an exception on .table()
        broken_supabase = MagicMock()
        broken_supabase.table.side_effect = Exception("DB connection error")

        result = svc.get_agent_summary(broken_supabase)

        assert result == []

    def test_single_agent_all_statuses(self):
        from app.services.comissoes_service import ComissoesService

        db = MockSupabaseClient()
        svc = ComissoesService(db, "user-1")

        mock_supabase = MockSupabaseClient(data=[
            {"corretor_id": "a1", "corretor_nome": "Ana", "valor": 1000.0,
             "comissao": {"status": "pendente", "valor_comissao": 5000}},
            {"corretor_id": "a1", "corretor_nome": "Ana", "valor": 2000.0,
             "comissao": {"status": "aprovada", "valor_comissao": 5000}},
            {"corretor_id": "a1", "corretor_nome": "Ana", "valor": 3000.0,
             "comissao": {"status": "paga", "valor_comissao": 5000}},
            {"corretor_id": "a1", "corretor_nome": "Ana", "valor": 500.0,
             "comissao": {"status": "cancelada", "valor_comissao": 5000}},
        ])

        result = svc.get_agent_summary(mock_supabase)

        assert len(result) == 1
        ana = result[0]
        assert ana["total_pendente"] == 1000.0
        assert ana["total_aprovada"] == 2000.0
        assert ana["total_paga"] == 3000.0
        assert ana["total_geral"] == 6500.0  # all statuses contribute to total
        assert ana["quantidade"] == 4
