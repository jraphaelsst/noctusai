"""
Unit tests for FinanceiroService — summaries, cash flow aggregation, overdue detection.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

from noctusai_lib.primitives.timeutil import current_month_ref, today_utc

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Relative date helpers (avoid hardcoded dates that break over time).
# Use UTC clock to match production — `date.today()` (local) drifts across
# UTC midnight and breaks tests at the day boundary.
# ---------------------------------------------------------------------------
_TODAY = today_utc()
yesterday = (_TODAY - timedelta(days=1)).isoformat()
two_days_ago = (_TODAY - timedelta(days=2)).isoformat()
last_week = (_TODAY - timedelta(days=7)).isoformat()
tomorrow = (_TODAY + timedelta(days=1)).isoformat()
next_week = (_TODAY + timedelta(days=7)).isoformat()
this_month = current_month_ref()
last_month = (_TODAY.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


# ---------------------------------------------------------------------------
# get_resumo
# ---------------------------------------------------------------------------

class TestGetResumo:

    def _make_service(self):
        db = MockSupabaseClient()
        from app.services.financeiro_service import FinanceiroService
        return FinanceiroService(db, "user-1")

    def test_basic_receitas_despesas(self):
        svc = self._make_service()
        lancamentos = [
            {"tipo": "receita", "status": "pago", "valor": 3000.0},
            {"tipo": "receita", "status": "pago", "valor": 2000.0},
            {"tipo": "despesa", "status": "pago", "valor": 1000.0},
        ]
        result = svc.get_resumo(lancamentos)

        assert result["receitas"] == 5000.0
        assert result["despesas"] == 1000.0
        assert result["saldo"] == 4000.0
        assert result["atrasados"] == 0

    def test_atrasados_count(self):
        svc = self._make_service()
        lancamentos = [
            {"tipo": "receita", "status": "atrasado", "valor": 1500.0},
            {"tipo": "despesa", "status": "atrasado", "valor": 500.0},
            {"tipo": "receita", "status": "pago", "valor": 2000.0},
        ]
        result = svc.get_resumo(lancamentos)

        assert result["atrasados"] == 2
        # Atrasados are not counted as paid receitas/despesas
        assert result["receitas"] == 2000.0
        assert result["despesas"] == 0.0

    def test_empty_lancamentos(self):
        svc = self._make_service()
        result = svc.get_resumo([])

        assert result["receitas"] == 0.0
        assert result["despesas"] == 0.0
        assert result["saldo"] == 0.0
        assert result["atrasados"] == 0

    def test_pendente_not_counted_as_paid(self):
        """Pending transactions should not add to receitas or despesas."""
        svc = self._make_service()
        lancamentos = [
            {"tipo": "receita", "status": "pendente", "valor": 5000.0},
            {"tipo": "despesa", "status": "pendente", "valor": 2000.0},
        ]
        result = svc.get_resumo(lancamentos)

        assert result["receitas"] == 0.0
        assert result["despesas"] == 0.0
        assert result["saldo"] == 0.0

    def test_missing_valor_defaults_to_zero(self):
        svc = self._make_service()
        lancamentos = [
            {"tipo": "receita", "status": "pago"},
        ]
        result = svc.get_resumo(lancamentos)

        assert result["receitas"] == 0.0

    def test_mixed_statuses(self):
        """Only 'pago' contributes to receitas/despesas; 'atrasado' adds to count."""
        svc = self._make_service()
        lancamentos = [
            {"tipo": "receita", "status": "pago", "valor": 1000.0},
            {"tipo": "receita", "status": "pendente", "valor": 2000.0},
            {"tipo": "receita", "status": "atrasado", "valor": 3000.0},
            {"tipo": "despesa", "status": "pago", "valor": 500.0},
            {"tipo": "despesa", "status": "atrasado", "valor": 750.0},
        ]
        result = svc.get_resumo(lancamentos)

        assert result["receitas"] == 1000.0
        assert result["despesas"] == 500.0
        assert result["saldo"] == 500.0
        assert result["atrasados"] == 2


# ---------------------------------------------------------------------------
# get_fluxo_caixa
# ---------------------------------------------------------------------------

class TestGetFluxoCaixa:

    def _make_service(self):
        db = MockSupabaseClient()
        from app.services.financeiro_service import FinanceiroService
        return FinanceiroService(db, "user-1")

    def test_groups_by_month(self):
        svc = self._make_service()
        lancamentos = [
            {"tipo": "receita", "valor": 1000.0, "data_vencimento": "2026-01-15"},
            {"tipo": "receita", "valor": 2000.0, "data_vencimento": "2026-01-20"},
            {"tipo": "despesa", "valor": 500.0, "data_vencimento": "2026-02-10"},
        ]
        result = svc.get_fluxo_caixa(lancamentos)

        assert len(result) == 2
        assert result[0]["mes"] == "2026-01"
        assert result[0]["receitas"] == 3000.0
        assert result[0]["despesas"] == 0.0
        assert result[0]["saldo"] == 3000.0
        assert result[1]["mes"] == "2026-02"
        assert result[1]["receitas"] == 0.0
        assert result[1]["despesas"] == 500.0
        assert result[1]["saldo"] == -500.0

    def test_prefers_data_pagamento(self):
        """When data_pagamento is present, it should be used over data_vencimento."""
        svc = self._make_service()
        lancamentos = [
            {
                "tipo": "receita",
                "valor": 1000.0,
                "data_vencimento": "2026-01-15",
                "data_pagamento": "2026-02-01",
            },
        ]
        result = svc.get_fluxo_caixa(lancamentos)

        assert len(result) == 1
        assert result[0]["mes"] == "2026-02"

    def test_empty_lancamentos(self):
        svc = self._make_service()
        result = svc.get_fluxo_caixa([])

        assert result == []

    def test_no_date_skipped(self):
        """Lancamentos without any date should be skipped."""
        svc = self._make_service()
        lancamentos = [
            {"tipo": "receita", "valor": 1000.0},
            {"tipo": "despesa", "valor": 500.0, "data_vencimento": "2026-03-01"},
        ]
        result = svc.get_fluxo_caixa(lancamentos)

        assert len(result) == 1
        assert result[0]["mes"] == "2026-03"

    def test_sorted_by_month_ascending(self):
        svc = self._make_service()
        lancamentos = [
            {"tipo": "despesa", "valor": 200.0, "data_vencimento": "2026-03-01"},
            {"tipo": "receita", "valor": 100.0, "data_vencimento": "2026-01-01"},
            {"tipo": "receita", "valor": 300.0, "data_vencimento": "2026-02-01"},
        ]
        result = svc.get_fluxo_caixa(lancamentos)

        months = [r["mes"] for r in result]
        assert months == ["2026-01", "2026-02", "2026-03"]

    def test_saldo_calculation(self):
        svc = self._make_service()
        lancamentos = [
            {"tipo": "receita", "valor": 5000.0, "data_vencimento": "2026-06-01"},
            {"tipo": "despesa", "valor": 3000.0, "data_vencimento": "2026-06-15"},
            {"tipo": "despesa", "valor": 1000.0, "data_vencimento": "2026-06-20"},
        ]
        result = svc.get_fluxo_caixa(lancamentos)

        assert len(result) == 1
        assert result[0]["saldo"] == 1000.0


# ---------------------------------------------------------------------------
# check_overdue
# ---------------------------------------------------------------------------

class TestCheckOverdue:

    def _make_service(self):
        db = MockSupabaseClient()
        from app.services.financeiro_service import FinanceiroService
        return FinanceiroService(db, "user-1")

    def test_detects_overdue(self):
        svc = self._make_service()
        lancamentos = [
            {"id": "l1", "status": "pendente", "data_vencimento": yesterday},
            {"id": "l2", "status": "pendente", "data_vencimento": two_days_ago},
        ]
        result = svc.check_overdue(lancamentos)

        assert "l1" in result
        assert "l2" in result
        assert len(result) == 2

    def test_future_not_overdue(self):
        svc = self._make_service()
        lancamentos = [
            {"id": "l1", "status": "pendente", "data_vencimento": tomorrow},
            {"id": "l2", "status": "pendente", "data_vencimento": next_week},
        ]
        result = svc.check_overdue(lancamentos)

        assert result == []

    def test_only_pendente_checked(self):
        """Paid or already-overdue entries should NOT be returned."""
        svc = self._make_service()
        lancamentos = [
            {"id": "l1", "status": "pago", "data_vencimento": yesterday},
            {"id": "l2", "status": "atrasado", "data_vencimento": two_days_ago},
            {"id": "l3", "status": "pendente", "data_vencimento": yesterday},
        ]
        result = svc.check_overdue(lancamentos)

        assert result == ["l3"]

    def test_empty_lancamentos(self):
        svc = self._make_service()
        result = svc.check_overdue([])
        assert result == []

    def test_no_vencimento_skipped(self):
        svc = self._make_service()
        lancamentos = [
            {"id": "l1", "status": "pendente"},
            {"id": "l2", "status": "pendente", "data_vencimento": ""},
        ]
        result = svc.check_overdue(lancamentos)
        assert result == []

    def test_mix_overdue_and_future(self):
        svc = self._make_service()
        lancamentos = [
            {"id": "l1", "status": "pendente", "data_vencimento": last_week},
            {"id": "l2", "status": "pendente", "data_vencimento": tomorrow},
            {"id": "l3", "status": "pendente", "data_vencimento": two_days_ago},
        ]
        result = svc.check_overdue(lancamentos)

        assert len(result) == 2
        assert "l1" in result
        assert "l3" in result


# ---------------------------------------------------------------------------
# mark_overdue (async, hits DB)
# ---------------------------------------------------------------------------

class TestMarkOverdue:

    @pytest.mark.asyncio
    async def test_marks_overdue_records(self):
        db = MockSupabaseClient()
        # Bulk update returns the updated rows
        db.set_table_data("lancamentos", [
            {"id": "l1", "status": "atrasado"},
            {"id": "l2", "status": "atrasado"},
        ])

        from app.services.financeiro_service import FinanceiroService
        svc = FinanceiroService(db, "user-1")

        count = await svc.mark_overdue()
        assert count == 2

    @pytest.mark.asyncio
    async def test_no_overdue_returns_zero(self):
        db = MockSupabaseClient(data=[])

        from app.services.financeiro_service import FinanceiroService
        svc = FinanceiroService(db, "user-1")

        count = await svc.mark_overdue()
        assert count == 0
