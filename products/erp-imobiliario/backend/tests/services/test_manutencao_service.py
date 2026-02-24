"""
Unit tests for ManutencaoService — SLA/resolution time, overdue detection, summary.
"""
import pytest
from datetime import date, timedelta

from tests.conftest import MockSupabaseClient


# ---------------------------------------------------------------------------
# get_resumo
# ---------------------------------------------------------------------------

class TestGetResumo:

    def _svc(self):
        from app.services.manutencao_service import ManutencaoService
        return ManutencaoService(MockSupabaseClient(), "u1")

    def test_empty_list(self):
        svc = self._svc()
        resumo = svc.get_resumo([])

        assert resumo["por_status"]["aberto"] == 0
        assert resumo["por_status"]["concluido"] == 0
        assert resumo["tempo_medio_resolucao"] == 0
        assert resumo["atrasados"] == 0
        assert resumo["custo_total"] == 0.0

    def test_counts_by_status(self):
        svc = self._svc()

        ordens = [
            {"status": "aberto", "data_previsao": "2099-12-31"},
            {"status": "aberto", "data_previsao": "2099-12-31"},
            {"status": "em_andamento", "data_previsao": "2099-12-31"},
            {"status": "concluido", "data_abertura": "2026-01-01", "data_conclusao": "2026-01-05", "custo_real": 500},
            {"status": "cancelado"},
        ]

        resumo = svc.get_resumo(ordens)

        assert resumo["por_status"]["aberto"] == 2
        assert resumo["por_status"]["em_andamento"] == 1
        assert resumo["por_status"]["concluido"] == 1
        assert resumo["por_status"]["cancelado"] == 1

    def test_average_resolution_time(self):
        svc = self._svc()

        ordens = [
            {
                "status": "concluido",
                "data_abertura": "2026-01-01",
                "data_conclusao": "2026-01-11",  # 10 days
                "custo_real": 100,
            },
            {
                "status": "concluido",
                "data_abertura": "2026-02-01",
                "data_conclusao": "2026-02-21",  # 20 days
                "custo_real": 200,
            },
        ]

        resumo = svc.get_resumo(ordens)

        assert resumo["tempo_medio_resolucao"] == 15.0  # (10 + 20) / 2

    def test_custo_total_only_concluido(self):
        svc = self._svc()

        ordens = [
            {"status": "concluido", "custo_real": 1000, "data_abertura": "2026-01-01", "data_conclusao": "2026-01-02"},
            {"status": "concluido", "custo_real": 500, "data_abertura": "2026-01-01", "data_conclusao": "2026-01-02"},
            {"status": "aberto", "custo_real": 999, "data_previsao": "2099-12-31"},
        ]

        resumo = svc.get_resumo(ordens)

        assert resumo["custo_total"] == 1500.0

    def test_overdue_detection(self):
        svc = self._svc()

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        ordens = [
            {"status": "aberto", "data_previsao": yesterday},       # overdue
            {"status": "em_andamento", "data_previsao": yesterday},  # overdue
            {"status": "aguardando", "data_previsao": yesterday},    # overdue (in ACTIVE_STATUSES)
            {"status": "aberto", "data_previsao": tomorrow},         # not overdue
            {"status": "concluido", "data_previsao": yesterday},     # not active
        ]

        resumo = svc.get_resumo(ordens)

        assert resumo["atrasados"] == 3

    def test_concluido_without_dates_skipped_for_avg(self):
        """Completed orders missing dates should not affect tempo_medio_resolucao."""
        svc = self._svc()

        ordens = [
            {
                "status": "concluido",
                "data_abertura": "2026-01-01",
                "data_conclusao": "2026-01-06",  # 5 days
                "custo_real": 100,
            },
            {
                "status": "concluido",
                "data_abertura": None,
                "data_conclusao": None,
                "custo_real": 200,
            },
        ]

        resumo = svc.get_resumo(ordens)

        assert resumo["tempo_medio_resolucao"] == 5.0

    def test_concluido_without_custo_real(self):
        """Completed orders with custo_real=None should not add to custo_total."""
        svc = self._svc()

        ordens = [
            {"status": "concluido", "custo_real": None, "data_abertura": "2026-01-01", "data_conclusao": "2026-01-02"},
        ]

        resumo = svc.get_resumo(ordens)

        assert resumo["custo_total"] == 0.0


# ---------------------------------------------------------------------------
# check_overdue
# ---------------------------------------------------------------------------

class TestCheckOverdue:

    def _svc(self):
        from app.services.manutencao_service import ManutencaoService
        return ManutencaoService(MockSupabaseClient(), "u1")

    def test_empty_returns_empty(self):
        svc = self._svc()
        assert svc.check_overdue([]) == []

    def test_identifies_overdue_orders(self):
        svc = self._svc()

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        ordens = [
            {"id": "o1", "status": "aberto", "data_previsao": yesterday},
            {"id": "o2", "status": "em_andamento", "data_previsao": yesterday},
            {"id": "o3", "status": "aberto", "data_previsao": tomorrow},
            {"id": "o4", "status": "concluido", "data_previsao": yesterday},
            {"id": "o5", "status": "aguardando", "data_previsao": yesterday},
        ]

        result = svc.check_overdue(ordens)

        # check_overdue only checks aberto and em_andamento (not aguardando)
        assert set(result) == {"o1", "o2"}

    def test_no_data_previsao_not_overdue(self):
        svc = self._svc()

        ordens = [
            {"id": "o1", "status": "aberto", "data_previsao": ""},
            {"id": "o2", "status": "aberto"},
        ]

        result = svc.check_overdue(ordens)

        assert result == []


# ---------------------------------------------------------------------------
# mark_overdue (async, DB-backed)
# ---------------------------------------------------------------------------

class TestMarkOverdue:

    @pytest.mark.asyncio
    async def test_no_overdue_returns_zero(self):
        db = MockSupabaseClient(data=[])

        from app.services.manutencao_service import ManutencaoService
        svc = ManutencaoService(db, "u1")

        count = await svc.mark_overdue()

        assert count == 0

    @pytest.mark.asyncio
    async def test_overdue_records_are_escalated(self):
        db = MockSupabaseClient(data=[{"id": "o1"}, {"id": "o2"}, {"id": "o3"}])

        from app.services.manutencao_service import ManutencaoService
        svc = ManutencaoService(db, "u1")

        count = await svc.mark_overdue()

        assert count == 3
