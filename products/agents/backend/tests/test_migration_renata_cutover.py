"""Static pins on the Renata cutover migration. The chain replay (noctus.dev.migration_replay, pre-commit) proves
it runs on Postgres twice; this pins the security-relevant shape: both functions are SECURITY DEFINER, fixed
search_path, and EXECUTE is revoked from every client role and granted to service_role only."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1] / "migrations", "renata_cutover")
FUNCOES = ("transferir_historico_agente", "arquivar_agente_legado")


def test_definition_mode_admits_arquivado():
    assert re.search(r"definition_mode\s+IN\s*\(\s*'legacy'\s*,\s*'studio'\s*,\s*'arquivado'\s*\)", SQL)


def test_both_functions_are_security_definer_and_service_role_only():
    for f in FUNCOES:
        assert re.search(rf"CREATE OR REPLACE FUNCTION agents\.{f}\b", SQL), f
        assert re.search(rf"REVOKE ALL ON FUNCTION agents\.{f}\([^)]*\)\s+FROM PUBLIC, anon, authenticated", SQL), f
        assert re.search(rf"GRANT EXECUTE ON FUNCTION agents\.{f}\([^)]*\)\s+TO service_role", SQL), f
    assert SQL.count("SECURITY DEFINER") >= 2
    assert SQL.count("SET search_path") >= 2


def test_the_credential_key_is_renamed_only_when_the_new_one_is_absent():
    assert "academia_agent_id" in SQL and "bia_agent_id" in SQL and "NOT EXISTS" in SQL
