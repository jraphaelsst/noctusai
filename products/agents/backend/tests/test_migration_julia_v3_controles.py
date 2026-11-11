"""Julia v3 controls migration (contract section 12.1 / 12.2): the platform switch is service-role only, the org
flag defaults to on, both writers are SECURITY DEFINER with EXECUTE revoked, and the audit CHECK admits the three
new actions (the latest-definition pin lives in ``test_migration_audit_acao_check``)."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1], "julia_v3_controles")


def test_the_platform_table_is_service_role_only_and_platform_wide():
    body = SQL[SQL.index("CREATE TABLE IF NOT EXISTS agents.plataforma_controles"):]
    body = body[: body.index(");")]
    assert "agent_key TEXT PRIMARY KEY" in body and "desligado BOOLEAN NOT NULL DEFAULT false" in body
    assert "org_id" not in body
    assert "ALTER TABLE agents.plataforma_controles ENABLE ROW LEVEL SECURITY" in SQL
    assert "REVOKE ALL ON agents.plataforma_controles FROM anon, authenticated" in SQL
    assert "TO service_role USING (true) WITH CHECK (true)" in SQL


def test_the_evaluation_mode_columns_and_writer():
    assert "ADD COLUMN IF NOT EXISTS modo_avaliacao BOOLEAN NOT NULL DEFAULT false" in SQL
    assert "ADD COLUMN IF NOT EXISTS avaliacao_usuarios UUID[] NOT NULL DEFAULT '{}'" in SQL
    assert "cardinality(v_novos) > 20" in SQL  # the cap lives in the writer
    fn = "set_agent_avaliacao(UUID, UUID, BOOLEAN, UUID[], UUID)"
    assert f"REVOKE ALL ON FUNCTION agents.{fn} FROM PUBLIC, anon, authenticated" in SQL
    assert f"GRANT EXECUTE ON FUNCTION agents.{fn} TO service_role" in SQL
    assert "avaliacao_numeros" not in SQL  # phones live in noc, never here


def test_the_writers_are_secdef_and_not_executable_by_clients():
    for fn in ("set_plataforma_controle(TEXT, BOOLEAN, TEXT, UUID)", "set_agent_fase_testes(UUID, UUID, BOOLEAN, UUID)"):
        assert f"REVOKE ALL ON FUNCTION agents.{fn} FROM PUBLIC, anon, authenticated" in SQL
        assert f"GRANT EXECUTE ON FUNCTION agents.{fn} TO service_role" in SQL
    assert SQL.count("SECURITY DEFINER") == 3


def test_the_audit_check_admits_the_new_actions():
    for acao in ("plataforma_desligada", "plataforma_religada", "fase_testes_alterada", "modo_avaliacao_alterado"):
        assert f"'{acao}'" in SQL
