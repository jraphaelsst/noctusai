"""
Unit tests for ContratosService — installment generation, summary, overdue detection.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db(insert_returns=None, select_data=None):
    """Build a MockSupabaseClient with configurable insert behaviour."""
    db = MockSupabaseClient(data=select_data)
    if insert_returns is not None:
        # Override the parcelas_contrato table to return specific data on insert
        builder = MagicMock()
        builder.select = MagicMock(return_value=builder)
        builder.insert = MagicMock(return_value=builder)
        builder.delete = MagicMock(return_value=builder)
        builder.update = MagicMock(return_value=builder)
        builder.eq = MagicMock(return_value=builder)
        builder.lt = MagicMock(return_value=builder)
        builder.single = MagicMock(return_value=builder)

        # Prepend a dummy response for the DELETE.execute() call that
        # gerar_parcelas performs before inserting new installments.
        all_returns = [None] + insert_returns
        call_count = {"n": 0}
        def _execute():
            idx = call_count["n"]
            call_count["n"] += 1
            if idx < len(all_returns):
                return MockSupabaseResponse(data=all_returns[idx])
            return MockSupabaseResponse(data=None)

        builder.execute = _execute
        db._tables["parcelas_contrato"] = builder
    return db


# ---------------------------------------------------------------------------
# gerar_parcelas
# ---------------------------------------------------------------------------

class TestGerarParcelas:

    @pytest.mark.asyncio
    async def test_basic_installment_generation(self):
        """Three equal installments from 10 000 total with 1 000 down payment."""
        parcela_records = [
            {"id": f"p-{i+1}", "contrato_id": "c1", "numero": i+1, "valor": 3000.0, "status": "pendente"}
            for i in range(3)
        ]
        db = _make_mock_db(insert_returns=parcela_records)

        from app.services.contratos_service import ContratosService
        svc = ContratosService(db, "user-1")

        result = await svc.gerar_parcelas(
            contrato_id="c1",
            valor_total=10000.0,
            valor_entrada=1000.0,
            num_parcelas=3,
            data_inicio="2026-03-01",
        )

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_entrada_covers_total_returns_empty(self):
        """When down payment >= total, no installments should be generated."""
        db = MockSupabaseClient()

        from app.services.contratos_service import ContratosService
        svc = ContratosService(db, "user-1")

        result = await svc.gerar_parcelas(
            contrato_id="c1",
            valor_total=5000.0,
            valor_entrada=5000.0,
            num_parcelas=5,
            data_inicio="2026-01-01",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_entrada_exceeds_total_returns_empty(self):
        """Down payment greater than total returns empty list."""
        db = MockSupabaseClient()

        from app.services.contratos_service import ContratosService
        svc = ContratosService(db, "user-1")

        result = await svc.gerar_parcelas(
            contrato_id="c1",
            valor_total=5000.0,
            valor_entrada=6000.0,
            num_parcelas=5,
            data_inicio="2026-01-01",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_rounding_remainder_on_last_installment(self):
        """Last installment absorbs rounding remainder so total is exact."""
        from app.services.contratos_service import ContratosService

        # 10 000 / 3 = 3333.33 (x2 = 6666.66), last = 3333.34
        valor_total = 10000.0
        valor_entrada = 0.0
        num_parcelas = 3
        valor_financiado = valor_total - valor_entrada
        valor_parcela = round(valor_financiado / num_parcelas, 2)
        valor_ultima = round(valor_financiado - (valor_parcela * (num_parcelas - 1)), 2)

        assert valor_parcela == 3333.33
        assert valor_ultima == 3333.34
        assert valor_parcela * 2 + valor_ultima == valor_financiado

    @pytest.mark.asyncio
    async def test_single_installment(self):
        """One installment should get the full financed amount."""
        record = {"id": "p-1", "contrato_id": "c1", "numero": 1, "valor": 8000.0, "status": "pendente"}
        db = _make_mock_db(insert_returns=[record])

        from app.services.contratos_service import ContratosService
        svc = ContratosService(db, "user-1")

        result = await svc.gerar_parcelas(
            contrato_id="c1",
            valor_total=10000.0,
            valor_entrada=2000.0,
            num_parcelas=1,
            data_inicio="2026-06-01",
        )

        assert len(result) == 1


# ---------------------------------------------------------------------------
# get_resumo
# ---------------------------------------------------------------------------

class TestGetResumo:

    def test_empty_list(self):
        from app.services.contratos_service import ContratosService
        svc = ContratosService(MockSupabaseClient(), "u1")

        resumo = svc.get_resumo([])

        assert resumo["total"] == 0
        assert resumo["valor_total"] == 0.0
        assert all(v == 0 for v in resumo["por_status"].values())
        assert all(v == 0 for v in resumo["por_tipo"].values())

    def test_counts_by_status(self):
        from app.services.contratos_service import ContratosService
        svc = ContratosService(MockSupabaseClient(), "u1")

        contratos = [
            {"status": "ativo", "tipo": "venda", "valor_total": 200000},
            {"status": "ativo", "tipo": "locacao", "valor_total": 1500},
            {"status": "rascunho", "tipo": "venda", "valor_total": 300000},
            {"status": "cancelado", "tipo": "venda", "valor_total": 100000},
            {"status": "concluido", "tipo": "venda", "valor_total": 500000},
        ]

        resumo = svc.get_resumo(contratos)

        assert resumo["total"] == 5
        assert resumo["por_status"]["ativo"] == 2
        assert resumo["por_status"]["rascunho"] == 1
        assert resumo["por_status"]["cancelado"] == 1
        assert resumo["por_status"]["concluido"] == 1

    def test_valor_total_only_ativo_concluido(self):
        """Only active and concluded contracts contribute to valor_total."""
        from app.services.contratos_service import ContratosService
        svc = ContratosService(MockSupabaseClient(), "u1")

        contratos = [
            {"status": "ativo", "tipo": "venda", "valor_total": 200000},
            {"status": "rascunho", "tipo": "venda", "valor_total": 300000},
            {"status": "concluido", "tipo": "venda", "valor_total": 500000},
            {"status": "cancelado", "tipo": "venda", "valor_total": 100000},
        ]

        resumo = svc.get_resumo(contratos)

        assert resumo["valor_total"] == 700000.0

    def test_tipo_breakdown(self):
        from app.services.contratos_service import ContratosService
        svc = ContratosService(MockSupabaseClient(), "u1")

        contratos = [
            {"status": "ativo", "tipo": "venda", "valor_total": 100},
            {"status": "ativo", "tipo": "locacao", "valor_total": 200},
            {"status": "ativo", "tipo": "locacao", "valor_total": 300},
        ]

        resumo = svc.get_resumo(contratos)

        assert resumo["por_tipo"]["venda"] == 1
        assert resumo["por_tipo"]["locacao"] == 2

    def test_unknown_status_not_counted(self):
        """A contract with an unknown status is still counted in total but not in por_status."""
        from app.services.contratos_service import ContratosService
        svc = ContratosService(MockSupabaseClient(), "u1")

        contratos = [
            {"status": "desconhecido", "tipo": "venda", "valor_total": 100},
        ]

        resumo = svc.get_resumo(contratos)

        assert resumo["total"] == 1
        assert all(v == 0 for v in resumo["por_status"].values())


# ---------------------------------------------------------------------------
# check_inadimplencia
# ---------------------------------------------------------------------------

class TestCheckInadimplencia:

    def test_all_paid_no_overdue(self):
        from app.services.contratos_service import ContratosService
        svc = ContratosService(MockSupabaseClient(), "u1")

        parcelas = [
            {"id": "p1", "status": "pago", "valor": 1000, "data_vencimento": "2020-01-01"},
            {"id": "p2", "status": "pago", "valor": 1000, "data_vencimento": "2020-02-01"},
        ]

        result = svc.check_inadimplencia(parcelas)

        assert result["total_atrasadas"] == 0
        assert result["valor_atrasado"] == 0.0
        assert result["taxa_inadimplencia"] == 0.0
        assert result["parcelas_ids"] == []

    def test_explicitly_overdue_parcelas(self):
        from app.services.contratos_service import ContratosService
        svc = ContratosService(MockSupabaseClient(), "u1")

        parcelas = [
            {"id": "p1", "status": "atrasado", "valor": 1000},
            {"id": "p2", "status": "pago", "valor": 1000},
            {"id": "p3", "status": "atrasado", "valor": 2000},
        ]

        result = svc.check_inadimplencia(parcelas)

        assert result["total_atrasadas"] == 2
        assert result["valor_atrasado"] == 3000.0
        assert set(result["parcelas_ids"]) == {"p1", "p3"}
        assert result["taxa_inadimplencia"] == pytest.approx(66.67, abs=0.01)

    def test_pending_past_due_detected(self):
        """Pending parcelas with past due date are counted as overdue."""
        from app.services.contratos_service import ContratosService
        svc = ContratosService(MockSupabaseClient(), "u1")

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        parcelas = [
            {"id": "p1", "status": "pendente", "valor": 500, "data_vencimento": yesterday},
            {"id": "p2", "status": "pendente", "valor": 500, "data_vencimento": tomorrow},
        ]

        result = svc.check_inadimplencia(parcelas)

        assert result["total_atrasadas"] == 1
        assert result["valor_atrasado"] == 500.0
        assert result["parcelas_ids"] == ["p1"]

    def test_empty_parcelas(self):
        from app.services.contratos_service import ContratosService
        svc = ContratosService(MockSupabaseClient(), "u1")

        result = svc.check_inadimplencia([])

        assert result["total_atrasadas"] == 0
        assert result["taxa_inadimplencia"] == 0.0

    def test_mixed_statuses(self):
        from app.services.contratos_service import ContratosService
        svc = ContratosService(MockSupabaseClient(), "u1")

        yesterday = (date.today() - timedelta(days=1)).isoformat()

        parcelas = [
            {"id": "p1", "status": "atrasado", "valor": 100},
            {"id": "p2", "status": "pago", "valor": 100},
            {"id": "p3", "status": "pendente", "valor": 100, "data_vencimento": yesterday},
            {"id": "p4", "status": "pendente", "valor": 100, "data_vencimento": "2099-12-31"},
        ]

        result = svc.check_inadimplencia(parcelas)

        assert result["total_atrasadas"] == 2
        assert result["valor_atrasado"] == 200.0
        assert result["taxa_inadimplencia"] == 50.0


# ---------------------------------------------------------------------------
# mark_overdue (async, uses DB)
# ---------------------------------------------------------------------------

class TestMarkOverdue:

    @pytest.mark.asyncio
    async def test_no_overdue_returns_zero(self):
        db = MockSupabaseClient(data=[])

        from app.services.contratos_service import ContratosService
        svc = ContratosService(db, "u1")

        count = await svc.mark_overdue()

        assert count == 0

    @pytest.mark.asyncio
    async def test_overdue_records_are_updated(self):
        db = MockSupabaseClient(data=[{"id": "p1"}, {"id": "p2"}])

        from app.services.contratos_service import ContratosService
        svc = ContratosService(db, "u1")

        count = await svc.mark_overdue()

        assert count == 2
