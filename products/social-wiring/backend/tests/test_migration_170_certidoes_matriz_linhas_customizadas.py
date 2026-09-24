"""Structural tests for `170_certidoes_matriz_linhas_customizadas.sql`.

Parse-based, mirroring `test_migration_167_empresas_crednet_cartao_cnpj.py`'s
shape — the migration is a FILE, not an applied change. Pins: the new
table's existence, RLS (three policies, same shape migration 168's
`contrato_testemunhas` uses), the `certidao_resultados.linha_customizada_id`
FK + its pairing CHECK with `tipo='outras_custom'`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "170_certidoes_matriz_linhas_customizadas.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public" in flat


def test_creates_linhas_customizadas_table(flat: str):
    assert "CREATE TABLE IF NOT EXISTS social_wiring.certidao_matriz_linhas_customizadas" in flat
    assert "cliente_id" in flat
    assert "REFERENCES social_wiring.clientes (id) ON DELETE CASCADE" in flat
    assert "ordem" in flat
    assert "excluida_em" in flat


def test_enables_rls_and_the_three_policies(flat: str):
    assert (
        "ALTER TABLE social_wiring.certidao_matriz_linhas_customizadas "
        "ENABLE ROW LEVEL SECURITY" in flat
    )
    for policy in (
        "certidao_matriz_linhas_select_own_org",
        "certidao_matriz_linhas_write_own_org",
        "certidao_matriz_linhas_service_role",
    ):
        assert policy in flat


def test_adds_linha_customizada_fk_to_resultados(flat: str):
    assert (
        "ALTER TABLE social_wiring.certidao_resultados "
        "ADD COLUMN IF NOT EXISTS linha_customizada_id UUID" in flat
    )
    assert "REFERENCES social_wiring.certidao_matriz_linhas_customizadas (id)" in flat


def test_check_pairs_tipo_outras_custom_with_linha_customizada_id(flat: str):
    assert "certidao_resultados_linha_customizada_par" in flat
    assert "(tipo = 'outras_custom') = (linha_customizada_id IS NOT NULL)" in flat


def test_is_idempotent_shape(flat: str):
    """Every DDL statement guards against re-running — no bare CREATE/ALTER
    ADD CONSTRAINT without an existence check."""
    assert "CREATE TABLE IF NOT EXISTS" in flat
    assert "ADD COLUMN IF NOT EXISTS" in flat
    assert "DROP POLICY IF EXISTS" in flat
    assert "CREATE INDEX IF NOT EXISTS" in flat
