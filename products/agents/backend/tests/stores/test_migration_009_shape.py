"""Structural tests for `009_session_transcripts.sql` — parse-based, no
database needed. Mirrors the style of `test_migration_006_shape.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "009_session_transcripts.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


class TestServiceRoleOnlyRls:
    def test_rls_is_enabled(self, sql):
        assert (
            "ALTER TABLE agents.session_transcript_entries ENABLE ROW LEVEL SECURITY"
            in sql
        )

    def test_the_bypass_policy_uses_the_literal_keeper_name(self, sql):
        """The `check_admin_endpoint_service_role_bypass` keeper matches on
        the literal name `service_role_bypass`."""
        assert re.search(
            r'CREATE POLICY "service_role_bypass" ON agents\.session_transcript_entries\s+'
            r"FOR ALL TO service_role USING \(true\) WITH CHECK \(true\)",
            sql,
        )

    def test_there_is_no_authenticated_select_policy(self, sql):
        """Unlike every table in 006/007, this table stores raw CLI
        transcript content and is service-role only by design — no
        `_select_own_org` policy exists for it."""
        assert "session_transcript_entries_select_own_org" not in sql
        assert not re.search(
            r'CREATE POLICY "[^"]+" ON agents\.session_transcript_entries\s+'
            r"FOR SELECT TO authenticated",
            sql,
        )

    def test_anon_and_authenticated_are_explicitly_revoked(self, sql):
        """Defense-in-depth on top of RLS-with-no-matching-policy: the
        schema-wide default-privileges grant (001_agents.sql) hands every
        NEW table `ALL` to anon/authenticated at CREATE TABLE time — this
        must be explicitly revoked for this one table."""
        assert re.search(
            r"REVOKE ALL ON agents\.session_transcript_entries FROM anon, authenticated",
            sql,
        )


class TestTableShape:
    def test_conversation_id_cascades_on_delete(self, sql):
        assert re.search(
            r"conversation_id\s+UUID NOT NULL REFERENCES agents\.conversations\(id\) "
            r"ON DELETE CASCADE",
            sql,
        )

    def test_the_idempotency_key_is_unique_per_session(self, sql):
        assert "UNIQUE (conversation_id, sdk_session_id, entry_uuid)" in sql

    def test_the_seq_ordering_index_exists(self, sql):
        assert re.search(
            r"CREATE INDEX IF NOT EXISTS idx_agents_session_transcript_entries_seq\s+"
            r"ON agents\.session_transcript_entries\(conversation_id, sdk_session_id, seq\)",
            sql,
        )

    def test_required_columns_are_present(self, sql):
        for column in (
            "org_id",
            "sdk_session_id",
            "seq",
            "entry",
            "entry_uuid",
            "byte_size",
            "created_at",
        ):
            assert re.search(rf"\b{column}\b", sql), f"missing column: {column}"


class TestConversationsTranscriptEstado:
    def test_the_column_is_added_idempotently_with_the_contract_default(self, sql):
        assert re.search(
            r"ADD COLUMN IF NOT EXISTS transcript_estado TEXT NOT NULL DEFAULT 'ok'",
            sql,
        )

    def test_the_check_constraint_lists_exactly_the_contract_states(self, sql):
        assert re.search(
            r"CHECK \(transcript_estado IN "
            r"\('ok', 'truncado', 'incompleto', 'invalido'\)\)",
            sql,
        )

    def test_the_constraint_is_dropped_before_recreated_for_idempotency(self, sql):
        drop_idx = sql.index("DROP CONSTRAINT IF EXISTS conversations_transcript_estado_check")
        add_idx = sql.index("ADD CONSTRAINT conversations_transcript_estado_check")
        assert drop_idx < add_idx
