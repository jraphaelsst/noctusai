"""Structural pins for the llm-provider-runtime migration (Lais A1): provider column + provider-keyed
model CHECK, `runtime='llm'`, the re-declared version guard / draft copy, and the
per-org credentials table. The migration is replayed on a real Postgres (PGlite)
by the pre-commit chain replay; these keep its intent honest against the Python
allowlists."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.stores.agents import RUNTIMES
from app.stores.studio_definitions import MODELS_BY_PROVIDER, PROVIDERS

SQL = migration_sql(Path(__file__).resolve().parents[1], "llm_provider_runtime")


def _in_list(fragment: str) -> set[str]:
    return set(re.findall(r"'([^']+)'", fragment))


def test_provider_check_matches_python_providers():
    m = re.search(r"agent_versions_provider_check\s+CHECK \(provider IN \(([^)]*)\)\)", SQL)
    assert m and _in_list(m.group(1)) == set(PROVIDERS)


def test_model_check_is_provider_keyed_and_matches_python():
    block = SQL[SQL.index("ADD CONSTRAINT agent_versions_model_check"):]
    block = block[: block.index(");")]
    for provider, models in MODELS_BY_PROVIDER.items():
        m = re.search(rf"provider = '{provider}'\s+AND model IN \(([^)]*)\)", block)
        assert m and _in_list(m.group(1)) == set(models), provider


def test_runtime_check_admits_llm_and_python_runtimes_agree():
    m = re.search(r"agents_runtime_check\s+CHECK \(runtime IN \(([^)]*)\)\)", SQL)
    assert m and "llm" in _in_list(m.group(1))
    assert _in_list(m.group(1)) >= set(RUNTIMES)


def test_provider_is_a_compiled_and_frozen_setting_and_survives_a_draft_copy():
    guard = SQL[SQL.index("FUNCTION agents.guard_agent_version_immutable()"): SQL.index("FUNCTION agents.create_agent_draft")]
    assert guard.count("NEW.provider IS DISTINCT FROM OLD.provider") == 2  # draft hash-clear + published freeze
    copy = SQL[SQL.index("FUNCTION agents.create_agent_draft"):]
    assert "v_src.provider" in copy and "notas, provider, model" in copy


def test_credentials_table_is_service_role_only():
    assert "CREATE TABLE IF NOT EXISTS agents.credentials" in SQL
    assert "REVOKE ALL ON agents.credentials FROM anon, authenticated" in SQL
    assert "UNIQUE(org_id, provider)" in SQL
