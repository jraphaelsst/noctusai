"""Structural tests for `*_clientes_por_cpf_normalizado.sql` + the contract
fake the unit tests route `clientes_por_cpf` through.

Parse-based like the sibling migration tests: the file is a FILE, not an
applied change. Pins what makes the function the ONE exact CPF lookup:
org-scoped, SECURITY INVOKER, normalised on BOTH sides (the indexed
`normalizar_documento(cpf)` expression), service_role-only.
"""
from __future__ import annotations

from pathlib import Path
from noctusai_lib.testing.migrations import migration_path

import pytest

from tests.support.rpc_fakes import clientes_por_cpf as fake_rpc

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "clientes_por_cpf_normalizado")


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    code = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_function_is_org_scoped_invoker_and_normalised_on_both_sides(flat: str):
    assert "CREATE OR REPLACE FUNCTION social_wiring.clientes_por_cpf( p_org_id UUID, p_cpfs TEXT[] )" in flat
    assert "RETURNS SETOF social_wiring.clientes" in flat
    assert "SECURITY INVOKER" in flat and "SECURITY DEFINER" not in flat
    assert "SET search_path = social_wiring, public" in flat
    assert "c.org_id = p_org_id" in flat
    # The indexed expression (idx_sw_clientes_cpf_norm) on the column side…
    assert "social_wiring.normalizar_documento(c.cpf) IN" in flat
    # …and the same normalisation applied to the keys, so any punctuation matches.
    assert "SELECT social_wiring.normalizar_documento(k) FROM unnest(p_cpfs)" in flat


def test_only_service_role_can_execute(flat: str):
    assert "REVOKE ALL ON FUNCTION social_wiring.clientes_por_cpf(UUID, TEXT[]) FROM PUBLIC" in flat
    assert "FROM anon, authenticated" in flat
    assert "GRANT EXECUTE ON FUNCTION social_wiring.clientes_por_cpf(UUID, TEXT[]) TO service_role" in flat


def test_it_touches_no_table_or_column(flat: str):
    for forbidden in ("ALTER TABLE", "CREATE TABLE", "DROP ", "INSERT ", "UPDATE ", "DELETE "):
        assert forbidden not in flat


def test_contract_fake_matches_any_punctuation_and_scopes_by_org():
    class _Client:
        def table(self, _name):
            class _Q:
                def select(self, *_a):
                    return self

                def execute(self):
                    class _R:
                        data = [
                            {"id": "2", "org_id": "o", "cpf": "529.982.247-25", "created_at": "2"},
                            {"id": "1", "org_id": "o", "cpf": "52998224725", "created_at": "1"},
                            {"id": "3", "org_id": "outra", "cpf": "52998224725", "created_at": "0"},
                            {"id": "4", "org_id": "o", "cpf": None, "created_at": "0"},
                        ]
                    return _R

            return _Q()

    rows = fake_rpc(_Client(), {"p_org_id": "o", "p_cpfs": ["529.982.247-25"]}).execute().data
    assert [r["id"] for r in rows] == ["1", "2"]
