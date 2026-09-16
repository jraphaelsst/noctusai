"""Structural (parse-based) tests for `126_fotos_modelos.sql`.

Pins the metrics RPC's "cost per APPROVED photo, silent-zero for unknown"
contract and the notes-history append-only shape.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "126_fotos_modelos.sql"


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


def test_notas_table_is_append_only_history(flat: str):
    assert "CREATE TABLE IF NOT EXISTS social_wiring.fotos_modelos_notas" in flat
    assert "modelo_id TEXT NOT NULL" in flat
    assert "gerado_em TIMESTAMPTZ NOT NULL DEFAULT now()" in flat


def test_notas_gated_admin_tier_not_org_scoped(flat: str):
    """Model selection is a platform-wide admin surface, not per-org
    data — no org_id column, role-gated SELECT only."""
    bloco = flat.split("CREATE TABLE IF NOT EXISTS social_wiring.fotos_modelos_notas")[1]
    bloco = bloco.split(");", 1)[0]
    assert "org_id" not in bloco
    assert 'CREATE POLICY "fotos_modelos_notas_select_admins"' in flat


def test_metrics_rpc_exists_and_is_stable_security_definer(flat: str):
    assert "CREATE OR REPLACE FUNCTION social_wiring.fotos_modelo_metricas(p_modelo_id TEXT)" in flat
    assert "LANGUAGE sql STABLE SECURITY DEFINER" in flat


def test_metrics_rpc_returns_the_four_named_metrics(flat: str):
    for col in ("total_fotos", "taxa_aprovacao", "score_medio", "custo_por_foto_aprovada_usd"):
        assert col in flat


def test_cost_metric_joins_llm_usage_via_edicoes(flat: str):
    bloco = flat.split("CREATE OR REPLACE FUNCTION social_wiring.fotos_modelo_metricas")[1]
    assert "social_wiring.llm_usage u ON u.id = e.llm_usage_id" in bloco
    assert "LEFT JOIN" in bloco  # a photo with no linked llm_usage row still counts, at cost 0


def test_cost_metric_only_counts_approved_photos(flat: str):
    bloco = flat.split("CREATE OR REPLACE FUNCTION social_wiring.fotos_modelo_metricas")[1]
    assert "ud.decisao = 'aprovar'" in bloco


def test_cost_metric_never_divides_by_zero(flat: str):
    bloco = flat.split("CREATE OR REPLACE FUNCTION social_wiring.fotos_modelo_metricas")[1]
    assert "NULLIF(" in bloco
