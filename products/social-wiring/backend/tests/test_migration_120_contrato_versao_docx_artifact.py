"""Structural tests for `120_contrato_versao_docx_artifact.sql`.

Parse-based, like `test_migration_112_contrato_versao_contexto_gerado.sql`'s
sibling `atendimento_contrato_versoes` migrations before it — the migration is
a FILE, not an applied change, and there is no dev database to run it
against. These pin: the two new columns are nullable and additive, the
per-origem CHECK matches the docx-only-for-gerado rule, the CHECK ships
`NOT VALID` and is never subsequently validated (pre-existing gerado rows
predate this feature and have no `.docx` to backfill from), and nothing is
dropped.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "120_contrato_versao_docx_artifact.sql"
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
    assert "SET search_path = social_wiring, public;" in flat


def test_is_forward_only(code: str):
    upper = code.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE"):
        assert forbidden not in upper


def test_adds_nullable_sibling_columns(flat: str):
    assert (
        "ADD COLUMN IF NOT EXISTS docx_storage_path TEXT" in flat
        or "ADD COLUMN IF NOT EXISTS docx_storage_path  TEXT" in flat
    )
    assert "docx_tamanho_bytes BIGINT" in flat
    # Neither column carries NOT NULL — an upload row must be able to leave
    # both null.
    assert "docx_storage_path TEXT NOT NULL" not in flat
    assert "docx_storage_path  TEXT NOT NULL" not in flat


def test_per_origem_check_requires_docx_only_for_gerado(flat: str):
    assert (
        "(origem = 'gerado' AND docx_storage_path IS NOT NULL "
        "AND docx_tamanho_bytes IS NOT NULL)"
    ) in flat
    assert (
        "(origem = 'upload' AND docx_storage_path IS NULL "
        "AND docx_tamanho_bytes IS NULL)"
    ) in flat


def test_check_is_not_valid_and_never_subsequently_validated(flat: str):
    """NOT VALID grandfathers pre-existing gerado rows (no .docx to backfill
    from — contract §5 discarded it before this migration). A later
    `VALIDATE CONSTRAINT` on this specific constraint would defeat that."""
    assert "NOT VALID" in flat
    assert (
        "VALIDATE CONSTRAINT atendimento_contrato_versoes_docx_por_origem"
        not in flat
    )


def test_targets_the_contrato_versoes_table(flat: str):
    assert "ALTER TABLE social_wiring.atendimento_contrato_versoes" in flat
