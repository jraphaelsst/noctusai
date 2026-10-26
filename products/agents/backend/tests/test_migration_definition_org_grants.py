"""Structural pins for 050 (org-config isolation): closed-by-default definitions, the grant allow-list, the
backfill-before-flip order and the guard refusal. Replayed on a real Postgres (twice) by the pre-commit replay."""
from __future__ import annotations

from pathlib import Path

SQL = next(Path(__file__).resolve().parents[1].joinpath("migrations").glob("050_*definition_org_grants.sql")).read_text(
    encoding="utf-8")


def test_default_is_closed():
    assert "ALTER COLUMN instanciavel SET DEFAULT FALSE" in SQL


def test_grants_table_is_service_role_only():
    assert "CREATE TABLE IF NOT EXISTS agents.definition_org_grants" in SQL
    assert "PRIMARY KEY (definition_id, org_id)" in SQL
    assert "ALTER TABLE agents.definition_org_grants ENABLE ROW LEVEL SECURITY" in SQL
    assert "REVOKE ALL ON agents.definition_org_grants FROM PUBLIC, anon, authenticated" in SQL
    assert "CREATE POLICY" not in SQL


def test_grants_are_backfilled_by_definition_id_before_the_flip_and_the_check():
    grant = SQL.index("INSERT INTO agents.definition_org_grants")
    flip = SQL.index("SET instanciavel = FALSE")
    check = SQL.index("ADD CONSTRAINT agents_product_owned_not_instanciavel")
    assert grant < flip < check
    assert "i.definition_agent_id" in SQL  # keyed by the definition pointer, not by agent key


def test_product_owned_check_is_scoped_to_definitions():
    # instances copy owner_product and carried the old TRUE default: the CHECK must not touch them
    assert "definition_scope <> 'plataforma' OR NOT (instanciavel AND owner_product IS NOT NULL)" in SQL


def test_guard_refuses_ungranted_instance():
    assert "definition_not_granted" in SQL
    assert "NOT v_def.instanciavel" in SQL and "g.org_id = NEW.org_id" in SQL
    assert "REVOKE ALL ON FUNCTION agents.guard_agent_definition_scope() FROM PUBLIC, anon, authenticated" in SQL
