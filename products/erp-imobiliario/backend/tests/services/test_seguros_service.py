"""
Unit tests for SegurosService — expiration tracking, summary calculation, check_vencidos.
"""
import pytest
from datetime import date, timedelta

from tests.conftest import MockSupabaseClient


# ---------------------------------------------------------------------------
# get_resumo
# ---------------------------------------------------------------------------

class TestGetResumo:

    def _svc(self):
        from app.services.seguros_service import SegurosService
        return SegurosService(MockSupabaseClient(), "u1")

    def test_empty_list(self):
        svc = self._svc()
        resumo = svc.get_resumo([])

        assert resumo["ativos"] == 0
        assert resumo["total_cobertura"] == 0.0
        assert resumo["total_premio_anual"] == 0.0
        assert resumo["vencendo_30d"] == 0

    def test_counts_only_active_policies(self):
        svc = self._svc()

        seguros = [
            {"status": "ativo", "valor_cobertura": 100000, "valor_premio": 1200, "data_vencimento": "2099-12-31"},
            {"status": "ativo", "valor_cobertura": 200000, "valor_premio": 2400, "data_vencimento": "2099-12-31"},
            {"status": "vencido", "valor_cobertura": 50000, "valor_premio": 600},
            {"status": "cancelado", "valor_cobertura": 75000, "valor_premio": 900},
        ]

        resumo = svc.get_resumo(seguros)

        assert resumo["ativos"] == 2
        assert resumo["total_cobertura"] == 300000.0
        assert resumo["total_premio_anual"] == 3600.0

    def test_vencendo_30d_detection(self):
        svc = self._svc()

        dentro_30d = (date.today() + timedelta(days=15)).isoformat()
        fora_30d = (date.today() + timedelta(days=60)).isoformat()
        passado = (date.today() - timedelta(days=1)).isoformat()

        seguros = [
            {"status": "ativo", "valor_cobertura": 100000, "valor_premio": 1000, "data_vencimento": dentro_30d},
            {"status": "ativo", "valor_cobertura": 100000, "valor_premio": 1000, "data_vencimento": fora_30d},
            {"status": "ativo", "valor_cobertura": 100000, "valor_premio": 1000, "data_vencimento": passado},
        ]

        resumo = svc.get_resumo(seguros)

        # Only the one within 30 days (and >= today) should count
        assert resumo["vencendo_30d"] == 1

    def test_today_counts_as_vencendo(self):
        """A policy expiring exactly today should be counted in vencendo_30d."""
        svc = self._svc()

        hoje = date.today().isoformat()

        seguros = [
            {"status": "ativo", "valor_cobertura": 50000, "valor_premio": 500, "data_vencimento": hoje},
        ]

        resumo = svc.get_resumo(seguros)

        assert resumo["vencendo_30d"] == 1

    def test_invalid_date_ignored(self):
        svc = self._svc()

        seguros = [
            {"status": "ativo", "valor_cobertura": 50000, "valor_premio": 500, "data_vencimento": "not-a-date"},
        ]

        resumo = svc.get_resumo(seguros)

        assert resumo["ativos"] == 1
        assert resumo["vencendo_30d"] == 0  # Invalid date skipped

    def test_missing_values_default_to_zero(self):
        svc = self._svc()

        seguros = [
            {"status": "ativo", "data_vencimento": "2099-12-31"},
        ]

        resumo = svc.get_resumo(seguros)

        assert resumo["total_cobertura"] == 0.0
        assert resumo["total_premio_anual"] == 0.0


# ---------------------------------------------------------------------------
# get_vencimentos
# ---------------------------------------------------------------------------

class TestGetVencimentos:

    def test_returns_list(self):
        db = MockSupabaseClient(data=[{"id": "s1"}])

        from app.services.seguros_service import SegurosService
        svc = SegurosService(db, "u1")

        result = svc.get_vencimentos(dias=30)

        assert isinstance(result, list)

    def test_empty_result(self):
        db = MockSupabaseClient(data=[])

        from app.services.seguros_service import SegurosService
        svc = SegurosService(db, "u1")

        result = svc.get_vencimentos(dias=30)

        assert result == []

    def test_custom_days_parameter(self):
        """Verify that the method accepts a custom dias parameter without error."""
        db = MockSupabaseClient(data=[])

        from app.services.seguros_service import SegurosService
        svc = SegurosService(db, "u1")

        result = svc.get_vencimentos(dias=90)

        assert result == []


# ---------------------------------------------------------------------------
# check_vencidos
# ---------------------------------------------------------------------------

class TestCheckVencidos:

    def test_no_expired_returns_zero(self):
        db = MockSupabaseClient(data=[])

        from app.services.seguros_service import SegurosService
        svc = SegurosService(db, "u1")

        count = svc.check_vencidos()

        assert count == 0

    def test_expired_policies_are_counted(self):
        db = MockSupabaseClient(data=[{"id": "s1"}, {"id": "s2"}])

        from app.services.seguros_service import SegurosService
        svc = SegurosService(db, "u1")

        count = svc.check_vencidos()

        assert count == 2


# ---------------------------------------------------------------------------
# Class constants
# ---------------------------------------------------------------------------

class TestConstants:

    def test_valid_statuses(self):
        from app.services.seguros_service import SegurosService

        assert "ativo" in SegurosService.VALID_STATUSES
        assert "vencido" in SegurosService.VALID_STATUSES
        assert "cancelado" in SegurosService.VALID_STATUSES
        assert "renovado" in SegurosService.VALID_STATUSES

    def test_valid_coberturas(self):
        from app.services.seguros_service import SegurosService

        assert "incendio" in SegurosService.VALID_COBERTURAS
        assert "completo" in SegurosService.VALID_COBERTURAS
        assert "fianca_locaticia" in SegurosService.VALID_COBERTURAS
