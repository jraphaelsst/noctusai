"""Structural pins for migration 030 (owner order 2026-10-19): the Academia agent's key
`julia` -> `bia`, then the SDR studio agent's `lead-imob` -> `julia`. The migration is also
replayed on a real Postgres (PGlite) by the pre-commit chain replay; these keep the ORDER
(free `julia` before reusing it), the re-run safety and the key-bearing leftovers honest."""
from __future__ import annotations

from pathlib import Path

from app.stores.agents import DEFAULT_AGENT_KEYS
from app.channels.chaves_legadas import canonical_channel_agent_key

SQL = Path(__file__).resolve().parents[1].joinpath("migrations").glob("*rename_bia_julia_agents.sql")
SQL = next(SQL).read_text(encoding="utf-8")


def test_academia_row_is_renamed_before_the_sdr_row_takes_the_key():
    assert SQL.index("SET key  = 'bia'") < SQL.index("WHERE a.key = 'lead-imob'")
    assert SQL.index("WHERE a.key = 'lead-imob'") < SQL.index("UPDATE agents.status_pagina")


def test_academia_row_is_identified_by_what_it_is_so_a_rerun_never_moves_the_sdr():
    block = SQL[SQL.index("SET key  = 'bia'"): SQL.index("-- 2.")]
    assert "a.key = 'julia'" in block
    assert "a.runtime = 'claude_sdk'" in block
    assert "a.definition_mode = 'legacy'" in block


def test_every_key_update_is_guarded_against_the_unique_org_key_constraint():
    assert SQL.count("NOT EXISTS") >= 5


def test_key_bearing_leftovers_are_moved_too():
    assert "nome_pagina = 'bia'" in SQL
    assert "key = 'bia_agent_id'" in SQL and "c.key = 'julia_agent_id'" in SQL
    assert "' · julia:'" in SQL


def test_python_side_matches_the_migration():
    # platform-defined agents are DATA, not reserved code keys (049)
    # (the code-defined chat agent stopped being seeded at the Renata cutover -- 053)
    assert DEFAULT_AGENT_KEYS == ("one-chat",)
    # NOC-REMEDIATE[drop-lead-imob-alias]: the old SDR key stays an alias for one release.
    assert canonical_channel_agent_key("lead-imob") == "julia"
    assert canonical_channel_agent_key("julia") == "julia"
    assert canonical_channel_agent_key("one-chat") == "one-chat"
