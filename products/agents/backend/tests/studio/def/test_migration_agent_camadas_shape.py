"""agent_camadas (073): template flag + parent link + the publish-time parent pin, every 072 publish gate kept."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

MIGS = Path(__file__).resolve().parents[3] / "migrations"
SQL = migration_sql(MIGS, "agent_camadas")
PUBLISH_ANTES = migration_sql(MIGS, "eval_consolidacao")


def test_adds_template_flag_parent_link_and_version_pin():
    assert "ADD COLUMN IF NOT EXISTS modelo BOOLEAN NOT NULL DEFAULT FALSE" in SQL
    assert "ADD COLUMN IF NOT EXISTS pai_agent_id UUID NULL REFERENCES agents.agents(id) ON DELETE RESTRICT" in SQL
    assert "ADD COLUMN IF NOT EXISTS pai_versao_id UUID NULL REFERENCES agents.agent_versions(id) ON DELETE RESTRICT" in SQL


def test_publish_signature_is_replaced_not_overloaded():
    assert "DROP FUNCTION IF EXISTS agents.publish_agent_version(UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, JSONB);" in SQL
    assert "GRANT EXECUTE ON FUNCTION agents.publish_agent_version(UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, JSONB, UUID) TO service_role;" in SQL


def test_publish_refuses_a_missing_or_moved_parent_pin():
    for code in ("pai_nao_publicado", "pai_desatualizado", "pai_invalido"):
        assert f"RAISE EXCEPTION '{code}'" in SQL
    assert "pai_versao_id = p_pai_versao_id" in SQL


def test_every_072_publish_gate_is_kept():
    for gate in ("'draft_changed'", "'mecanismo_required'", "'eval_required'", "eval_run_cobre_casos", "'invalid_payload'"):
        assert SQL.count(gate) >= PUBLISH_ANTES.split("CREATE OR REPLACE FUNCTION agents.publish_agent_version(")[1].count(gate) >= 1, gate
