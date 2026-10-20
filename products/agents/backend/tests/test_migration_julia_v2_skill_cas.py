"""Structural pins for migration 041 (Julia v2 A-polish #11). The behaviour runs on a real Postgres in the chain replay
(`mcp/noctusai/tests/test_agents_skill_cas_on_replay.py`); these keep the intent honest."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

ROOT = Path(__file__).resolve().parents[1]
M41 = migration_sql(ROOT, "julia_v2_skill_cas")


def test_the_parent_draft_is_locked_and_compared_before_the_update():
    lock, compare, update = (M41.index("FOR UPDATE"), M41.index("v_hash IS DISTINCT FROM p_expected_hash"),
                             M41.index("UPDATE agents.agent_skills"))
    assert lock < compare < update
    assert "'conflito_de_versao'" in M41 and "'version_immutable'" in M41


def test_execute_is_service_role_only():
    assert re.search(r"REVOKE ALL ON FUNCTION agents\.update_draft_skill\(UUID, UUID, JSONB, TEXT\) FROM PUBLIC, anon, authenticated", M41)
    assert "GRANT EXECUTE ON FUNCTION agents.update_draft_skill(UUID, UUID, JSONB, TEXT) TO service_role" in M41
