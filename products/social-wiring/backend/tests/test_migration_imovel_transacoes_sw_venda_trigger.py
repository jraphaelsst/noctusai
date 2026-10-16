"""Structural tests for the `imovel_transacoes_sw_venda_trigger` migration.

Behaviour (a won deal inserts one row, an open deal none, a human-decided row is
never rewritten) is the PGlite replay; these pin the contract the replay cannot
read: which events fire, the won-deal predicate, the never-overwrite guard and
the security posture.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "imovel_transacoes_sw_venda_trigger")

FUNCTIONS = [
    ("sincronizar_transacao_sw", "UUID", "VOID"),
    ("registrar_transacao_sw_atendimento", "", "TRIGGER"),
    ("registrar_transacao_sw_negociacao", "", "TRIGGER"),
]


@pytest.fixture(scope="module")
def code() -> str:
    return "\n".join(ln for ln in MIGRATION.read_text().splitlines() if not ln.strip().startswith("--"))


class TestWonDealPredicate:
    def test_same_sale_definition_as_266_and_081(self, code: str):
        for clause in (
            "a.status = 'aceita'",
            "a.closed_at IS NOT NULL",
            "n.valor_negociado IS NOT NULL",
            "n.valor_negociado > 0",
        ):
            assert clause in code, clause

    def test_code_decides_initial_status(self, code: str):
        assert "CASE WHEN n.imovel_codigo IS NULL THEN 'pendente' ELSE 'confirmado' END" in code


class TestTriggers:
    def test_fires_when_the_deal_becomes_won(self, code: str):
        m = re.search(
            r"AFTER UPDATE OF status, closed_at ON social_wiring\.atendimentos\s+"
            r"FOR EACH ROW\s+WHEN \((.*?)\)\s+EXECUTE",
            code,
            re.S,
        )
        assert m, "atendimentos trigger must be column-scoped with a WHEN clause"
        when = m.group(1)
        assert "NEW.status = 'aceita' AND NEW.closed_at IS NOT NULL" in when
        assert "OLD.status    IS DISTINCT FROM NEW.status" in when

    def test_fires_when_a_negociacao_is_typed_or_corrected(self, code: str):
        assert re.search(r"AFTER INSERT ON social_wiring\.atendimento_negociacao", code)
        m = re.search(
            r"AFTER UPDATE OF valor_negociado, imovel_codigo, financiamento, fgts\s+"
            r"ON social_wiring\.atendimento_negociacao\s+FOR EACH ROW\s+WHEN \((.*?)\)\s+EXECUTE",
            code,
            re.S,
        )
        assert m, "negociacao UPDATE trigger must be column-scoped with a WHEN clause"
        for col in ("valor_negociado", "imovel_codigo", "financiamento", "fgts"):
            assert re.search(rf"OLD\.{col}\s+IS DISTINCT FROM NEW\.{col}", m.group(1)), col


class TestNeverOverwritesAHumanDecision:
    def test_conflict_refreshes_only_undecided_rows(self, code: str):
        m = re.search(r"ON CONFLICT \(org_id, fonte, fonte_ref\) DO UPDATE(.*?);", code, re.S)
        assert m, "the rule must be an upsert on the 266 unique key"
        assert "WHERE t.confirmado_por IS NULL" in m.group(1)
        assert "t.vinculo_status IN ('pendente', 'confirmado')" in m.group(1)

    def test_no_delete(self, code: str):
        assert not re.search(r"\bDELETE\b", code)


class TestSecurity:
    @pytest.mark.parametrize("fn,args,returns", FUNCTIONS)
    def test_security_definer_with_pinned_path_and_revoked_execute(self, code: str, fn, args, returns):
        sig = rf"social_wiring\.{fn}\((?:p_atendimento_id )?{args}\)"
        assert re.search(rf"FUNCTION {sig}\s+RETURNS {returns}\s+LANGUAGE plpgsql\s+SECURITY DEFINER\s+SET search_path", code)
        assert re.search(rf"REVOKE EXECUTE ON FUNCTION social_wiring\.{fn}\({args}\) FROM PUBLIC, anon, authenticated", code)


class TestCatchUp:
    def test_replays_every_won_deal(self, code: str):
        assert re.search(
            r"SELECT social_wiring\.sincronizar_transacao_sw\(a\.id\)\s+FROM social_wiring\.atendimentos a\s+"
            r"WHERE a\.status = 'aceita'\s+AND a\.closed_at IS NOT NULL",
            code,
        )
