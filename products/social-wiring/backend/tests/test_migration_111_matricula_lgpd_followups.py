"""Structural tests for `111_matricula_lgpd_followups.sql`.

Parse-based, like `test_migration_093_imoveis_campos_vista_completos.py` and
`test_migration_090_um_card_por_lead.py` — the migration is a FILE, not an
applied change, and its trigger body is SQL there is no dev database to run.
These assert the DECLARED shape: that the security-review follow-ups (F2,
migration 109) landed as constraints, not comments.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "111_matricula_lgpd_followups.sql"
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
    assert "DROP CONSTRAINT IF EXISTS" in code
    assert "CREATE INDEX IF NOT EXISTS" in code
    assert "DROP TRIGGER IF EXISTS" in code
    assert "CREATE OR REPLACE FUNCTION" in code


# ─── 1. text-read logging ───────────────────────────────────────────────


def test_documento_id_becomes_optional(flat: str):
    assert (
        "ALTER TABLE social_wiring.imovel_documento_acessos "
        "ALTER COLUMN documento_id DROP NOT NULL" in flat
    )


def test_extracao_id_is_added_and_fks_the_extraction(flat: str):
    assert "ADD COLUMN IF NOT EXISTS extracao_id UUID" in flat
    assert (
        "REFERENCES social_wiring.matricula_extracoes (id) ON DELETE CASCADE"
        in flat
    )


def test_exactly_one_target_is_enforced(flat: str):
    assert "imovel_documento_acessos_um_alvo" in flat
    assert (
        "CHECK ((documento_id IS NOT NULL) <> (extracao_id IS NOT NULL))" in flat
    )


def test_text_view_joins_the_acao_enum(flat: str):
    assert (
        "CHECK (acao IN ('view', 'download', 'delete', 'text_view'))" in flat
    )


# ─── 2. retention clock ─────────────────────────────────────────────────


def test_imovel_joins_the_superficie_enum(flat: str):
    assert (
        "CHECK (superficie IN ('cliente', 'atendimento', 'imovel'))" in flat
    )


def test_platform_defaults_cover_the_pdf_and_the_transcription(flat: str):
    for tipo in ("'matricula'", "'guia_iptu'", "'texto_extraido'"):
        assert f"'imovel', {tipo}," in flat, (
            f"missing a platform default row for imovel/{tipo}"
        )


def test_imovel_documentos_and_matricula_extracoes_gain_retencao_ate(code: str):
    assert (
        "ALTER TABLE social_wiring.imovel_documentos\n"
        "    ADD COLUMN IF NOT EXISTS retencao_ate DATE;" in code
    )
    assert (
        "ALTER TABLE social_wiring.matricula_extracoes\n"
        "    ADD COLUMN IF NOT EXISTS retencao_ate DATE;" in code
    )


# ─── 3. write-once guard ────────────────────────────────────────────────


def test_the_guard_freezes_texto_extraido_only_once_concluida(flat: str):
    assert "OLD.status = 'concluida'" in flat
    assert (
        "NEW.texto_extraido IS DISTINCT FROM OLD.texto_extraido" in flat
    )


def test_a_purge_to_null_is_the_one_exempted_transition(flat: str):
    """The trigger must refuse a REPLACEMENT but let a purge (-> NULL)
    through, or `estrutura_service.purgar_texto_expirado` could never run."""
    assert "AND NEW.texto_extraido IS NOT NULL THEN" in flat


def test_the_guard_freezes_codigo_and_imovel_documento_id_once_linked(flat: str):
    assert "OLD.codigo IS NOT NULL" in flat
    assert "NEW.codigo IS DISTINCT FROM OLD.codigo" in flat
    assert "OLD.imovel_documento_id IS NOT NULL" in flat
    assert (
        "NEW.imovel_documento_id IS DISTINCT FROM OLD.imovel_documento_id" in flat
    )


def test_the_trigger_fires_before_update_for_every_row(flat: str):
    assert (
        "CREATE TRIGGER protege_concluida_matricula_extracoes "
        "BEFORE UPDATE ON social_wiring.matricula_extracoes "
        "FOR EACH ROW EXECUTE FUNCTION "
        "social_wiring.matricula_extracoes_protege_concluida();" in flat
    )


def test_no_role_is_exempted(code: str):
    """No `TO authenticated` / role carve-out anywhere near the trigger —
    the guard is a table trigger, which fires for every role including
    service_role by construction; this pins that no scoping was added."""
    trecho = code[code.index("matricula_extracoes_protege_concluida") :]
    assert "TO authenticated" not in trecho
    assert "TO service_role" not in trecho


# ─── 4. composite FK (match 076) ────────────────────────────────────────


def test_imovel_documentos_gets_an_org_id_id_unique_constraint(flat: str):
    assert (
        "ADD CONSTRAINT imovel_documentos_org_id_id_key UNIQUE (org_id, id)"
        in flat
    )


def test_the_fk_is_composite_and_same_org_only(flat: str):
    assert (
        "FOREIGN KEY (org_id, imovel_documento_id) "
        "REFERENCES social_wiring.imovel_documentos (org_id, id)" in flat
    )
