"""Structural tests for `*_contrato_aditivos.sql` (aditivos).

Parse-based, like the sibling contract migrations (106/120/177). These pin:
the four tables exist schema-qualified and idempotently, RLS + the two
policies on each, the never-reused ordinal/numero UNIQUE indexes, the
gerado-row completeness CHECK (PDF + docx + sha born together), the parcela
vocabulary WITHOUT permuta, and that the file is forward-only.
"""
from __future__ import annotations

from pathlib import Path
from noctusai_lib.testing.migrations import migration_path

import pytest

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "contrato_aditivos")
TABELAS = (
    "atendimento_contrato_aditivos",
    "atendimento_contrato_aditivo_parcelas",
    "atendimento_contrato_aditivo_versoes",
    "atendimento_contrato_aditivo_versao_acessos",
)


@pytest.fixture(scope="module")
def flat() -> str:
    sql = MIGRATION.read_text(encoding="utf-8")
    code = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    return " ".join(code.split())


def test_migration_parses():
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))) > 0


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


@pytest.mark.parametrize("tabela", TABELAS)
def test_each_table_is_idempotent_and_org_scoped(flat: str, tabela: str):
    assert f"CREATE TABLE IF NOT EXISTS social_wiring.{tabela} (" in flat
    assert f"ALTER TABLE social_wiring.{tabela} ENABLE ROW LEVEL SECURITY;" in flat
    assert f'CREATE POLICY "{tabela}_select_own_org"' in flat
    assert f'CREATE POLICY "{tabela}_service_role"' in flat


def test_ordinal_and_numero_are_unique_across_every_row(flat: str):
    assert "ON social_wiring.atendimento_contrato_aditivos (contrato_id, ordinal);" in flat
    assert "ON social_wiring.atendimento_contrato_aditivo_versoes (aditivo_id, numero);" in flat


def test_a_gerado_version_is_born_complete(flat: str):
    assert "AND contexto_sha256 ~ '^[0-9a-f]{64}$' AND docx_storage_path IS NOT NULL" in flat


def test_parcelas_exclude_permuta(flat: str):
    assert "CHECK (tipo IN ('sinal', 'intermediaria', 'financiamento', 'fgts', 'saldo', 'direta'))" in flat


def test_is_forward_only(flat: str):
    upper = flat.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE"):
        assert forbidden not in upper
