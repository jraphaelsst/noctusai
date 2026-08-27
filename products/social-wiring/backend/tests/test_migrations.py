"""
Structural (parse-based) tests for social_wiring migrations.

No database required — these tests read the SQL migration files as text and
assert that the expected structural elements are declared. They catch
regressions like "someone deleted a policy" or "renamed a column" before
they hit a real Supabase instance.

Coverage:
- 001_social-wiring.sql: api_tokens table structure + RLS shape
- 011_rls_current_org_id.sql: current_org_id() fix shape (no jwt() pattern)
- 042_whatsapp_inbox_realtime_schema.sql: whatsapp_chats table + indexes +
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
    / "042_whatsapp_inbox_realtime_schema.sql"
)


MIGRATION_META_WEBHOOK_PATH = (
    Path(__file__).resolve().parents[1] / "migrations" / "044_meta_webhook_events.sql"
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
# 042_whatsapp_inbox_realtime_schema.sql — whatsapp_chats + conversation_messages
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


@pytest.fixture(scope="module")
def sql_meta_webhook() -> str:
    assert MIGRATION_META_WEBHOOK_PATH.is_file(), f"Migration file missing at {MIGRATION_META_WEBHOOK_PATH}"
    return MIGRATION_META_WEBHOOK_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# social_wiring.meta_webhook_events — Meta Lead-Ads webhook inbox (044)
#
# This table is the reason a failed delivery is recoverable instead of lost:
# Meta retries non-2xx and can disable the subscription, and never re-sends
# after a 200, so the receiver persists-then-200s. These tests pin the
# structural properties that guarantee is built on.
# ---------------------------------------------------------------------------


def test_meta_webhook_table_is_created(sql_meta_webhook: str) -> None:
    assert re.search(
        r"CREATE TABLE\s+IF NOT EXISTS\s+social_wiring\.meta_webhook_events\s*\(",
        sql_meta_webhook,
    ), "Missing CREATE TABLE social_wiring.meta_webhook_events"


def test_meta_webhook_id_is_the_natural_primary_key(sql_meta_webhook: str) -> None:
    """`id` IS Meta's `leadgen_id`. The PK is the replay-dedup guarantee —
    the layer that survives a restart and a Redis eviction. A surrogate key
    here would silently allow duplicate leads."""
    assert re.search(r"id\s+TEXT\s+PRIMARY KEY", sql_meta_webhook), (
        "meta_webhook_events.id must be TEXT PRIMARY KEY (Meta's leadgen_id)"
    )


def test_meta_webhook_org_id_is_nullable(sql_meta_webhook: str) -> None:
    """NULLABLE ON PURPOSE: an unmappable page lands `status='unresolved'`
    rather than being guessed into an org. Adding NOT NULL here would force
    the receiver to invent an org_id, which is how one tenant's lead PII
    ends up in another tenant's RLS scope."""
    assert re.search(r"org_id\s+UUID\s*,", sql_meta_webhook), (
        "org_id must be nullable — 'unresolved' deliveries carry no org"
    )
    assert not re.search(r"org_id\s+UUID\s+NOT NULL", sql_meta_webhook), (
        "org_id must NOT be NOT NULL — see the org-misattribution guard"
    )


def test_meta_webhook_payload_is_jsonb_not_null(sql_meta_webhook: str) -> None:
    assert re.search(r"payload\s+JSONB\s+NOT NULL", sql_meta_webhook), (
        "payload must be JSONB NOT NULL — the lossless verified delivery"
    )


def test_meta_webhook_status_check_covers_the_full_lifecycle(sql_meta_webhook: str) -> None:
    """Every state the receiver and the retry job can write must be legal,
    or a legitimate outcome becomes a constraint violation at runtime."""
    match = re.search(r"status IN \(([^)]*)\)", sql_meta_webhook)
    assert match, "Missing status CHECK constraint"
    allowed = {v.strip().strip("'") for v in match.group(1).split(",")}
    assert allowed == {"received", "processed", "error", "unresolved", "ignored"}, (
        f"status CHECK drifted from the receiver's lifecycle: {allowed}"
    )


def test_meta_webhook_rls_is_enabled(sql_meta_webhook: str) -> None:
    assert re.search(
        r"ALTER TABLE\s+social_wiring\.meta_webhook_events\s+ENABLE ROW LEVEL SECURITY",
        sql_meta_webhook,
    ), "RLS must be enabled — this table holds lead PII"


def test_meta_webhook_select_policy_uses_current_org_id_not_jwt(sql_meta_webhook: str) -> None:
    """RLS must resolve the org through `public.current_org_id()`, never
    `auth.jwt()` / `user_metadata` (memory: feedback_rls_never_key_on_user_metadata)."""
    assert re.search(
        r'CREATE POLICY\s+"meta_webhook_events_select_own_org".*?'
        r"USING \(org_id = public\.current_org_id\(\)\)",
        sql_meta_webhook,
        re.DOTALL,
    ), "SELECT policy must key on public.current_org_id()"
    # Comments are stripped first (same reason as `test_011_no_broken_jwt_org_id_pattern`):
    # the header deliberately NAMES the forbidden patterns to explain why they
    # are forbidden, and a naive substring check would flag that prose.
    sql_no_comments = _strip_sql_comments(sql_meta_webhook)
    assert "auth.jwt()" not in sql_no_comments, "must not key RLS on auth.jwt()"
    assert "user_metadata" not in sql_no_comments, "must not key RLS on user_metadata"


def test_meta_webhook_service_role_policy_exists(sql_meta_webhook: str) -> None:
    """The receiver writes through the admin (service-role) client, since a
    public webhook has no JWT context to resolve an org from."""
    assert re.search(
        r'CREATE POLICY\s+"meta_webhook_events_service_role".*?FOR ALL\s+TO service_role',
        sql_meta_webhook,
        re.DOTALL,
    ), "Missing service_role ALL policy"


def test_meta_webhook_pending_index_matches_the_retry_job_predicate(sql_meta_webhook: str) -> None:
    """The partial index and the drain query must agree, or the retry job
    silently sequential-scans a table that only grows."""
    match = re.search(
        r"idx_sw_meta_webhook_events_pending.*?WHERE status IN \(([^)]*)\)",
        sql_meta_webhook,
        re.DOTALL,
    )
    assert match, "Missing partial pending index"
    covered = {v.strip().strip("'") for v in match.group(1).split(",")}
    assert covered == {"received", "error", "unresolved"}, (
        f"pending index predicate drifted from the drain query: {covered}"
    )


def test_meta_webhook_is_idempotent_and_forward_only(sql_meta_webhook: str) -> None:
    """Re-applying must be a no-op: every CREATE POLICY is preceded by a
    DROP POLICY IF EXISTS, and every CREATE INDEX/TABLE is IF NOT EXISTS."""
    created = set(re.findall(r'CREATE POLICY\s+"([^"]+)"', sql_meta_webhook))
    dropped = set(re.findall(r'DROP POLICY IF EXISTS\s+"([^"]+)"', sql_meta_webhook))
    assert created and created <= dropped, (
        f"policies created without a preceding DROP IF EXISTS: {created - dropped}"
    )
    bare_index = re.findall(r"CREATE INDEX (?!IF NOT EXISTS)", sql_meta_webhook)
    assert not bare_index, "every CREATE INDEX must be IF NOT EXISTS"


def test_meta_webhook_carries_the_migration_file_only_banner(sql_meta_webhook: str) -> None:
    """The banner is what stops an agent applying this to prod as a side
    effect — application is an explicitly consented, separate step."""
    assert "MIGRATION FILE ONLY" in sql_meta_webhook, (
        "missing the 🔴 MIGRATION FILE ONLY banner (see migration 033)"
    )
# 042_whatsapp_inbox_realtime_schema.sql — whatsapp_chats + conversation_messages
# ack/chat_id (whatsapp-realtime-inbox, Slice 3, 2026-08-03)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 083_cliente_checklist_extras.sql — the operator-authored half of the card's
# checklist (card_hub, 2026-08-27)
# ---------------------------------------------------------------------------

MIGRATION_083_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "083_cliente_checklist_extras.sql"
)


@pytest.fixture(scope="module")
def sql_extras() -> str:
    assert MIGRATION_083_PATH.is_file(), f"Migration file missing at {MIGRATION_083_PATH}"
    return MIGRATION_083_PATH.read_text(encoding="utf-8")


def test_extras_table_is_created_schema_qualified(sql_extras: str) -> None:
    assert re.search(
        r"CREATE TABLE IF NOT EXISTS\s+social_wiring\.cliente_checklist_extras\s*\(",
        sql_extras,
    ), "Missing CREATE TABLE social_wiring.cliente_checklist_extras"


def test_extras_tipo_check_matches_the_service(sql_extras: str) -> None:
    """The CHECK and `checklist_extras_service.TIPOS_VALIDOS` are two guards on
    one decision — the schema protects the API surface, the CHECK protects
    every other writer. They must name the SAME set, or a migration writes a
    row the service cannot render."""
    from app.modules.card_hub import checklist_extras_service as extras_svc

    match = re.search(r"CHECK \(tipo IN \(([^)]*)\)\)", sql_extras)
    assert match, "Missing CHECK on tipo"
    permitidos = {v.strip().strip("'") for v in match.group(1).split(",")}
    assert permitidos == set(extras_svc.TIPOS_VALIDOS), (
        f"tipo CHECK drifted from TIPOS_VALIDOS: {permitidos} vs "
        f"{set(extras_svc.TIPOS_VALIDOS)}"
    )


def test_extras_has_no_stored_concluido_column(sql_extras: str) -> None:
    """🔴 Completion is DERIVED. A `concluido` column could only agree with
    `valor_texto`/`documento_id` or be silently wrong — and the retention sweep
    soft-deletes documents with no knowledge of this table, so a stored tick
    would outlive the file it asserts."""
    bloco = sql_extras.split("CREATE TABLE IF NOT EXISTS", 1)[1].split(");", 1)[0]
    assert "concluido" not in bloco, (
        "cliente_checklist_extras must NOT store a concluido column"
    )


def test_extras_documento_fk_sets_null_never_cascades(sql_extras: str) -> None:
    """Deleting the FILE keeps the LINE. A CASCADE would delete the request
    because someone sent the wrong scan."""
    assert re.search(
        r"documento_id\s+UUID\s+REFERENCES\s+social_wiring\.cliente_documentos\(id\)\s+"
        r"ON DELETE SET NULL",
        sql_extras,
    ), "documento_id must be ON DELETE SET NULL"
    assert not re.search(
        r"cliente_documentos\(id\)\s+ON DELETE CASCADE", sql_extras
    ), "documento_id must never CASCADE"


def test_extras_cliente_fk_cascades(sql_extras: str) -> None:
    """The lines belong to the client — mirrors `cliente_documentos` (057) and
    `cliente_documento_checklist` (067)."""
    assert re.search(
        r"cliente_id\s+UUID NOT NULL REFERENCES\s+social_wiring\.clientes\(id\)\s+"
        r"ON DELETE CASCADE",
        sql_extras,
    ), "cliente_id must CASCADE from clientes"


def test_extras_rls_is_enabled_and_org_scoped(sql_extras: str) -> None:
    """Org scoping copied from the sibling tables rather than reinvented:
    `public.current_org_id()`, never `auth.jwt()` / `user_metadata` (011)."""
    assert re.search(
        r"ALTER TABLE social_wiring\.cliente_checklist_extras ENABLE ROW LEVEL SECURITY",
        sql_extras,
    ), "RLS must be enabled"
    assert re.search(
        r'CREATE POLICY\s+"cliente_checklist_extras_select_own_org".*?'
        r"USING \(org_id = public\.current_org_id\(\)\)",
        sql_extras,
        re.DOTALL,
    ), "Missing org-scoped SELECT policy on current_org_id()"
    assert re.search(
        r'CREATE POLICY\s+"cliente_checklist_extras_service_role".*?FOR ALL\s+TO service_role',
        sql_extras,
        re.DOTALL,
    ), "Missing service_role ALL policy"
    sem_comentarios = "\n".join(
        linha for linha in sql_extras.splitlines() if not linha.strip().startswith("--")
    )
    assert "auth.jwt()" not in sem_comentarios
    assert "user_metadata" not in sem_comentarios


def test_extras_is_idempotent_and_forward_only(sql_extras: str) -> None:
    """Re-applying must be a no-op."""
    created = set(re.findall(r'CREATE POLICY\s+"([^"]+)"', sql_extras))
    dropped = set(re.findall(r'DROP POLICY IF EXISTS\s+"([^"]+)"', sql_extras))
    assert created and created <= dropped, (
        f"policies created without a preceding DROP IF EXISTS: {created - dropped}"
    )
    assert not re.findall(r"CREATE INDEX (?!IF NOT EXISTS)", sql_extras), (
        "every CREATE INDEX must be IF NOT EXISTS"
    )
    assert not re.findall(r"CREATE TABLE (?!IF NOT EXISTS)", sql_extras), (
        "every CREATE TABLE must be IF NOT EXISTS"
    )


def test_extras_carries_the_migration_file_only_banner(sql_extras: str) -> None:
    """The banner is what stops an agent applying this to prod as a side
    effect — application is an explicitly consented, separate step."""
    assert "MIGRATION FILE ONLY" in sql_extras, (
        "missing the 🔴 MIGRATION FILE ONLY banner (see migration 033)"
    )
