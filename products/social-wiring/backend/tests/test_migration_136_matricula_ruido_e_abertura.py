"""Structural tests for `136_matricula_ruido_e_abertura.sql`.

Parse-based, same shape as `test_migration_135_matricula_retencao_fonte.py`
and `test_migration_111_matricula_lgpd_followups.py` — the migration is a
FILE, not an applied change (it is not applied to any DB by this branch),
and its trigger/function bodies are SQL there is no dev database to run.
These assert the DECLARED shape: that `ruido` landed as a shape-guarded,
write-once column and `matricula_abertura_blocos` landed with the RLS/index
discipline every other 109-derived table carries — not as comments.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "136_matricula_ruido_e_abertura.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    """SQL with comment lines stripped — prose in the header must never
    satisfy (or trip) a check about actual SQL."""
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    """`code` with runs of whitespace collapsed — the DDL aligns its column
    definitions, so a substring check must not depend on that alignment."""
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    statements = pglast.parse_sql(sql)
    assert len(statements) > 0


def test_is_idempotent(code: str):
    assert "ADD COLUMN IF NOT EXISTS" in code
    assert "CREATE TABLE IF NOT EXISTS" in code
    assert "CREATE OR REPLACE FUNCTION" in code
    assert "DROP CONSTRAINT IF EXISTS" in code
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in code
    assert "CREATE INDEX IF NOT EXISTS" in code
    assert "DROP POLICY IF EXISTS" in code


def test_not_applied_to_any_db_by_this_change(sql: str):
    """The header's own contract — a follow-up (this project's PROJECT.md,
    or `noctus.dev.migrate_product`) applies it with explicit consent."""
    assert "MIGRATION FILE ONLY" in sql
    assert "not applied to any DB by this change" in sql


# ─── 1. matricula_extracoes.ruido — page furniture as offsets ─────────────


def test_ruido_column_exists_as_jsonb_default_empty_array(flat: str):
    assert (
        "ALTER TABLE social_wiring.matricula_extracoes "
        "ADD COLUMN IF NOT EXISTS ruido JSONB NOT NULL DEFAULT '[]'::jsonb;"
        in flat
    )


def test_ruido_shape_guard_requires_start_end_kind(flat: str):
    assert "CREATE OR REPLACE FUNCTION social_wiring.matricula_ruido_valido(v JSONB)" in flat
    assert "jsonb_typeof(v) = 'array'" in flat
    assert "jsonb_typeof(e -> 'start') <> 'number'" in flat
    assert "jsonb_typeof(e -> 'end') <> 'number'" in flat
    assert "(e ->> 'end')::numeric < (e ->> 'start')::numeric" in flat
    assert "'cabecalho_pagina', 'rodape_pagina'" in flat


def test_ruido_shape_guard_is_attached_as_a_check_constraint(flat: str):
    assert "matricula_extracoes_ruido_shape" in flat
    assert (
        "CHECK (social_wiring.matricula_ruido_valido(ruido))" in flat
    )


# ─── 2. matricula_abertura_blocos — the abertura's typed sub-spans ────────


def test_abertura_blocos_table_has_the_expected_columns(flat: str):
    assert (
        "CREATE TABLE IF NOT EXISTS social_wiring.matricula_abertura_blocos" in flat
    )
    for coluna in (
        "org_id",
        "extracao_id",
        "campo",
        "char_inicio",
        "char_fim",
        "rotulo_inicio",
        "rotulo_fim",
    ):
        assert coluna in flat


def test_campo_is_constrained_to_the_four_typed_fields(flat: str):
    assert (
        "CHECK (campo IN ( 'descricao_imovel', 'cadastro_municipal', "
        "'proprietarios', 'registro_anterior' ))" in flat
    )


def test_extracao_id_cascades_unlike_the_atos_restrict(flat: str):
    """Unlike `matricula_atos` (RESTRICT — a contract selection points at an
    act), no contract selection points at a block, so this table follows the
    extraction's own lifecycle."""
    trecho = flat[flat.index("matricula_abertura_blocos (") :][:600]
    assert "REFERENCES social_wiring.matricula_extracoes (id) ON DELETE CASCADE" in trecho


def test_one_block_per_field_per_extraction_is_unique(flat: str):
    assert (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sw_matricula_abertura_blocos_campo "
        "ON social_wiring.matricula_abertura_blocos (extracao_id, campo);" in flat
    )


def test_rls_matches_every_other_109_derived_table(flat: str):
    assert "ALTER TABLE social_wiring.matricula_abertura_blocos ENABLE ROW LEVEL SECURITY;" in flat
    assert 'FOR SELECT TO authenticated' in flat
    assert (
        'CREATE POLICY "matricula_abertura_blocos_service_role" '
        "ON social_wiring.matricula_abertura_blocos "
        "FOR ALL TO service_role USING (true) WITH CHECK (true);" in flat
    )


# ─── 3. the write-once trigger is EXTENDED to `ruido`, never weakened ─────


def test_the_original_five_checks_survive_verbatim(flat: str):
    """136 replaces the function body (111/135's) — this pins that every
    earlier check survived the replace byte-for-byte in its condition."""
    assert "OLD.status = 'concluida'" in flat
    assert "NEW.texto_extraido IS DISTINCT FROM OLD.texto_extraido" in flat
    assert "OLD.codigo IS NOT NULL" in flat
    assert "NEW.codigo IS DISTINCT FROM OLD.codigo" in flat
    assert "OLD.imovel_documento_id IS NOT NULL" in flat
    assert "NEW.imovel_documento_id IS DISTINCT FROM OLD.imovel_documento_id" in flat
    assert "OLD.arquivo_origem_id IS NOT NULL" in flat
    assert "NEW.arquivo_origem_id IS DISTINCT FROM OLD.arquivo_origem_id" in flat
    assert "OLD.substituida_por IS NOT NULL" in flat
    assert "NEW.substituida_por IS DISTINCT FROM OLD.substituida_por" in flat


def test_ruido_is_frozen_once_concluida_the_same_way_texto_extraido_is(flat: str):
    """The concrete guard the brief calls for: once `status = 'concluida'`,
    a write that changes `ruido` is refused — RAISE EXCEPTION, not a
    silently-ignored column. Structural pin (no dev DB to execute the
    trigger against): asserts the exact condition exists in the function
    body, mirroring how the pre-existing checks above are pinned."""
    trecho = flat[flat.index("matricula_extracoes_protege_concluida()") :]
    assert "OLD.status = 'concluida'" in trecho
    assert "AND NEW.ruido IS DISTINCT FROM OLD.ruido THEN" in trecho
    assert "RAISE EXCEPTION" in trecho
    assert "ruido não pode ser alterado após" in trecho


def test_no_role_is_exempted_from_the_extended_guard(code: str):
    trecho = code[code.index("matricula_extracoes_protege_concluida") :]
    assert "TO authenticated" not in trecho
    assert "TO service_role" not in trecho


def test_the_trigger_itself_is_not_redeclared(flat: str):
    """136 keeps the SAME trigger (function replace only) — no second
    `CREATE TRIGGER protege_concluida_matricula_extracoes`, no DROP TRIGGER
    (nothing to re-attach a function to that is already attached)."""
    assert flat.count("CREATE TRIGGER protege_concluida_matricula_extracoes") == 0
    assert flat.count("DROP TRIGGER") == 0


def test_does_not_touch_matricula_atos(flat: str):
    """The migration header is explicit: `matricula_atos` and its
    contiguous/covers-everything invariant are untouched — only the QUOTE
    subtracts noise. Pinned structurally: no ALTER/DROP on that table here."""
    assert "ALTER TABLE social_wiring.matricula_atos" not in flat
    assert "DROP TABLE" not in flat
