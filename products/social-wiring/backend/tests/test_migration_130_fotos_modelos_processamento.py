"""Structural (parse-based) tests for `130_fotos_modelos_processamento.sql`.

Pins: the catalog-override tables are the seed template verbatim
(`llm_model_overrides.sql.template`, schema substituted), history is
append-only and version-unique, the processing switch defaults OFF, the
per-step model columns exist, the metrics RPC is service-role only, and the
new admin page row is insert-if-missing.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.domain.photo_editing import PlatformSettings
from noctusai_lib.domain.photo_editing.steps import STEP_SETTING

HERE = Path(__file__).resolve()
MIGRATION = HERE.parents[1] / "migrations" / "130_fotos_modelos_processamento.sql"


def _template() -> str:
    rel = Path("seed/lib/backend/noctusai_lib/integrations/llm/migrations/llm_model_overrides.sql.template")
    for parent in HERE.parents:
        if (parent / rel).is_file():
            return (parent / rel).read_text(encoding="utf-8")
    raise FileNotFoundError(rel)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


def _code(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    collapsed = " ".join(_code(sql).split())
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", collapsed))


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_is_forward_only(sql: str):
    code = _code(sql)
    assert "DROP TABLE" not in code and "DROP COLUMN" not in code


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


def test_catalog_tables_are_the_seed_template(sql: str):
    template = _code(_template()).replace("{{SCHEMA_NAME}}", "social_wiring")
    body = _code(sql)
    for statement in (s.strip() for s in template.split(";")):
        if statement:
            assert " ".join(statement.split()) in " ".join(body.split()), statement[:80]


def test_history_is_append_only_and_version_unique(flat: str):
    assert "UNIQUE (provider, kind, model_id, version)" in flat
    assert "BEFORE UPDATE OR DELETE ON social_wiring.llm_model_override_versions" in flat


def test_catalog_is_platform_admin_read_service_role_write(flat: str):
    assert flat.count("USING (public.is_platform_admin())") == 2
    assert flat.count('CREATE POLICY "service_role_bypass"') == 2
    assert "ENABLE ROW LEVEL SECURITY" in flat


def test_processing_switch_defaults_off(flat: str):
    assert "ADD COLUMN IF NOT EXISTS processamento_ativo BOOLEAN NOT NULL DEFAULT false" in flat
    assert PlatformSettings().processamento_ativo is False  # the decoder agrees


def test_step_model_columns_match_the_engine(flat: str):
    for column in STEP_SETTING.values():
        assert f"ADD COLUMN IF NOT EXISTS {column} TEXT" in flat


def test_metrics_rpc_is_service_role_only(flat: str):
    assert "REVOKE EXECUTE ON FUNCTION social_wiring.fotos_modelo_metricas(TEXT) FROM PUBLIC;" in flat
    assert "REVOKE EXECUTE ON FUNCTION social_wiring.fotos_modelo_metricas(TEXT) FROM anon, authenticated;" in flat
    assert "GRANT EXECUTE ON FUNCTION social_wiring.fotos_modelo_metricas(TEXT) TO service_role;" in flat


def test_processamento_page_row_is_insert_if_missing(flat: str):
    assert "('edicao-fotos-processamento', 'desenvolvimento'," in flat
    assert "ON CONFLICT (nome_pagina) DO NOTHING;" in flat


def test_rule_proposer_tunables_default_to_the_engine_config(flat: str):
    from noctusai_lib.domain.photo_editing import PhotoEditingConfig

    cfg = PhotoEditingConfig()
    assert (
        "ADD COLUMN IF NOT EXISTS rule_proposal_debounce_seconds INTEGER NOT NULL "
        f"DEFAULT {cfg.rule_proposal_debounce_seconds}"
    ) in flat
    assert (
        "ADD COLUMN IF NOT EXISTS max_rejections_per_proposal INTEGER NOT NULL "
        f"DEFAULT {cfg.max_rejections_per_proposal}"
    ) in flat
