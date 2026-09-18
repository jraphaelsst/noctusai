"""Structural tests for `135_matricula_retencao_fonte.sql`.

Parse-based, same shape as `test_migration_111_matricula_lgpd_followups.py` —
the migration is a FILE, not an applied change, and its trigger body is SQL
there is no dev database to run. These assert the DECLARED shape: that
source retention + supersede-not-rewrite landed as constraints and a real
trigger extension, not as comments.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "135_matricula_retencao_fonte.sql"
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
    statements = pglast.parse_sql(sql)
    assert len(statements) > 0


def test_is_idempotent(code: str):
    assert "CREATE TABLE IF NOT EXISTS" in code
    assert "ADD COLUMN IF NOT EXISTS" in code
    assert "DROP CONSTRAINT IF EXISTS" in code
    assert "CREATE INDEX IF NOT EXISTS" in code
    assert "CREATE OR REPLACE FUNCTION" in code


# ─── 1. the retained-file table ─────────────────────────────────────────


def test_matricula_extracao_arquivos_exists_with_the_documentostore_shape(flat: str):
    assert "CREATE TABLE IF NOT EXISTS social_wiring.matricula_extracao_arquivos" in flat
    for coluna in (
        "org_id",
        "storage_path",
        "nome_original",
        "mime_type",
        "tamanho_bytes",
        "tipo_documento",
        "enviado_por",
        "deleted_at",
        "delete_motivo",
        "retencao_ate",
    ):
        assert coluna in flat


def test_tipo_documento_is_constrained_to_matricula(flat: str):
    assert "CHECK (tipo_documento = 'matricula')" in flat


def test_authenticated_gets_select_only_service_role_gets_all(flat: str):
    assert 'FOR SELECT TO authenticated' in flat
    assert (
        'CREATE POLICY "matricula_extracao_arquivos_service_role" '
        "ON social_wiring.matricula_extracao_arquivos "
        "FOR ALL TO service_role USING (true) WITH CHECK (true);" in flat
    )


# ─── 2. matricula_extracoes: the retained-file pointer + supersede pointer ─


def test_arquivo_origem_id_and_substituida_por_and_flag_are_added(flat: str):
    assert "ADD COLUMN IF NOT EXISTS arquivo_origem_id" in flat
    assert "ADD COLUMN IF NOT EXISTS substituida_por" in flat
    assert (
        "ADD COLUMN IF NOT EXISTS possui_marcacao_bruta BOOLEAN NOT NULL DEFAULT false"
        in flat
    )


def test_arquivo_origem_id_fks_the_new_table(flat: str):
    assert (
        "FOREIGN KEY (arquivo_origem_id) "
        "REFERENCES social_wiring.matricula_extracao_arquivos (id) ON DELETE SET NULL"
        in flat
    )


def test_substituida_por_is_self_referential_set_null(flat: str):
    assert (
        "FOREIGN KEY (substituida_por) "
        "REFERENCES social_wiring.matricula_extracoes (id) ON DELETE SET NULL" in flat
    )


def test_a_row_holds_at_most_one_kind_of_retained_source(flat: str):
    assert "matricula_extracoes_uma_fonte" in flat
    assert (
        "CHECK (imovel_documento_id IS NULL OR arquivo_origem_id IS NULL)" in flat
    )


def test_only_a_concluded_row_can_be_superseded(flat: str):
    assert "matricula_extracoes_substituida_exige_concluida" in flat
    assert "CHECK (substituida_por IS NULL OR status = 'concluida')" in flat


# ─── 3. the write-once trigger is EXTENDED, never weakened ─────────────────


def test_the_original_three_checks_are_still_present_verbatim(flat: str):
    """135 replaces the function body — this pins that 111's three checks
    survived the replace byte-for-byte in their conditions."""
    assert "OLD.status = 'concluida'" in flat
    assert "NEW.texto_extraido IS DISTINCT FROM OLD.texto_extraido" in flat
    assert "AND NEW.texto_extraido IS NOT NULL THEN" in flat
    assert "OLD.codigo IS NOT NULL" in flat
    assert "NEW.codigo IS DISTINCT FROM OLD.codigo" in flat
    assert "OLD.imovel_documento_id IS NOT NULL" in flat
    assert (
        "NEW.imovel_documento_id IS DISTINCT FROM OLD.imovel_documento_id" in flat
    )


def test_arquivo_origem_id_is_frozen_once_set(flat: str):
    assert "OLD.arquivo_origem_id IS NOT NULL" in flat
    assert (
        "NEW.arquivo_origem_id IS DISTINCT FROM OLD.arquivo_origem_id" in flat
    )


def test_substituida_por_is_frozen_once_set(flat: str):
    """The one legitimate transition is NULL -> a new id; re-pointing an
    already-superseded row again is refused, not silently allowed."""
    assert "OLD.substituida_por IS NOT NULL" in flat
    assert "NEW.substituida_por IS DISTINCT FROM OLD.substituida_por" in flat


def test_no_role_is_exempted_from_the_extended_guard(code: str):
    trecho = code[code.index("matricula_extracoes_protege_concluida") :]
    assert "TO authenticated" not in trecho
    assert "TO service_role" not in trecho


def test_the_trigger_itself_is_not_redeclared(flat: str):
    """135 keeps the SAME trigger (function replace only) — no second
    `CREATE TRIGGER protege_concluida_matricula_extracoes` competing with
    111's, and no DROP TRIGGER here (nothing to re-attach a function to
    that is already attached)."""
    assert flat.count("CREATE TRIGGER protege_concluida_matricula_extracoes") == 0
    assert flat.count("DROP TRIGGER") == 0


# ─── 4. backfill ────────────────────────────────────────────────────────


def test_backfill_flags_concluded_rows_with_raw_markers_only(flat: str):
    assert "UPDATE social_wiring.matricula_extracoes" in flat
    assert "SET possui_marcacao_bruta = true" in flat
    assert "WHERE status = 'concluida'" in flat
    assert "texto_extraido LIKE '%**%'" in flat
