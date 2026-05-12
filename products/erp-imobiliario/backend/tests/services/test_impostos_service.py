"""
Unit tests for ImpostosService — tax summary, single-payment discount, overdue detection.
"""
import pytest

from tests.conftest import MockSupabaseClient


# ---------------------------------------------------------------------------
# get_resumo
# ---------------------------------------------------------------------------

class TestGetResumo:

    def _svc(self):
        from app.services.impostos_service import ImpostosService
        return ImpostosService(MockSupabaseClient(), "u1")

    def test_empty_list(self):
        svc = self._svc()
        resumo = svc.get_resumo([])

        assert resumo["total_devido"] == 0.0
        assert resumo["total_pago"] == 0.0
        assert resumo["total_pendente"] == 0.0
        assert resumo["total_atrasado"] == 0.0
        assert resumo["quantidade"] == 0
        assert all(v == 0 for v in resumo["count_by_status"].values())

    def test_status_counts(self):
        svc = self._svc()

        impostos = [
            {"status": "pendente", "valor_total": 1000, "valor_pago": 0},
            {"status": "pendente", "valor_total": 2000, "valor_pago": 0},
            {"status": "parcial", "valor_total": 3000, "valor_pago": 1000},
            {"status": "pago", "valor_total": 4000, "valor_pago": 4000},
            {"status": "atrasado", "valor_total": 5000, "valor_pago": 0},
            {"status": "isento", "valor_total": 0, "valor_pago": 0},
        ]

        resumo = svc.get_resumo(impostos)

        assert resumo["count_by_status"]["pendente"] == 2
        assert resumo["count_by_status"]["parcial"] == 1
        assert resumo["count_by_status"]["pago"] == 1
        assert resumo["count_by_status"]["atrasado"] == 1
        assert resumo["count_by_status"]["isento"] == 1
        assert resumo["quantidade"] == 6

    def test_total_sums(self):
        svc = self._svc()

        impostos = [
            {"status": "pendente", "valor_total": 1000, "valor_pago": 0},
            {"status": "parcial", "valor_total": 3000, "valor_pago": 1000},
            {"status": "pago", "valor_total": 4000, "valor_pago": 4000},
            {"status": "atrasado", "valor_total": 5000, "valor_pago": 2000},
        ]

        resumo = svc.get_resumo(impostos)

        assert resumo["total_devido"] == 13000.0
        assert resumo["total_pago"] == 7000.0
        # pendente: 1000-0 = 1000, parcial: 3000-1000 = 2000
        assert resumo["total_pendente"] == 3000.0
        # atrasado: 5000-2000 = 3000
        assert resumo["total_atrasado"] == 3000.0

    def test_unknown_status_not_counted(self):
        svc = self._svc()

        impostos = [
            {"status": "desconhecido", "valor_total": 1000, "valor_pago": 500},
        ]

        resumo = svc.get_resumo(impostos)

        assert resumo["total_devido"] == 1000.0
        assert resumo["total_pago"] == 500.0
        # Unknown status: not pendente/parcial/atrasado, so not added to either
        assert resumo["total_pendente"] == 0.0
        assert resumo["total_atrasado"] == 0.0

    def test_rounding(self):
        svc = self._svc()

        impostos = [
            {"status": "pendente", "valor_total": 100.555, "valor_pago": 0},
            {"status": "pendente", "valor_total": 200.449, "valor_pago": 0},
        ]

        resumo = svc.get_resumo(impostos)

        # Both total_devido and total_pendente should be rounded to 2 decimal places
        assert resumo["total_devido"] == 301.0  # 100.555 + 200.449 = 301.004, rounded = 301.0
        assert resumo["total_pendente"] == 301.0


# ---------------------------------------------------------------------------
# calcular_cota_unica
# ---------------------------------------------------------------------------

class TestCalcularCotaUnica:

    def test_basic_discount(self):
        from app.services.impostos_service import ImpostosService

        result = ImpostosService.calcular_cota_unica(1000.0, 10.0)

        assert result == 900.0

    def test_zero_discount(self):
        from app.services.impostos_service import ImpostosService

        result = ImpostosService.calcular_cota_unica(1000.0, 0.0)

        assert result == 1000.0

    def test_negative_discount_returns_original(self):
        from app.services.impostos_service import ImpostosService

        result = ImpostosService.calcular_cota_unica(1000.0, -5.0)

        assert result == 1000.0

    def test_100_percent_discount(self):
        from app.services.impostos_service import ImpostosService

        result = ImpostosService.calcular_cota_unica(1000.0, 100.0)

        assert result == 0.0

    def test_over_100_percent_discount(self):
        from app.services.impostos_service import ImpostosService

        result = ImpostosService.calcular_cota_unica(1000.0, 150.0)

        assert result == 0.0

    def test_fractional_discount(self):
        from app.services.impostos_service import ImpostosService

        result = ImpostosService.calcular_cota_unica(1000.0, 7.5)

        assert result == 925.0

    def test_rounding_to_two_decimals(self):
        from app.services.impostos_service import ImpostosService

        # 333.33 * 0.10 = 33.333 => 333.33 - 33.333 = 299.997 => 300.0
        result = ImpostosService.calcular_cota_unica(333.33, 10.0)

        assert result == 300.0  # round(299.997, 2)

    def test_small_values(self):
        from app.services.impostos_service import ImpostosService

        result = ImpostosService.calcular_cota_unica(0.01, 50.0)

        assert result == 0.01  # round(0.005, 2) = 0.01

    def test_large_values(self):
        from app.services.impostos_service import ImpostosService

        result = ImpostosService.calcular_cota_unica(1_000_000.0, 3.0)

        assert result == 970_000.0


# ---------------------------------------------------------------------------
# check_vencidos (async, DB-backed)
# ---------------------------------------------------------------------------

class TestCheckVencidos:

    @pytest.mark.asyncio
    async def test_no_overdue_returns_zero(self):
        db = MockSupabaseClient(data=[])

        from app.services.impostos_service import ImpostosService
        svc = ImpostosService(db, "u1")

        count = await svc.check_vencidos()

        assert count == 0

    @pytest.mark.asyncio
    async def test_overdue_records_counted(self):
        # Production runs TWO SELECTs (status=pendente + status=parcial)
        # each with `.lt("data_vencimento", today)`. Pre-MOCK-SELECT-PREDICATE-
        # FIX both queries returned the same 2 rows (predicates tracked-but-
        # unevaluated), totalling 4. Post-fix each predicate must literally
        # match — seed 2 pendente + 2 parcial rows (4 distinct), each with a
        # past `data_vencimento` so `.lt("data_vencimento", today)` passes.
        past = "2000-01-01"
        db = MockSupabaseClient(data=[
            {"id": "i1", "status": "pendente", "data_vencimento": past},
            {"id": "i2", "status": "pendente", "data_vencimento": past},
            {"id": "i3", "status": "parcial", "data_vencimento": past},
            {"id": "i4", "status": "parcial", "data_vencimento": past},
        ])

        from app.services.impostos_service import ImpostosService
        svc = ImpostosService(db, "u1")

        count = await svc.check_vencidos()

        # 2 pendente + 2 parcial overdue rows, all past data_vencimento.
        assert count == 4
