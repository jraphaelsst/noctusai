"""Structural tests for `006_agents.sql` — parse-based, no database needed.

Mirrors the style of
`products/social-wiring/backend/tests/test_migration_052_imovelweb_portal_leads.py`:
these guarantees are invisible at runtime until the day they are not, so
they are asserted against the migration TEXT rather than a live DB.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "006_agents.sql"
)

TABLES = ("agents", "agent_personas", "conversations", "messages", "approvals")


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


class TestRls:
    @pytest.mark.parametrize("table", TABLES)
    def test_rls_is_enabled(self, sql, table):
        assert f"ALTER TABLE agents.{table} ENABLE ROW LEVEL SECURITY" in sql

    @pytest.mark.parametrize("table", TABLES)
    def test_the_select_policy_is_org_scoped_via_current_org_id(self, sql, table):
        assert re.search(
            rf'CREATE POLICY "{table}_select_own_org"\s+ON agents\.{table}\s+'
            rf"FOR SELECT TO authenticated\s+USING \(org_id = current_org_id\(\)\)",
            sql,
        ), f"{table} is missing the org-scoped SELECT policy"

    @pytest.mark.parametrize("table", TABLES)
    def test_the_bypass_policy_uses_the_literal_keeper_name(self, sql, table):
        """The `check_admin_endpoint_service_role_bypass` keeper matches on
        the literal name `service_role_bypass` — a differently-named
        equivalent policy is invisible to it."""
        assert re.search(
            rf'CREATE POLICY "service_role_bypass" ON agents\.{table}\s+'
            rf"FOR ALL TO service_role USING \(true\) WITH CHECK \(true\)",
            sql,
        ), f"{table} must name its bypass policy literally `service_role_bypass`"


class TestUpdatedAtTriggers:
    @pytest.mark.parametrize("table", TABLES)
    def test_every_table_has_an_updated_at_trigger(self, sql, table):
        assert re.search(
            rf"CREATE OR REPLACE TRIGGER set_updated_at_{table}\s+"
            rf"BEFORE UPDATE ON agents\.{table}\s+"
            rf"FOR EACH ROW EXECUTE FUNCTION agents\.set_updated_at\(\)",
            sql,
        ), f"{table} is missing its updated_at trigger"

    def test_the_updated_at_function_is_declared_once(self, sql):
        assert sql.count("CREATE OR REPLACE FUNCTION agents.set_updated_at()") == 1


class TestPersonaVersioning:
    def test_exactly_one_active_persona_per_agent_is_enforced(self, sql):
        assert re.search(
            r"CREATE UNIQUE INDEX agent_personas_one_active_idx\s+"
            r"ON agents\.agent_personas \(agent_id\) WHERE ativa",
            sql,
        )

    def test_versao_is_unique_per_agent(self, sql):
        block = _table_block(sql, "agent_personas")
        assert "UNIQUE (agent_id, versao)" in block

    def test_the_atomic_version_flip_function_exists(self, sql):
        assert "CREATE OR REPLACE FUNCTION agents.create_persona_version(" in sql
        assert "RETURNS agents.agent_personas" in sql
        # The flip-then-insert body, in order: the old active row is
        # deactivated BEFORE the new one is inserted, both inside the same
        # function body (== one transaction per the migration header).
        fn_start = sql.index("CREATE OR REPLACE FUNCTION agents.create_persona_version(")
        fn_body = sql[fn_start:]
        deactivate_idx = fn_body.index("SET ativa = false")
        insert_idx = fn_body.index("INSERT INTO agents.agent_personas")
        assert deactivate_idx < insert_idx


class TestTurnLock:
    def test_conversations_carries_the_lock_columns(self, sql):
        block = _table_block(sql, "conversations")
        assert re.search(r"turn_lock_until\s+TIMESTAMPTZ NULL", block)
        assert re.search(r"turn_lock_instance_id\s+TEXT NULL", block)


class TestChecks:
    def test_agents_runtime_check(self, sql):
        block = _table_block(sql, "agents")
        assert "CHECK (runtime IN ('claude_sdk', 'external'))" in block

    def test_agents_key_is_unique_per_org(self, sql):
        block = _table_block(sql, "agents")
        assert "UNIQUE (org_id, key)" in block

    def test_agent_personas_model_check(self, sql):
        block = _table_block(sql, "agent_personas")
        assert "CHECK (model IN ('claude-opus-5', 'claude-sonnet-5'))" in block

    def test_agent_personas_effort_check(self, sql):
        block = _table_block(sql, "agent_personas")
        assert (
            "CHECK (effort IN ('low', 'medium', 'high', 'xhigh', 'max'))" in block
        )

    def test_conversations_status_check(self, sql):
        block = _table_block(sql, "conversations")
        assert "CHECK (status IN ('ativa', 'arquivada'))" in block

    def test_messages_role_check(self, sql):
        block = _table_block(sql, "messages")
        assert "CHECK (role IN ('user', 'assistant', 'system'))" in block

    def test_approvals_classe_and_decision_checks(self, sql):
        block = _table_block(sql, "approvals")
        assert "CHECK (classe IN ('escrita'))" in block
        assert (
            "CHECK (decision IN ('pendente', 'aprovada', 'negada', 'expirada'))"
            in block
        )


class TestNoWhatsAppColumns:
    """Contract §E.1 'Dropped from the sibling' — these must never reappear."""

    def test_no_whatsapp_tables_or_columns(self, sql):
        forbidden = [
            "whatsapp_connections",
            "whatsapp_allowlist",
            "app_settings",
            "credentials",
            "owner_msisdn",
            "waha_message_id",
            "ack_status",
        ]
        for term in forbidden:
            assert term not in sql, f"{term!r} must not appear — dropped from the sibling"


class TestCommonColumns:
    @pytest.mark.parametrize("table", TABLES)
    def test_every_table_has_the_common_columns(self, sql, table):
        block = _table_block(sql, table)
        assert re.search(r"id\s+UUID PRIMARY KEY DEFAULT gen_random_uuid\(\)", block)
        assert re.search(r"org_id\s+UUID NOT NULL", block)
        assert re.search(r"created_at\s+TIMESTAMPTZ NOT NULL DEFAULT now\(\)", block)
        assert re.search(r"updated_at\s+TIMESTAMPTZ NOT NULL DEFAULT now\(\)", block)


def _table_block(sql: str, table: str) -> str:
    """The `CREATE TABLE agents.<table> ( ... )` body."""
    start = sql.index(f"CREATE TABLE agents.{table} (")
    return sql[start : sql.index(");", start)]
