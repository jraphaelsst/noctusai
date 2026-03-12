"""
Unit tests for RecorrenciaService — rent generation, recurring entries, delinquency.
"""
import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

yesterday = (date.today() - timedelta(days=1)).isoformat()
two_days_ago = (date.today() - timedelta(days=2)).isoformat()
tomorrow = (date.today() + timedelta(days=1)).isoformat()
current_ref = date.today().strftime("%Y-%m")


def _make_db_for_insert(inserted_record):
    """Return a MockSupabaseClient where insert chains return *inserted_record*."""
    db = MockSupabaseClient()
    builder = MagicMock()
    builder.insert = MagicMock(return_value=builder)
    builder.select = MagicMock(return_value=builder)
    builder.single = MagicMock(return_value=builder)
    builder.eq = MagicMock(return_value=builder)
    builder.execute = MagicMock(return_value=MockSupabaseResponse(data=inserted_record))
    return db, builder


# ---------------------------------------------------------------------------
# gerar_alugueis_mes
# ---------------------------------------------------------------------------

class TestGerarAlugueisMes:

    def test_generates_for_active_contracts(self):
        """Active contracts without existing lancamentos should get new entries."""
        db = MockSupabaseClient()

        contratos = [
            {
                "id": "c-aaa-1111",
                "status": "ativo",
                "valor_aluguel": 2500.0,
                "dia_vencimento": 10,
                "cliente_id": "cli-1",
                "imovel_id": "imv-1",
            },
            {
                "id": "c-bbb-2222",
                "status": "ativo",
                "valor_aluguel": 3000.0,
                "dia_vencimento": 15,
                "cliente_id": "cli-2",
                "imovel_id": "imv-2",
            },
        ]

        # contratos_locacao returns active contracts
        db.set_table_data("contratos_locacao", contratos)

        # lancamentos: 1st call = batch-fetch existing (empty),
        # 2nd call = batch-insert all new
        db.set_sequential_responses("lancamentos", [
            MockSupabaseResponse(data=[]),   # batch-fetch existing — none found
            MockSupabaseResponse(data=[]),   # batch-insert new lancamentos
        ])

        from app.services.recorrencia_service import RecorrenciaService
        svc = RecorrenciaService(db, "org-1")

        result = svc.gerar_alugueis_mes("2026-03")

        assert result["referencia"] == "2026-03"
        assert result["gerados"] == 2
        assert result["existentes"] == 0
        assert result["erros"] == 0
        assert result["total_contratos"] == 2

    def test_skips_already_generated(self):
        """Contracts that already have a lancamento for the reference month are skipped."""
        db = MockSupabaseClient()

        contratos = [
            {
                "id": "c-aaa-1111",
                "valor_aluguel": 2500.0,
                "dia_vencimento": 10,
            },
        ]
        db.set_table_data("contratos_locacao", contratos)

        # lancamentos: batch-fetch returns existing record with matching contrato_id
        db.set_sequential_responses("lancamentos", [
            MockSupabaseResponse(data=[{"contrato_id": "c-aaa-1111"}]),
        ])

        from app.services.recorrencia_service import RecorrenciaService
        svc = RecorrenciaService(db, "org-1")

        result = svc.gerar_alugueis_mes("2026-03")

        assert result["gerados"] == 0
        assert result["existentes"] == 1

    def test_no_active_contracts(self):
        """When there are no active contracts, nothing should be generated."""
        db = MockSupabaseClient()
        db.set_table_data("contratos_locacao", [])

        from app.services.recorrencia_service import RecorrenciaService
        svc = RecorrenciaService(db, "org-1")

        result = svc.gerar_alugueis_mes("2026-03")

        assert result["gerados"] == 0
        assert result["existentes"] == 0
        assert result["total_contratos"] == 0

    def test_defaults_to_current_month(self):
        """When referencia is None, defaults to current YYYY-MM."""
        db = MockSupabaseClient()
        db.set_table_data("contratos_locacao", [])

        from app.services.recorrencia_service import RecorrenciaService
        svc = RecorrenciaService(db, "org-1")

        result = svc.gerar_alugueis_mes()

        expected_ref = datetime.now(timezone.utc).strftime("%Y-%m")
        assert result["referencia"] == expected_ref

    def test_mixed_existing_and_new(self):
        """Mix of contracts: some already generated, some new."""
        db = MockSupabaseClient()

        contratos = [
            {"id": "c-111", "valor_aluguel": 1000.0, "dia_vencimento": 5},
            {"id": "c-222", "valor_aluguel": 2000.0, "dia_vencimento": 10},
            {"id": "c-333", "valor_aluguel": 3000.0, "dia_vencimento": 15},
        ]
        db.set_table_data("contratos_locacao", contratos)

        # batch-fetch returns c-111 as already existing, then batch-insert for c-222 + c-333
        db.set_sequential_responses("lancamentos", [
            MockSupabaseResponse(data=[{"contrato_id": "c-111"}]),  # c-111 already generated
            MockSupabaseResponse(data=[]),                           # batch-insert new ones
        ])

        from app.services.recorrencia_service import RecorrenciaService
        svc = RecorrenciaService(db, "org-1")

        result = svc.gerar_alugueis_mes("2026-04")

        assert result["gerados"] == 2
        assert result["existentes"] == 1
        assert result["total_contratos"] == 3


# ---------------------------------------------------------------------------
# gerar_lancamentos_recorrentes
# ---------------------------------------------------------------------------

class TestGerarLancamentosRecorrentes:

    def test_generates_from_paid_recurring(self):
        """Paid recurring lancamentos should produce new entries for current month."""
        db = MockSupabaseClient()

        recorrentes = [
            {
                "id": "r-1",
                "tipo": "despesa",
                "categoria": "condominio",
                "descricao": "Condominio Edifício Central",
                "valor": 800.0,
                "data_vencimento": "2026-01-10",
                "status": "pago",
                "recorrente": True,
                "contrato_id": None,
                "cliente_id": None,
                "imovel_id": "imv-1",
            },
        ]

        # 1st call: fetch recurring paid lancamentos
        # 2nd call: batch-fetch existing for current month (empty = none found)
        # 3rd call: batch-insert new lancamentos
        db.set_sequential_responses("lancamentos", [
            MockSupabaseResponse(data=recorrentes),  # fetch recorrentes
            MockSupabaseResponse(data=[]),             # batch-fetch existing — not found
            MockSupabaseResponse(data=[]),             # batch-insert
        ])

        from app.services.recorrencia_service import RecorrenciaService
        svc = RecorrenciaService(db, "org-1")

        result = svc.gerar_lancamentos_recorrentes()

        assert result["gerados"] == 1
        assert result["referencia"] == current_ref

    def test_skips_already_generated(self):
        """If a recurring entry already exists for the current month, skip it."""
        db = MockSupabaseClient()

        recorrentes = [
            {
                "id": "r-1",
                "tipo": "despesa",
                "categoria": "condominio",
                "descricao": "Condominio",
                "valor": 500.0,
                "data_vencimento": "2026-02-10",
                "status": "pago",
                "recorrente": True,
            },
        ]

        db.set_sequential_responses("lancamentos", [
            MockSupabaseResponse(data=recorrentes),  # fetch recorrentes
            MockSupabaseResponse(data=[              # batch-fetch existing — found match
                {"categoria": "condominio", "descricao": "Condominio"},
            ]),
        ])

        from app.services.recorrencia_service import RecorrenciaService
        svc = RecorrenciaService(db, "org-1")

        result = svc.gerar_lancamentos_recorrentes()

        assert result["gerados"] == 0

    def test_no_recorrentes_returns_zero(self):
        """When there are no paid recurring lancamentos, nothing is generated."""
        db = MockSupabaseClient(data=[])

        from app.services.recorrencia_service import RecorrenciaService
        svc = RecorrenciaService(db, "org-1")

        result = svc.gerar_lancamentos_recorrentes()

        assert result["gerados"] == 0
        assert result["referencia"] == current_ref


# ---------------------------------------------------------------------------
# verificar_inadimplencia
# ---------------------------------------------------------------------------

class TestVerificarInadimplencia:

    def test_marks_overdue_lancamentos(self):
        """Pending lancamentos past due should be updated to 'atrasado'."""
        db = MockSupabaseClient()

        # Bulk update returns the updated rows
        db.set_table_data("lancamentos", [
            {"id": "l-1", "status": "atrasado"},
            {"id": "l-2", "status": "atrasado"},
        ])

        # parcelas_contrato: no overdue parcelas (bulk update returns empty)
        db.set_table_data("parcelas_contrato", [])

        from app.services.recorrencia_service import RecorrenciaService
        svc = RecorrenciaService(db, "org-1")

        result = svc.verificar_inadimplencia()

        assert result["lancamentos_atrasados"] == 2
        assert result["total_atualizados"] == 2

    def test_marks_overdue_parcelas(self):
        """Overdue parcelas_contrato should also be updated."""
        db = MockSupabaseClient()

        # No overdue lancamentos (bulk update returns empty)
        db.set_table_data("lancamentos", [])

        # Bulk update returns the 3 updated parcelas
        db.set_table_data("parcelas_contrato", [
            {"id": "p-1", "status": "atrasada"},
            {"id": "p-2", "status": "atrasada"},
            {"id": "p-3", "status": "atrasada"},
        ])

        from app.services.recorrencia_service import RecorrenciaService
        svc = RecorrenciaService(db, "org-1")

        result = svc.verificar_inadimplencia()

        assert result["parcelas_atrasadas"] == 3
        assert result["lancamentos_atrasados"] == 0
        assert result["total_atualizados"] == 3

    def test_no_overdue_returns_zeros(self):
        """When everything is paid/current, all counts should be zero."""
        db = MockSupabaseClient(data=[])

        from app.services.recorrencia_service import RecorrenciaService
        svc = RecorrenciaService(db, "org-1")

        result = svc.verificar_inadimplencia()

        assert result["lancamentos_atrasados"] == 0
        assert result["parcelas_atrasadas"] == 0
        assert result["total_atualizados"] == 0

    def test_combined_lancamentos_and_parcelas(self):
        """Both overdue lancamentos and parcelas are counted."""
        db = MockSupabaseClient()

        # Bulk update returns the updated lancamento
        db.set_table_data("lancamentos", [
            {"id": "l-1", "status": "atrasado"},
        ])

        # Bulk update returns the updated parcela
        db.set_table_data("parcelas_contrato", [
            {"id": "p-1", "status": "atrasada"},
        ])

        from app.services.recorrencia_service import RecorrenciaService
        svc = RecorrenciaService(db, "org-1")

        result = svc.verificar_inadimplencia()

        assert result["lancamentos_atrasados"] == 1
        assert result["parcelas_atrasadas"] == 1
        assert result["total_atualizados"] == 2
