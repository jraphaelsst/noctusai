"""
Real-DB verification that `016_metas_domain.sql` applied correctly.

Assumes the migration has been run on the target Supabase instance
(either via `supabase db push` or the SQL editor). Tests hit
information_schema + pg_catalog via raw SQL RPC and verify the
expected structure is present.

Skips automatically when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set.

Run: pytest tests/realdb/test_metas_realdb.py -v
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.realdb


EXPECTED_TABLES = {
    "equipes",
    "equipe_membros",
    "meta_periodos",
    "metas_empresa",
    "metas_equipe",
    "metas_configuracao",
    "regras_pontuacao",
    "meta_eventos",
    "meta_fechamentos",
}

EXPECTED_NEW_ENUMS = {
    "modalidade_evento",
    "tipo_evento_meta",
    "papel_equipe",
    "status_periodo",
}


def _exec(core_db, sql: str):
    """
    Run raw SQL via Supabase RPC. Requires a helper SQL function `exec_sql`
    in the database, or skips the test when it isn't available.
    """
    try:
        return core_db.rpc("exec_sql", {"query": sql}).execute().data
    except Exception as e:
        pytest.skip(f"exec_sql RPC unavailable or failed: {e}")


# ---------------------------------------------------------------------------
# Table presence
# ---------------------------------------------------------------------------

def test_all_metas_tables_exist(core_db):
    rows = _exec(core_db, (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'erp' AND table_name = ANY(ARRAY["
        + ",".join(f"'{t}'" for t in sorted(EXPECTED_TABLES))
        + "])"
    ))
    present = {r["table_name"] for r in (rows or [])}
    missing = EXPECTED_TABLES - present
    assert not missing, f"Missing tables in erp schema: {missing}"


# ---------------------------------------------------------------------------
# RLS enabled
# ---------------------------------------------------------------------------

def test_rls_enabled_on_all_metas_tables(core_db):
    rows = _exec(core_db, (
        "SELECT c.relname AS table_name, c.relrowsecurity AS rls "
        "FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'erp' AND c.relname = ANY(ARRAY["
        + ",".join(f"'{t}'" for t in sorted(EXPECTED_TABLES))
        + "])"
    ))
    off = [r["table_name"] for r in (rows or []) if not r.get("rls")]
    assert not off, f"RLS disabled on: {off}"


# ---------------------------------------------------------------------------
# Enum presence
# ---------------------------------------------------------------------------

def test_new_enums_created(core_db):
    rows = _exec(core_db, (
        "SELECT t.typname FROM pg_type t "
        "JOIN pg_namespace n ON n.oid = t.typnamespace "
        "WHERE n.nspname = 'erp' AND t.typtype = 'e' AND t.typname = ANY(ARRAY["
        + ",".join(f"'{e}'" for e in sorted(EXPECTED_NEW_ENUMS))
        + "])"
    ))
    present = {r["typname"] for r in (rows or [])}
    missing = EXPECTED_NEW_ENUMS - present
    assert not missing, f"Missing enum types: {missing}"


def test_categoria_meta_includes_vgv(core_db):
    rows = _exec(core_db, (
        "SELECT e.enumlabel FROM pg_enum e "
        "JOIN pg_type t ON t.oid = e.enumtypid "
        "JOIN pg_namespace n ON n.oid = t.typnamespace "
        "WHERE n.nspname = 'erp' AND t.typname = 'categoria_meta'"
    ))
    labels = {r["enumlabel"] for r in (rows or [])}
    assert "vgv" in labels, "erp.categoria_meta is missing 'vgv' value"


def test_tipo_meta_includes_quinzenal_and_trimestral(core_db):
    rows = _exec(core_db, (
        "SELECT e.enumlabel FROM pg_enum e "
        "JOIN pg_type t ON t.oid = e.enumtypid "
        "JOIN pg_namespace n ON n.oid = t.typnamespace "
        "WHERE n.nspname = 'erp' AND t.typname = 'tipo_meta'"
    ))
    labels = {r["enumlabel"] for r in (rows or [])}
    assert {"quinzenal", "trimestral"}.issubset(labels), (
        f"erp.tipo_meta missing quinzenal/trimestral, found: {labels}"
    )


# ---------------------------------------------------------------------------
# erp.metas was extended
# ---------------------------------------------------------------------------

def test_erp_metas_has_new_columns(core_db):
    rows = _exec(core_db, (
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'erp' AND table_name = 'metas' "
        "AND column_name IN ('periodo_id', 'equipe_id', 'meta_vgv', 'meta_vgv_realizado')"
    ))
    present = {r["column_name"] for r in (rows or [])}
    expected = {"periodo_id", "equipe_id", "meta_vgv", "meta_vgv_realizado"}
    assert expected.issubset(present), f"Missing erp.metas columns: {expected - present}"


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

def test_platform_default_point_rules_seeded(erp_db):
    """Default point rules live with org_id IS NULL and no period scope."""
    resp = (
        erp_db.table("regras_pontuacao")
        .select("evento_tipo, modalidade, pontos")
        .is_("org_id", "null")
        .is_("vigencia_periodo_id", "null")
        .execute()
    )
    rules = {(r["evento_tipo"], r["modalidade"]): float(r["pontos"]) for r in (resp.data or [])}
    # Core expectations — adding new rules should update this mapping in lockstep
    expected = {
        ("captacao", "padrao"): 1.0,
        ("captacao", "compartilhada"): 0.5,
        ("captacao", "exclusividade"): 2.0,
        ("visita", "padrao"): 1.0,
        ("venda", "padrao"): 50.0,
        ("venda", "compartilhada"): 25.0,
        ("venda", "exclusividade"): 125.0,
        ("locacao", "padrao"): 5.0,
        ("reuniao", "padrao"): 1.0,
    }
    for key, pts in expected.items():
        assert rules.get(key) == pts, f"Seed rule {key} expected {pts}, got {rules.get(key)}"


# ---------------------------------------------------------------------------
# Default scoring config shape
# ---------------------------------------------------------------------------

def test_metas_configuracao_vgv_default_is_sensible(core_db):
    rows = _exec(core_db, (
        "SELECT column_name, column_default FROM information_schema.columns "
        "WHERE table_schema = 'erp' AND table_name = 'metas_configuracao'"
    ))
    defaults = {r["column_name"]: r.get("column_default") for r in (rows or [])}
    assert "10000" in str(defaults.get("vgv_por_ponto", "")), (
        f"Default vgv_por_ponto should be 10000, got: {defaults.get('vgv_por_ponto')}"
    )
    assert "unificado" in str(defaults.get("metrica_ranking_padrao", "")), (
        f"Default ranking metric should be 'unificado', got: {defaults.get('metrica_ranking_padrao')}"
    )
