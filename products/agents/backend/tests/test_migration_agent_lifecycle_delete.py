"""048 structural pins: the agent-deletion RPC is locked down, the audit log can lose ONLY its agent_id (under the
flag), and -- the part that rots -- every table that references ``agents.agents`` is accounted for by the RPC.

A new table with ``agent_id REFERENCES agents.agents(id)`` (NO ACTION) makes `excluir_agente` fail in prod with an FK
violation on the first delete of an agent that has a row there; this test turns that into a red the day the table is
added, naming the table. Behaviour on a real Postgres: mcp/noctusai/tests/test_agents_excluir_agente_on_replay.py.
"""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

BACKEND = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted(BACKEND.joinpath("migrations").glob("[0-9][0-9][0-9]_*.sql"))
SQL = migration_sql(BACKEND, "agent_lifecycle_delete")
_TABLE_RE = re.compile(r"^(?:CREATE TABLE(?: IF NOT EXISTS)?|ALTER TABLE(?: ONLY)?)\s+agents\.(\w+)", re.I)
_REF_RE = re.compile(r"REFERENCES agents\.agents\s*\(id\)(?P<tail>[^,\n]*)", re.I)


def _rpc_body() -> str:
    m = re.search(r"CREATE OR REPLACE FUNCTION agents\.excluir_agente\(.*?\n\$\$;", SQL, re.S)
    assert m, "excluir_agente not found"
    return m.group(0)


def _referencing_tables() -> dict[str, str]:
    """table -> the ON DELETE action of its FK to agents.agents ('NO ACTION' | 'CASCADE' | 'SET NULL')."""
    found: dict[str, str] = {}
    for path in MIGRATIONS:
        table = None
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _TABLE_RE.match(line.strip())
            if m:
                table = m.group(1)
            ref = _REF_RE.search(line)
            if ref and table:
                tail = ref.group("tail").upper()
                action = "CASCADE" if "ON DELETE CASCADE" in tail else "SET NULL" if "ON DELETE SET NULL" in tail else "NO ACTION"
                found[table] = action
    return found


def test_the_rpc_is_service_role_only_with_a_pinned_search_path():
    body = _rpc_body()
    assert "SECURITY DEFINER" in body and "SET search_path = agents, public" in body
    assert "REVOKE ALL ON FUNCTION agents.excluir_agente(UUID, UUID, UUID) FROM PUBLIC, anon, authenticated;" in SQL
    assert "GRANT EXECUTE ON FUNCTION agents.excluir_agente(UUID, UUID, UUID) TO service_role;" in SQL


def test_every_guard_code_is_raised_with_a_distinct_text():
    body = _rpc_body()
    for code in ("publicado", "tem_instancias", "tem_conversas", "tem_canal", "ativo"):
        assert f"RAISE EXCEPTION 'excluir_agente_{code}' USING ERRCODE = 'P0001'" in body, code
    assert "RAISE EXCEPTION 'agent_not_found'" in body


def test_every_table_referencing_agents_is_handled_by_the_rpc():
    body = _rpc_body()
    refs = _referencing_tables()
    assert len(refs) >= 20, f"the FK scan broke (found {sorted(refs)})"
    unhandled = []
    for table, action in sorted(refs.items()):
        if table == "agent_audit_log":
            continue  # 048 turns it into ON DELETE SET NULL
        if action in ("CASCADE", "SET NULL"):
            continue
        if f"agents.{table}" not in body:
            unhandled.append(table)
    assert not unhandled, f"excluir_agente must delete (or guard) rows of: {unhandled}"


def test_the_audit_fk_is_set_null_and_the_guard_has_the_single_carveout():
    assert "REFERENCES agents.agents(id) ON DELETE SET NULL" in SQL
    assert "ALTER COLUMN agent_id DROP NOT NULL" in SQL
    guard = re.search(r"FUNCTION agents\.guard_audit_log_append_only\(\).*?\n\$\$;", SQL, re.S).group(0)
    assert "current_setting('agents.agent_delete', true) = 'on'" in guard
    assert "NEW.agent_id IS NULL" in guard and "TG_OP = 'UPDATE'" in guard
    # every other column frozen, DELETE never allowed
    for col in ("id", "org_id", "actor", "acao", "antes", "depois", "created_at", "agent_key", "agent_nome"):
        assert f"NEW.{col} IS NOT DISTINCT FROM OLD.{col}" in guard, col
    assert "RAISE EXCEPTION 'audit_log_append_only'" in guard


def test_the_flag_wraps_only_the_agent_delete():
    body = _rpc_body()
    on = body.index("set_config('agents.agent_delete', 'on', true)")
    delete = body.index("DELETE FROM agents.agents WHERE id = p_agent_id")
    off = body.index("set_config('agents.agent_delete', 'off', true)")
    assert on < delete < off
    assert "agents.agent_delete" not in body[:on], "the flag must not be on while the dependents are deleted"


def test_the_tombstone_names_the_agent_without_an_id():
    body = _rpc_body()
    assert "'agente_excluido'" in body and "p_org_id, NULL, v_agent.key, v_agent.nome" in body
