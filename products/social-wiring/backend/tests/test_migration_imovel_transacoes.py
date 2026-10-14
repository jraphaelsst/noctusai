"""Structural tests for the `imovel_transacoes` migration.

Behaviour (constraints reject bad rows, backfill idempotent) is the PGlite replay;
these pin the contract the replay cannot read: the vocabulary, the confirm-needs-a-code
guard, the unique key, the security posture and the backfill's source predicate.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "imovel_transacoes")


@pytest.fixture(scope="module")
def code() -> str:
    return "\n".join(ln for ln in MIGRATION.read_text().splitlines() if not ln.strip().startswith("--"))


class TestConstraints:
    def test_vocabularies(self, code: str):
        assert "tipo IN ('venda')" in code
        assert "'contrato_d4sign', 'contrato_revisao', 'sw_negociacao', 'manual'" in code
        assert "'pendente', 'confirmado', 'rejeitado'" in code

    def test_price_positive_and_confirmed_needs_code(self, code: str):
        assert "valor_transacao > 0" in code
        assert "vinculo_status <> 'confirmado' OR codigo_canonical IS NOT NULL" in code

    def test_unique_key(self, code: str):
        assert "UNIQUE (org_id, fonte, fonte_ref)" in code

    def test_codigo_nullable_and_no_pii_columns(self, code: str):
        assert re.search(r"codigo_canonical\s+TEXT,", code)
        for pii in ("cpf", "nome", "email", "matricula", "logradouro", "rg "):
            assert not re.search(rf"^\s+{pii}\b", code, re.M | re.I), pii


class TestSecurity:
    def test_rls_org_scoped_select_and_no_authenticated_write(self, code: str):
        assert "imovel_transacoes ENABLE ROW LEVEL SECURITY" in code
        assert "FOR SELECT TO authenticated" in code
        assert "current_org_id_for('social_wiring')" in code
        assert not re.search(r"FOR (INSERT|UPDATE|DELETE|ALL) TO authenticated", code)
        assert "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON social_wiring.imovel_transacoes FROM anon, authenticated" in code

    def test_acting_audit_attached(self, code: str):
        assert "attach_acting_audit_triggers('social_wiring')" in code


class TestBackfill:
    def test_won_deals_only_and_idempotent(self, code: str):
        assert "a.status = 'aceita'" in code and "a.closed_at IS NOT NULL" in code
        assert "n.valor_negociado > 0" in code
        assert "ON CONFLICT (org_id, fonte, fonte_ref) DO NOTHING" in code

    def test_linked_deal_is_born_confirmed_unlinked_stays_pending(self, code: str):
        assert "CASE WHEN n.imovel_codigo IS NULL THEN 'pendente' ELSE 'confirmado' END" in code
