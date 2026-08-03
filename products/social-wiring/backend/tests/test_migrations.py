"""
Structural (parse-based) tests for social_wiring migrations.

No database required — these tests read the SQL migration files as text and
assert that the expected structural elements are declared. They catch
regressions like "someone deleted a policy" or "renamed a column" before
they hit a real Supabase instance.

Coverage:
- 001_social-wiring.sql: api_tokens table structure + RLS shape
- 011_rls_current_org_id.sql: current_org_id() fix shape (no jwt() pattern)
- 040_whatsapp_inbox_realtime_schema.sql: whatsapp_chats table + indexes +
  RLS shape, conversation_messages ack/chat_id columns + thread index
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "migrations" / "001_social-wiring.sql"
)

MIGRATION_011_PATH = (
    Path(__file__).resolve().parents[1] / "migrations" / "011_rls_current_org_id.sql"
)

MIGRATION_040_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "040_whatsapp_inbox_realtime_schema.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"Migration file missing at {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# social_wiring.api_tokens — platform-auth-modernization Wave 1 (E-MIGRATION)
# ---------------------------------------------------------------------------


def test_api_tokens_table_is_created(sql: str) -> None:
    """The CREATE TABLE block must exist verbatim (schema-qualified)."""
    assert re.search(
        r"CREATE TABLE\s+social_wiring\.api_tokens\s*\(",
        sql,
    ), "Missing CREATE TABLE social_wiring.api_tokens"


def test_api_tokens_token_prefix_not_null(sql: str) -> None:
    """`token_prefix` is the plaintext UI-display prefix — must be NOT NULL.

    The brief's CHECK-constraint clause for `token_prefix` is the NOT NULL
    constraint on the column declaration (the SQL has no separate
    `CHECK (token_prefix IS NOT NULL)` — `NOT NULL` IS the constraint).
    """
    assert re.search(
        r"token_prefix\s+TEXT\s+NOT\s+NULL\b",
        sql,
    ), "token_prefix must be declared TEXT NOT NULL"


def test_api_tokens_unique_index_on_token_hash(sql: str) -> None:
    """A UNIQUE index on token_hash (active-only) must exist."""
    assert re.search(
        r"CREATE\s+UNIQUE\s+INDEX\s+idx_sw_api_tokens_hash_active\s+"
        r"ON\s+social_wiring\.api_tokens\(token_hash\)\s+"
        r"WHERE\s+revoked_at\s+IS\s+NULL",
        sql,
    ), "Missing UNIQUE active-only index on social_wiring.api_tokens(token_hash)"


def test_api_tokens_rls_enabled(sql: str) -> None:
    """RLS must be enabled on the api_tokens table."""
    assert re.search(
        r"ALTER\s+TABLE\s+social_wiring\.api_tokens\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        sql,
    ), "RLS not enabled for social_wiring.api_tokens"


def test_api_tokens_has_four_policies(sql: str) -> None:
    """Exactly 4 policies: select / insert / update / service_role."""
    policy_pattern = re.compile(
        r'CREATE\s+POLICY\s+"(api_tokens_[a-z_]+)"\s+ON\s+social_wiring\.api_tokens',
        re.IGNORECASE,
    )
    policy_names = policy_pattern.findall(sql)
    assert len(policy_names) == 4, (
        f"Expected 4 policies on social_wiring.api_tokens; found {len(policy_names)}: "
        f"{policy_names!r}"
    )
    expected = {
        "api_tokens_select_own_org",
        "api_tokens_insert_own_org_admin",
        "api_tokens_update_own_org_admin",
        "api_tokens_service_role",
    }
    assert set(policy_names) == expected, (
        f"Policy-name set mismatch.\n  expected: {expected!r}\n  got:      {set(policy_names)!r}"
    )


@pytest.fixture(scope="module")
def sql_011() -> str:
    assert MIGRATION_011_PATH.is_file(), f"Migration 011 missing at {MIGRATION_011_PATH}"
    return MIGRATION_011_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 011_rls_current_org_id.sql — current_org_id() RLS fix (2026-06-02)
# ---------------------------------------------------------------------------


def test_011_declares_public_current_org_id(sql_011: str) -> None:
    """public.current_org_id() must be declared as SECURITY DEFINER."""
    assert re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.current_org_id\(\)",
        sql_011,
        re.IGNORECASE,
    ), "Missing CREATE OR REPLACE FUNCTION public.current_org_id()"
    assert "SECURITY DEFINER" in sql_011, "current_org_id() must be SECURITY DEFINER"
    assert "noctus_users" in sql_011, (
        "current_org_id() must read from noctus_users (trusted-table resolver)"
    )


def test_011_declares_erp_current_org_id(sql_011: str) -> None:
    """erp.current_org_id() must also be declared SECURITY DEFINER."""
    assert re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+erp\.current_org_id\(\)",
        sql_011,
        re.IGNORECASE,
    ), "Missing CREATE OR REPLACE FUNCTION erp.current_org_id()"


def _strip_sql_comments(sql: str) -> str:
    """Strip single-line (--) SQL comments for AST-style checks.

    This lets tests assert absence of patterns in actual SQL while
    allowing explanatory comments to reference the old broken form.
    Does NOT strip block comments (/* ... */), which are not used in
    these migration files.
    """
    lines = []
    for line in sql.splitlines():
        # Remove everything from -- onwards
        idx = line.find("--")
        if idx != -1:
            line = line[:idx]
        lines.append(line)
    return "\n".join(lines)


def test_011_no_broken_jwt_org_id_pattern(sql_011: str) -> None:
    """011 SQL (non-comment) must NOT contain the broken auth.jwt() org_id claim.

    The old pattern (auth.jwt() ->> 'org_id') is always NULL in Supabase —
    org_id is nested under user_metadata. All policies must use current_org_id().
    Comments may reference the old form for WHY documentation.
    """
    sql_no_comments = _strip_sql_comments(sql_011)
    assert "auth.jwt()" not in sql_no_comments, (
        "Migration 011 SQL must NOT reference auth.jwt() outside comments — "
        "all policies must use current_org_id() (the SECURITY DEFINER "
        "trusted-table resolver). auth.jwt() ->> 'org_id' is always NULL. "
        "See memory/feedback_rls_never_key_on_user_metadata.md"
    )
    assert "user_metadata" not in sql_no_comments, (
        "Migration 011 SQL must NOT reference user_metadata outside comments — "
        "it is user-editable and constitutes a privilege-escalation hole."
    )


def test_011_covers_49_current_org_id_policies(sql_011: str) -> None:
    """011 must recreate exactly 49 policies that call current_org_id().

    These are the 49 policies fixed live on 2026-06-02 for social_wiring.
    The count is also a sentinel: fewer = missing policy; more = new policy
    added without this test being updated.
    """
    # Count CREATE POLICY statements (Section 2 + Section 3 combined)
    policy_pattern = re.compile(r"^CREATE\s+POLICY\b", re.MULTILINE | re.IGNORECASE)
    policy_count = len(policy_pattern.findall(sql_011))
    # 49 already-fixed + 5 remaining broken = 54 total CREATE POLICY statements
    assert policy_count == 54, (
        f"Expected 54 CREATE POLICY statements in 011 (49 codified + 5 new fixes); "
        f"found {policy_count}. If policies were added/removed, update this count."
    )


def test_001_no_broken_jwt_pattern(sql: str) -> None:
    """001_social-wiring.sql SQL (non-comment) must not have jwt() org_id pattern.

    After the 011 migration update, all 001 policies use current_org_id().
    This test prevents regression (someone adding a new policy to 001 with the
    old broken pattern). Comments explaining the old form are still allowed.
    """
    sql_no_comments = _strip_sql_comments(sql)
    assert "auth.jwt()" not in sql_no_comments, (
        "001_social-wiring.sql must NOT reference auth.jwt() in SQL — all org-scoped "
        "policies must use current_org_id(). See 011_rls_current_org_id.sql."
    )


# ---------------------------------------------------------------------------
# 040_whatsapp_inbox_realtime_schema.sql — whatsapp_chats + conversation_messages
# ack/chat_id (whatsapp-realtime-inbox, Slice 3, 2026-08-03)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sql_040() -> str:
    assert MIGRATION_040_PATH.is_file(), f"Migration 040 missing at {MIGRATION_040_PATH}"
    return MIGRATION_040_PATH.read_text(encoding="utf-8")


def test_040_whatsapp_chats_table_created(sql_040: str) -> None:
    """The CREATE TABLE block must exist verbatim (idempotent, schema-qualified)."""
    assert re.search(
        r"CREATE TABLE IF NOT EXISTS\s+social_wiring\.whatsapp_chats\s*\(",
        sql_040,
    ), "Missing CREATE TABLE IF NOT EXISTS social_wiring.whatsapp_chats"


def test_040_whatsapp_chats_primary_key(sql_040: str) -> None:
    """PK is (connection_id, chat_id) — the compound identity of one chat."""
    assert re.search(
        r"PRIMARY KEY\s*\(connection_id,\s*chat_id\)",
        sql_040,
    ), "whatsapp_chats must have PRIMARY KEY (connection_id, chat_id)"


def test_040_whatsapp_chats_connection_id_has_no_fk(sql_040: str) -> None:
    """connection_id carries NO REFERENCES — mirrors 014's no-FK precedent.

    Connections can be deleted; orphaned chat history is an accepted
    trade-off (see 014_whatsapp_chat_per_connection.sql and this file's
    header). A future edit adding a FK here would silently reintroduce the
    coupling 014 deliberately avoided.
    """
    sql_no_comments = _strip_sql_comments(sql_040)
    assert "REFERENCES social_wiring.whatsapp_connections" not in sql_no_comments, (
        "whatsapp_chats.connection_id must NOT carry a FOREIGN KEY to "
        "whatsapp_connections — see 014_whatsapp_chat_per_connection.sql precedent."
    )


def test_040_chat_list_index_shape(sql_040: str) -> None:
    """THE chat-list query index: (connection_id, archived, last_message_at DESC)."""
    assert re.search(
        r"CREATE INDEX IF NOT EXISTS idx_sw_whatsapp_chats_list\s+"
        r"ON social_wiring\.whatsapp_chats\s*"
        r"\(connection_id,\s*archived,\s*last_message_at DESC\)",
        sql_040,
    ), "Missing/wrong-shaped idx_sw_whatsapp_chats_list — must be (connection_id, archived, last_message_at DESC)"


def test_040_whatsapp_chats_rls_enabled(sql_040: str) -> None:
    assert re.search(
        r"ALTER TABLE social_wiring\.whatsapp_chats ENABLE ROW LEVEL SECURITY",
        sql_040,
    ), "RLS not enabled for social_wiring.whatsapp_chats"


def test_040_whatsapp_chats_has_two_policies(sql_040: str) -> None:
    """Exactly 2 policies: authenticated SELECT (org-scoped) + service_role ALL."""
    policy_pattern = re.compile(
        r'CREATE\s+POLICY\s+"(whatsapp_chats_[a-z_]+)"\s+ON\s+social_wiring\.whatsapp_chats',
    )
    policy_names = policy_pattern.findall(sql_040)
    assert set(policy_names) == {
        "whatsapp_chats_select_own_org",
        "whatsapp_chats_service_role",
    }, f"Policy-name set mismatch on whatsapp_chats: {set(policy_names)!r}"


def test_040_select_policy_does_not_filter_beyond_org(sql_040: str) -> None:
    """The authenticated SELECT policy must only scope by org_id.

    Per KB § PATTERNS/frontend/status-pagina-dev-visibility.md: an RLS
    read-policy that filters a category (e.g. archived / unread) makes every
    downstream FE branch keyed on that category dead. That filtering belongs
    in the FE, not RLS.
    """
    match = re.search(
        r'CREATE POLICY "whatsapp_chats_select_own_org" ON social_wiring\.whatsapp_chats\s+'
        r"FOR SELECT TO authenticated\s+"
        r"USING \(org_id = current_org_id\(\)\);",
        sql_040,
    )
    assert match, (
        "whatsapp_chats_select_own_org must be USING (org_id = current_org_id()) "
        "with no additional predicate (no archived/unread/status filter)."
    )


def test_040_conversation_messages_ack_columns_added(sql_040: str) -> None:
    for stmt in (
        r"ALTER TABLE social_wiring\.conversation_messages\s+"
        r"ADD COLUMN IF NOT EXISTS ack SMALLINT;",
        r"ALTER TABLE social_wiring\.conversation_messages\s+"
        r"ADD COLUMN IF NOT EXISTS acked_at TIMESTAMPTZ;",
        r"ALTER TABLE social_wiring\.conversation_messages\s+"
        r"ADD COLUMN IF NOT EXISTS chat_id TEXT;",
    ):
        assert re.search(stmt, sql_040), f"Missing idempotent ALTER: {stmt!r}"


def test_040_conversation_messages_not_backfilled(sql_040: str) -> None:
    """No UPDATE statement may backfill chat_id on existing rows (by design)."""
    sql_no_comments = _strip_sql_comments(sql_040)
    assert not re.search(
        r"UPDATE\s+social_wiring\.conversation_messages\s+SET\s+chat_id",
        sql_no_comments,
        re.IGNORECASE,
    ), "conversation_messages.chat_id must NOT be backfilled (mirrors 014's connection_id precedent)"


def test_040_thread_index_shape(sql_040: str) -> None:
    """THE thread query index: (connection_id, chat_id, created_at DESC)."""
    assert re.search(
        r"CREATE INDEX IF NOT EXISTS idx_sw_conv_msgs_connection_chat_id\s+"
        r"ON social_wiring\.conversation_messages\s*"
        r"\(connection_id,\s*chat_id,\s*created_at DESC\)",
        sql_040,
    ), "Missing/wrong-shaped idx_sw_conv_msgs_connection_chat_id"


def test_040_all_statements_are_idempotent(sql_040: str) -> None:
    """Every DDL verb in this file must carry an idempotent guard.

    CREATE TABLE / INDEX -> IF NOT EXISTS; ALTER TABLE ADD COLUMN -> IF NOT
    EXISTS; DROP POLICY / DROP TRIGGER -> IF EXISTS; CREATE FUNCTION ->
    OR REPLACE. A bare CREATE TABLE/INDEX (no IF NOT EXISTS) or a bare DROP
    POLICY/TRIGGER (no IF EXISTS) would make a re-run of this file error out.
    """
    sql_no_comments = _strip_sql_comments(sql_040)
    assert not re.search(
        r"CREATE TABLE(?! IF NOT EXISTS)\s+social_wiring", sql_no_comments
    ), "found a non-idempotent bare CREATE TABLE"
    assert not re.search(
        r"CREATE INDEX(?! IF NOT EXISTS)\s+\w", sql_no_comments
    ), "found a non-idempotent bare CREATE INDEX"
    assert not re.search(
        r"DROP POLICY(?! IF EXISTS)\s+", sql_no_comments
    ), "found a non-idempotent bare DROP POLICY"
    assert not re.search(
        r"DROP TRIGGER(?! IF EXISTS)\s+", sql_no_comments
    ), "found a non-idempotent bare DROP TRIGGER"
