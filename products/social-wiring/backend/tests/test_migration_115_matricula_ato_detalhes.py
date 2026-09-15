"""Structural tests for `115_matricula_ato_detalhes.sql`.

Parse-based, like `test_migration_111_matricula_lgpd_followups.py` — the
migration is a FILE, not an applied change. These pin the DECLARED shape: the
vocabulary mirrors the seed's, the FKs are same-org composites, and the
LGPD / permuta guarantees landed as constraints rather than comments.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.integrations.documents import NATUREZAS_ATO

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "115_matricula_ato_detalhes.sql"
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


def test_is_idempotent(code: str):
    assert "CREATE TABLE IF NOT EXISTS social_wiring.matricula_ato_detalhes" in code
    assert "ADD COLUMN IF NOT EXISTS" in code
    assert "DROP CONSTRAINT IF EXISTS" in code
    assert "DROP POLICY IF EXISTS" in code
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in code


def test_natureza_check_mirrors_the_seed_vocabulary(flat: str):
    m = re.search(r"CHECK \(natureza IS NULL OR natureza IN \(([^)]*)\)\)", flat)
    assert m, "natureza CHECK missing"
    declarados = [v.strip().strip("'") for v in m.group(1).split(",")]
    assert declarados == list(NATUREZAS_ATO)


def test_every_field_has_a_confidence_column(flat: str):
    for campo in (
        "natureza", "data_registro", "valor", "transmitentes", "adquirentes",
        "credor", "instrumento", "atos_referidos",
    ):
        assert (
            f"{campo}_confianca TEXT NOT NULL DEFAULT 'nenhuma' "
            f"CHECK ({campo}_confianca IN ('alta', 'baixa', 'nenhuma'))" in flat
        ), campo


def test_one_row_per_act_and_same_org_composite_fk(flat: str):
    assert "UNIQUE (org_id, extracao_id, id)" in flat
    assert (
        "FOREIGN KEY (org_id, extracao_id, ato_id) "
        "REFERENCES social_wiring.matricula_atos (org_id, extracao_id, id) "
        "ON DELETE CASCADE" in flat
    )
    assert "ON social_wiring.matricula_ato_detalhes (ato_id)" in flat


def test_origem_and_its_confirmation_stamp(flat: str):
    assert "CHECK (origem IN ('sugestao', 'confirmado'))" in flat
    assert "CHECK ((origem = 'confirmado') = (confirmado_em IS NOT NULL))" in flat


def test_rls_matches_109(flat: str):
    assert "ALTER TABLE social_wiring.matricula_ato_detalhes ENABLE ROW LEVEL SECURITY" in flat
    assert "FOR SELECT TO authenticated USING (org_id = public.current_org_id())" in flat
    assert "FOR ALL TO service_role USING (true) WITH CHECK (true)" in flat


def test_detalhes_view_joins_the_access_log_vocabulary(flat: str):
    assert (
        "CHECK (acao IN ('view', 'download', 'delete', 'text_view', 'detalhes_view'))"
        in flat
    )


def test_imovel_dados_confirmed_wording_columns(flat: str):
    for coluna in (
        "titulo_aquisitivo_texto TEXT",
        "titulo_aquisitivo_texto_confirmado_por UUID",
        "titulo_aquisitivo_texto_confirmado_em TIMESTAMPTZ",
        "onus_credor TEXT",
        "onus_credor_confirmado_por UUID",
        "onus_credor_confirmado_em TIMESTAMPTZ",
    ):
        assert f"ADD COLUMN IF NOT EXISTS {coluna}" in flat
    assert (
        "CHECK ((titulo_aquisitivo_texto IS NULL) = "
        "(titulo_aquisitivo_texto_confirmado_em IS NULL))" in flat
    )
    assert "CHECK ((onus_credor IS NULL) = (onus_credor_confirmado_em IS NULL))" in flat


def test_selection_gains_papel_and_a_same_org_permuta_fk(flat: str):
    assert "ADD COLUMN IF NOT EXISTS papel TEXT NOT NULL DEFAULT 'objeto'" in flat
    assert "CHECK (papel IN ('objeto', 'permuta'))" in flat
    assert "CHECK ((papel = 'permuta') = (permuta_ativo_id IS NOT NULL))" in flat
    assert "ADD CONSTRAINT permuta_ativos_org_id_id_key UNIQUE (org_id, id)" in flat
    assert (
        "FOREIGN KEY (org_id, permuta_ativo_id) "
        "REFERENCES social_wiring.permuta_ativos (org_id, id) ON DELETE RESTRICT" in flat
    )


def test_ordering_is_unique_per_group_not_per_contract(flat: str):
    assert "DROP INDEX IF EXISTS social_wiring.idx_sw_contrato_matricula_atos_ordem" in flat
    assert "idx_sw_contrato_matricula_atos_grupo_ordem" in flat
    assert "papel, COALESCE(permuta_ativo_id," in flat


def test_no_sql_backfill_of_empty_suggestions(code: str):
    """The extractor is Python; an all-NULL row inserted here would claim the
    extractor found nothing. Backfill is heal-on-read in the app."""
    assert "INSERT INTO social_wiring.matricula_ato_detalhes" not in code
