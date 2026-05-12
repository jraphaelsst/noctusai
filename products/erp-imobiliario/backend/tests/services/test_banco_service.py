"""
Unit tests for BancoService — statement import, auto-matching, reconciliation, remittance.
"""
import pytest
from unittest.mock import MagicMock

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
# importar_extrato
# ---------------------------------------------------------------------------

class TestImportarExtrato:

    def test_basic_import(self):
        db, builder = _make_db_for_insert({"id": "ext-1"})
        db._tables["extratos_bancarios"] = builder
        db._tables["movimentacoes_bancarias"] = builder

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        movimentacoes = [
            {"data": "2026-01-15", "descricao": "Aluguel", "valor": 1500.0, "tipo": "credito"},
            {"data": "2026-01-20", "descricao": "Taxa", "valor": 50.0, "tipo": "debito"},
        ]

        result = svc.importar_extrato(
            banco="Itau",
            agencia="1234",
            conta="56789-0",
            movimentacoes=movimentacoes,
            arquivo_nome="extrato_jan.ofx",
        )

        assert result["extrato_id"] == "ext-1"
        assert result["total_registros"] == 2
        assert result["periodo_inicio"] == "2026-01-15"
        assert result["periodo_fim"] == "2026-01-20"
        assert result["total_creditos"] == 1500.0
        assert result["total_debitos"] == 50.0
        assert result["saldo_periodo"] == 1450.0

    def test_single_movimentacao(self):
        db, builder = _make_db_for_insert({"id": "ext-2"})
        db._tables["extratos_bancarios"] = builder
        db._tables["movimentacoes_bancarias"] = builder

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        movimentacoes = [
            {"data": "2026-03-01", "descricao": "Deposito", "valor": 5000.0, "tipo": "credito"},
        ]

        result = svc.importar_extrato(
            banco="BB",
            agencia=None,
            conta=None,
            movimentacoes=movimentacoes,
            arquivo_nome="extrato.ofx",
        )

        assert result["total_registros"] == 1
        assert result["periodo_inicio"] == "2026-03-01"
        assert result["periodo_fim"] == "2026-03-01"
        assert result["total_creditos"] == 5000.0
        assert result["total_debitos"] == 0.0

    def test_no_extrato_record_raises(self):
        """If the extrato insert returns no data, RuntimeError should be raised.

        2026-04-29: Migrated to `set_sequential_responses` after seed-lib mock
        upgrade — `MockRequestBuilder.insert(...)` now returns the inserted row
        with auto-id by default (matches real Supabase). To simulate insert
        failure, queue an explicit empty response on the table.
        """
        db = MockSupabaseClient(data=None)
        db.set_sequential_responses("extratos_bancarios", [MockSupabaseResponse(data=[])])

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        with pytest.raises(RuntimeError, match="Falha ao criar registro de extrato"):
            svc.importar_extrato(
                banco="Itau",
                agencia="1234",
                conta="56789-0",
                movimentacoes=[{"data": "2026-01-01", "descricao": "x", "valor": 100, "tipo": "credito"}],
                arquivo_nome="test.ofx",
            )

    def test_creditos_and_debitos_calculation(self):
        db, builder = _make_db_for_insert({"id": "ext-3"})
        db._tables["extratos_bancarios"] = builder
        db._tables["movimentacoes_bancarias"] = builder

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        movimentacoes = [
            {"data": "2026-01-01", "descricao": "Aluguel 1", "valor": 2000.0, "tipo": "credito"},
            {"data": "2026-01-02", "descricao": "Aluguel 2", "valor": 3000.0, "tipo": "credito"},
            {"data": "2026-01-03", "descricao": "IPTU", "valor": 500.0, "tipo": "debito"},
            {"data": "2026-01-04", "descricao": "Manutencao", "valor": 1500.0, "tipo": "debito"},
        ]

        result = svc.importar_extrato(
            banco="Caixa",
            agencia="0001",
            conta="12345",
            movimentacoes=movimentacoes,
            arquivo_nome="extrato.ofx",
        )

        assert result["total_creditos"] == 5000.0
        assert result["total_debitos"] == 2000.0
        assert result["saldo_periodo"] == 3000.0


# ---------------------------------------------------------------------------
# get_pendentes_conciliacao
# ---------------------------------------------------------------------------

class TestGetPendentesConciliacao:

    def test_returns_list(self):
        db = MockSupabaseClient(data=[{"id": "m1", "conciliado": False}])

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        result = svc.get_pendentes_conciliacao()

        assert isinstance(result, list)

    def test_empty_returns_empty_list(self):
        db = MockSupabaseClient(data=[])

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        result = svc.get_pendentes_conciliacao()

        assert result == []


# ---------------------------------------------------------------------------
# conciliar
# ---------------------------------------------------------------------------

class TestConciliar:

    def test_movimentacao_not_found_raises(self):
        db = MockSupabaseClient(data=None)

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        with pytest.raises(ValueError, match="Movimentacao bancaria nao encontrada"):
            svc.conciliar("mov-missing", "lanc-1")

    def test_lancamento_not_found_raises(self):
        """When movimentacao exists but lancamento does not, should raise ValueError."""
        db = MockSupabaseClient()
        # movimentacoes_bancarias returns data; lancamentos returns None
        db.set_table_data("movimentacoes_bancarias", {"id": "m1", "conciliado": False})
        db.set_table_data("lancamentos", None)

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        with pytest.raises(ValueError, match="Lancamento financeiro nao encontrado"):
            svc.conciliar("m1", "lanc-missing")

    def test_successful_conciliation(self):
        db = MockSupabaseClient()
        db.set_table_data("movimentacoes_bancarias", {"id": "m1", "conciliado": False})
        db.set_table_data("lancamentos", {"id": "l1"})

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        result = svc.conciliar("m1", "l1")

        # The mock returns whichever data was set — we just verify it ran without error
        assert result is not None


# ---------------------------------------------------------------------------
# auto_conciliar
# ---------------------------------------------------------------------------

class TestAutoConciliar:

    def test_no_movimentacoes_returns_zeros(self):
        db = MockSupabaseClient(data=[])

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        result = svc.auto_conciliar("ext-1")

        assert result["total_conciliados"] == 0
        assert result["total_pendentes"] == 0

    def test_matching_logic(self):
        """When movimentacoes and lancamentos match on tipo+valor+data, they should be reconciled."""
        db = MockSupabaseClient()

        # `extrato_id` + `conciliado` required on seed: production filters by
        # `.eq("extrato_id", extrato_id).eq("conciliado", False)`. Pre-MOCK-
        # SELECT-PREDICATE-FIX predicates were tracked-but-unevaluated; once
        # SELECT obeys them, missing columns silently strip rows.
        movs = [
            {"id": "m1", "extrato_id": "ext-1", "conciliado": False, "tipo": "credito", "valor": 1000.0, "data": "2026-01-15"},
            {"id": "m2", "extrato_id": "ext-1", "conciliado": False, "tipo": "debito", "valor": 500.0, "data": "2026-01-20"},
            {"id": "m3", "extrato_id": "ext-1", "conciliado": False, "tipo": "credito", "valor": 2000.0, "data": "2026-01-25"},  # no match
        ]
        lancs = [
            {"id": "l1", "tipo": "receita", "valor": 1000.0, "data_vencimento": "2026-01-15", "status": "pendente"},
            {"id": "l2", "tipo": "despesa", "valor": 500.0, "data_vencimento": "2026-01-20", "status": "pendente"},
        ]

        db.set_table_data("movimentacoes_bancarias", movs)
        db.set_table_data("lancamentos", lancs)

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        result = svc.auto_conciliar("ext-1")

        assert result["total_conciliados"] == 2
        assert result["total_pendentes"] == 1

    def test_no_duplicate_matching(self):
        """Two movimentacoes with the same signature should not both match the same lancamento."""
        db = MockSupabaseClient()

        # `extrato_id` + `conciliado` required on seed — same MOCK-SELECT shape
        # as test_matching_logic above.
        movs = [
            {"id": "m1", "extrato_id": "ext-1", "conciliado": False, "tipo": "credito", "valor": 1000.0, "data": "2026-01-15"},
            {"id": "m2", "extrato_id": "ext-1", "conciliado": False, "tipo": "credito", "valor": 1000.0, "data": "2026-01-15"},
        ]
        lancs = [
            {"id": "l1", "tipo": "receita", "valor": 1000.0, "data_vencimento": "2026-01-15", "status": "pendente"},
        ]

        db.set_table_data("movimentacoes_bancarias", movs)
        db.set_table_data("lancamentos", lancs)

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        result = svc.auto_conciliar("ext-1")

        assert result["total_conciliados"] == 1
        assert result["total_pendentes"] == 1


# ---------------------------------------------------------------------------
# gerar_remessa
# ---------------------------------------------------------------------------

class TestGerarRemessa:

    def test_basic_remessa(self):
        db, builder = _make_db_for_insert({"id": "rem-1"})
        db._tables["remessas"] = builder

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        titulos = [
            {"valor": 1500.0, "vencimento": "2026-03-01", "sacado_nome": "Joao", "sacado_cpf": "111.111.111-11"},
            {"valor": 2500.0, "vencimento": "2026-03-15", "sacado_nome": "Maria", "sacado_cpf": "222.222.222-22"},
        ]

        result = svc.gerar_remessa(tipo="cnab240", banco="Itau", titulos=titulos)

        assert result["remessa_id"] == "rem-1"
        assert result["total_titulos"] == 2
        assert result["valor_total"] == 4000.0
        assert result["status"] == "gerado"
        assert result["tipo"] == "cnab240"
        assert "remessa_cnab240_Itau_" in result["arquivo_nome"]
        assert result["arquivo_nome"].endswith(".rem")

    def test_empty_titulos(self):
        db, builder = _make_db_for_insert({"id": "rem-2"})
        db._tables["remessas"] = builder

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        result = svc.gerar_remessa(tipo="cnab400", banco="BB", titulos=[])

        assert result["total_titulos"] == 0
        assert result["valor_total"] == 0.0

    def test_no_remessa_record_raises(self):
        """Migrated 2026-04-29: explicit insert-failure simulation via
        `set_sequential_responses` (was relying on `data=None` quirk before
        the seed-lib mock upgrade)."""
        db = MockSupabaseClient(data=None)
        db.set_sequential_responses("remessas", [MockSupabaseResponse(data=[])])

        from app.services.banco_service import BancoService
        svc = BancoService(db, "user-1")

        with pytest.raises(RuntimeError, match="Falha ao criar registro de remessa"):
            svc.gerar_remessa(
                tipo="cnab240",
                banco="Itau",
                titulos=[{"valor": 100, "vencimento": "2026-01-01", "sacado_nome": "A", "sacado_cpf": "000"}],
            )
