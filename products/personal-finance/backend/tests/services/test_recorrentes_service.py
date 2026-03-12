"""Unit tests for RecorrentesService — recurring execution and date calculation."""
import pytest
from datetime import date, timedelta
from tests.conftest import MockSupabaseClient


ORG_ID = "test-org-123"

yesterday = (date.today() - timedelta(days=1)).isoformat()
tomorrow = (date.today() + timedelta(days=1)).isoformat()
next_month = (date.today() + timedelta(days=35)).isoformat()


def make_service(mock_sb=None):
    from app.services.recorrentes_service import RecorrentesService
    sb = mock_sb or MockSupabaseClient()
    return RecorrentesService(sb, ORG_ID), sb


class TestCalcularProximaData:
    """Pure function tests — no mocks needed."""

    def test_semanal(self):
        from app.services.recorrentes_service import calcular_proxima_data
        result = calcular_proxima_data(date(2026, 3, 1), "semanal")
        assert result == date(2026, 3, 8)

    def test_quinzenal(self):
        from app.services.recorrentes_service import calcular_proxima_data
        result = calcular_proxima_data(date(2026, 3, 1), "quinzenal")
        assert result == date(2026, 3, 15)

    def test_mensal(self):
        from app.services.recorrentes_service import calcular_proxima_data
        result = calcular_proxima_data(date(2026, 3, 1), "mensal")
        assert result == date(2026, 4, 1)

    def test_bimestral(self):
        from app.services.recorrentes_service import calcular_proxima_data
        result = calcular_proxima_data(date(2026, 3, 1), "bimestral")
        assert result == date(2026, 5, 1)

    def test_trimestral(self):
        from app.services.recorrentes_service import calcular_proxima_data
        result = calcular_proxima_data(date(2026, 3, 1), "trimestral")
        assert result == date(2026, 6, 1)

    def test_semestral(self):
        from app.services.recorrentes_service import calcular_proxima_data
        result = calcular_proxima_data(date(2026, 3, 1), "semestral")
        assert result == date(2026, 9, 1)

    def test_anual(self):
        from app.services.recorrentes_service import calcular_proxima_data
        result = calcular_proxima_data(date(2026, 3, 1), "anual")
        assert result == date(2027, 3, 1)

    def test_end_of_month_mensal(self):
        """Jan 31 + 1 month = Feb 28 (relativedelta handles this)."""
        from app.services.recorrentes_service import calcular_proxima_data
        result = calcular_proxima_data(date(2026, 1, 31), "mensal")
        assert result == date(2026, 2, 28)

    def test_unknown_frequency_raises(self):
        from app.services.recorrentes_service import calcular_proxima_data
        with pytest.raises(ValueError, match="Frequencia desconhecida"):
            calcular_proxima_data(date(2026, 3, 1), "diario")


class TestExecutarPendentes:
    @pytest.mark.asyncio
    async def test_creates_transactions_for_pending(self):
        svc, sb = make_service()
        sb.set_table_data("recorrentes", [{
            "id": "rec-001",
            "org_id": ORG_ID,
            "nome": "Aluguel",
            "valor": 2500,
            "tipo": "despesa",
            "frequencia": "mensal",
            "conta_id": "c-1",
            "categoria_id": "cat-1",
            "proxima_data": yesterday,
            "ativo": True,
            "is_automatico": True,
            "comerciante": None,
        }])
        sb.set_table_data("transacoes", [{"id": "tx-gen-001"}])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 10000}])
        sb.set_table_data("orcamento_itens", [])
        sb.set_table_data("orcamentos", [])
        sb.set_table_data("resumos_mensais", [])

        result = await svc.executar_pendentes()
        assert result["pendentes_processadas"] == 1
        assert result["erros"] == 0

    @pytest.mark.asyncio
    async def test_skips_entries_without_conta_id(self):
        svc, sb = make_service()
        sb.set_table_data("recorrentes", [{
            "id": "rec-002",
            "org_id": ORG_ID,
            "nome": "Sem Conta",
            "valor": 100,
            "tipo": "despesa",
            "frequencia": "mensal",
            "conta_id": None,
            "categoria_id": None,
            "proxima_data": yesterday,
            "ativo": True,
            "is_automatico": True,
            "comerciante": None,
        }])

        result = await svc.executar_pendentes()
        assert result["executadas"] == 0

    @pytest.mark.asyncio
    async def test_empty_pending_list(self):
        svc, sb = make_service()
        sb.set_table_data("recorrentes", [])

        result = await svc.executar_pendentes()
        assert result["executadas"] == 0
        assert result["pendentes_processadas"] == 0
        assert result["erros"] == 0


class TestExecutarUnico:
    @pytest.mark.asyncio
    async def test_creates_single_transaction(self):
        svc, sb = make_service()
        sb.set_table_data("recorrentes", [{
            "id": "rec-001",
            "org_id": ORG_ID,
            "nome": "Internet",
            "valor": 120,
            "tipo": "despesa",
            "frequencia": "mensal",
            "conta_id": "c-1",
            "categoria_id": "cat-1",
            "proxima_data": tomorrow,
            "ativo": True,
            "is_automatico": False,
            "comerciante": "Vivo",
        }])
        sb.set_table_data("transacoes", [{"id": "tx-gen-001"}])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 5000}])
        sb.set_table_data("orcamento_itens", [])
        sb.set_table_data("orcamentos", [])
        sb.set_table_data("resumos_mensais", [])

        result = await svc.executar_unico("rec-001")
        assert result is not None

    @pytest.mark.asyncio
    async def test_nonexistent_returns_none(self):
        svc, sb = make_service()
        sb.set_table_data("recorrentes", [])

        result = await svc.executar_unico("rec-999")
        assert result is None

    @pytest.mark.asyncio
    async def test_executes_future_dates(self):
        """Manual execution should work even if proxima_data is in the future."""
        svc, sb = make_service()
        sb.set_table_data("recorrentes", [{
            "id": "rec-001",
            "org_id": ORG_ID,
            "nome": "Futuro",
            "valor": 50,
            "tipo": "despesa",
            "frequencia": "mensal",
            "conta_id": "c-1",
            "categoria_id": None,
            "proxima_data": next_month,
            "ativo": True,
            "is_automatico": False,
            "comerciante": None,
        }])
        sb.set_table_data("transacoes", [{"id": "tx-gen-001"}])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 5000}])
        sb.set_table_data("resumos_mensais", [])

        result = await svc.executar_unico("rec-001")
        assert result is not None
