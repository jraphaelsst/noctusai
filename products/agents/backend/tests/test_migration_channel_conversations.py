"""Structural pins for migration 025 (Lais A2): channel columns + the owner
CHECK, the identity unique index, the idempotency ledger, the two erasure
functions (service-role only), and the lead-data RLS narrowing. The migration is
replayed on a real Postgres (PGlite) by the pre-commit chain replay; these keep
its intent honest against the Python side."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1], "channel_conversations")


def test_channel_columns_and_nullable_owner():
    for col in ("channel TEXT NULL", "channel_ref JSONB NULL", "contact JSONB NULL"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in SQL
    assert "ALTER COLUMN owner_user_id DROP NOT NULL" in SQL


def test_check_keeps_an_owner_on_every_user_conversation_and_an_identity_on_every_channel_one():
    block = SQL[SQL.index("ADD CONSTRAINT conversations_channel_owner_check"):]
    block = block[: block.index(");")]
    assert "channel IS NULL AND owner_user_id IS NOT NULL" in block
    assert "channel IS NOT NULL AND channel <> '' AND channel_ref IS NOT NULL" in block


def test_identity_unique_partial_index():
    m = re.search(
        r"CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_conversations_channel_ref\s+"
        r"ON agents\.conversations \(org_id, agent_id, channel, channel_ref\)\s+WHERE channel IS NOT NULL",
        SQL,
    )
    assert m


def test_idempotency_ledger_is_unique_on_org_connection_message_and_cascades():
    assert "CONSTRAINT uq_agents_channel_inbound_msg UNIQUE (org_id, connection_id, provider_message_id)" in SQL
    assert "REFERENCES agents.conversations(id) ON DELETE CASCADE" in SQL
    assert "REVOKE ALL ON agents.channel_inbound FROM anon, authenticated" in SQL


def test_erasure_functions_are_secdef_service_role_only():
    for fn, sig in (
        ("delete_channel_conversation", "UUID, UUID"),
        ("purge_channel_conversations", "TIMESTAMPTZ"),
    ):
        assert f"FUNCTION agents.{fn}(" in SQL
        assert f"REVOKE ALL ON FUNCTION agents.{fn}({sig}) FROM PUBLIC, anon, authenticated" in SQL
        assert f"GRANT EXECUTE ON FUNCTION agents.{fn}({sig}) TO service_role" in SQL


def test_erasure_takes_messages_approvals_ledger_and_the_conversation():
    for fn in ("delete_channel_conversation", "purge_channel_conversations"):
        body = SQL[SQL.index(f"FUNCTION agents.{fn}("):]
        body = body[: body.index("$$;", body.index("AS $$")) ]
        for table in ("agents.messages", "agents.approvals", "agents.channel_inbound", "agents.conversations"):
            assert f"DELETE FROM {table}" in body, (fn, table)
        assert "channel IS NOT NULL" in body  # a user conversation is never erased


def test_authenticated_reads_never_reach_a_lead_conversation():
    assert re.search(r"ALTER POLICY conversations_select_own_org[\s\S]*?channel IS NULL", SQL)
    assert re.search(r"ALTER POLICY messages_select_own_org[\s\S]*?c\.channel IS NOT NULL", SQL)
