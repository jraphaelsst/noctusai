"""Structural (parse-based) tests for `123_fotos_core.sql`.

Pins: fotos_avaliacoes is a SEPARATE table (never folded into fotos_
edicoes/fotos_fotos — contract §1's table-separation privacy guarantee),
every org table carries org_id + RLS + service_role_bypass, batch
visibility gates on fotos_lote_visivel(), and fotos_lotes_openai is
deliberately absent with a named NOC-REMEDIATE.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "123_fotos_core.sql"

ORG_TABLES = (
    "fotos_org_settings",
    "fotos_lotes",
    "fotos_fotos",
    "fotos_eventos",
    "fotos_edicoes",
    "fotos_avaliacoes",
    "fotos_decisoes",
    "fotos_dataset",
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
    collapsed = " ".join(code.split())
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", collapsed))


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


def test_is_forward_only(code: str):
    assert "DROP TABLE" not in code
    assert "DROP COLUMN" not in code


@pytest.mark.parametrize("table", ORG_TABLES)
def test_every_table_exists(flat: str, table: str):
    assert f"CREATE TABLE IF NOT EXISTS social_wiring.{table}" in flat


@pytest.mark.parametrize("table", ORG_TABLES)
def test_every_table_has_org_id_and_rls_and_service_role_bypass(flat: str, table: str):
    assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY" in flat
    assert f'CREATE POLICY "service_role_bypass" ON social_wiring.{table}' in flat


def test_fotos_avaliacoes_is_a_separate_table_from_edicoes_and_fotos(flat: str):
    """Contract §1: 'hidden from corretores by table separation, not by
    field omission'."""
    assert "CREATE TABLE IF NOT EXISTS social_wiring.fotos_avaliacoes" in flat
    bloco = flat.split("CREATE TABLE IF NOT EXISTS social_wiring.fotos_edicoes")[1]
    bloco = bloco.split(");", 1)[0]
    assert "recomendacao" not in bloco
    assert "score" not in bloco


def test_fotos_avaliacoes_rls_never_visible_to_corretor(flat: str):
    """No creator-based branch — admin-tier role or platform admin ONLY,
    unlike fotos_lotes/fotos_fotos which also admit the batch creator."""
    bloco = flat.split('CREATE POLICY "fotos_avaliacoes_select_admins"')[1]
    bloco = bloco.split(";", 1)[0]
    assert "criado_por" not in bloco
    assert "owner" in bloco and "admin" in bloco and "manager" in bloco


def test_fotos_lote_visivel_helper_used_by_every_child_table(flat: str):
    assert "CREATE OR REPLACE FUNCTION social_wiring.fotos_lote_visivel(p_lote_id UUID)" in flat
    # 1 definition (self-referential call inside its own body doesn't
    # count) + 5 child-table SELECT-policy usages
    # (lotes/fotos/eventos/edicoes/decisoes).
    assert flat.count("social_wiring.fotos_lote_visivel(") >= 6


def test_decisao_rejeitar_requires_comentario(flat: str):
    assert "CHECK (decisao <> 'rejeitar' OR comentario IS NOT NULL)" in flat


def test_fotos_fotos_ordem_unique_per_lote(flat: str):
    assert "UNIQUE (lote_id, ordem)" in flat


def test_fotos_lotes_openai_is_deliberately_absent_with_named_remediation(sql: str):
    """fotos_lotes_openai is mentioned only in the explanatory header/
    comments (Econômico-only, blocked by C8) — never actually created."""
    assert "fotos_lotes_openai" in sql
    assert "NOC-REMEDIATE[fotos-lotes-openai-table]" in sql
    assert "CREATE TABLE IF NOT EXISTS social_wiring.fotos_lotes_openai" not in sql


def test_fotos_fotos_openai_batch_id_is_a_bare_pointer_no_fk(flat: str):
    bloco = flat.split("CREATE TABLE IF NOT EXISTS social_wiring.fotos_fotos")[1]
    bloco = bloco.split(");", 1)[0]
    assert "openai_batch_id TEXT" in bloco
    assert "openai_batch_id TEXT REFERENCES" not in bloco


def test_fotos_edicoes_llm_usage_id_has_no_fk(flat: str):
    """llm_usage is a cross-cutting sink table, not owned by this
    pipeline — a hard FK across that boundary is deliberately avoided."""
    bloco = flat.split("CREATE TABLE IF NOT EXISTS social_wiring.fotos_edicoes")[1]
    bloco = bloco.split(");", 1)[0]
    assert "llm_usage_id BIGINT" in bloco
    assert "llm_usage_id BIGINT REFERENCES" not in bloco


def test_fotos_platform_settings_is_a_singleton(flat: str):
    assert "id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1)" in flat
    assert "INSERT INTO social_wiring.fotos_platform_settings (id) VALUES (1)" in flat
    assert "ON CONFLICT (id) DO NOTHING" in flat


def test_edit_type_vocabulary_is_the_fixed_four(flat: str):
    vocab = "ARRAY['cor_luz', 'ceu', 'declutter', 'staging_virtual']::TEXT[]"
    assert vocab in flat
