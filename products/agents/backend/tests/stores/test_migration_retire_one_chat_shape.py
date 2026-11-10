"""075: the retired One Chat operator bot is erased from the DB -- catalogue rows, control rows, the bridge credential."""
from __future__ import annotations

import re
from pathlib import Path

from app.stores.agents import FakeAgentStore, SupabaseAgentStore
from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[2] / "migrations", "retire_one_chat")


def test_catalogue_children_go_before_the_parent():
    cap = SQL.index("DELETE FROM agents.catalogo_capacidades WHERE agent_key = 'one-chat'")
    ag = SQL.index("DELETE FROM agents.catalogo_agentes WHERE agent_key = 'one-chat'")
    assert cap < ag


def test_a_row_with_history_is_archived_not_failed():
    assert "EXCEPTION WHEN foreign_key_violation" in SQL
    assert "definition_mode = 'arquivado'" in SQL
    # only the code-defined (legacy) row is touched, never a Studio agent that happens to reuse the key
    assert "key = 'one-chat' AND definition_mode = 'legacy'" in SQL


def test_the_bridge_credential_row_is_removed():
    assert "DELETE FROM agents.app_integration_config WHERE key = 'social_wiring_api_token'" in SQL


def test_nothing_is_inserted_and_every_delete_is_scoped():
    assert "INSERT INTO" not in SQL.upper()
    for stmt in re.findall(r"DELETE FROM [\w.]+(?: WHERE [^;]+)?;", SQL):
        assert "WHERE" in stmt, stmt


def test_python_side_no_longer_seeds_it():
    # the seeding API itself is gone: nothing can re-create the retired row on a request
    assert not hasattr(FakeAgentStore, "ensure_default_agents")
    assert not hasattr(SupabaseAgentStore, "ensure_default_agents")
    assert FakeAgentStore().list(__import__("uuid").uuid4()) == []
