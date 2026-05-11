"""
Structural (parse-based) tests for ``migrations/001_imobi_scheduling.sql``.

These tests read the SQL file as text and assert that the expected
tables / RLS policies / triggers / indexes / constraints are declared.
No database is required — they catch regressions like deleted columns,
renamed policies, or stripped triggers before they reach a real
Supabase instance.

For full correctness (actual migration running cleanly against
Postgres), the live ``realdb`` test suite runs against a staging DB.

Pattern lifted from ``products/erp-imobiliario/backend/tests/test_metas_migration.py``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "migrations" / "001_imobi_scheduling.sql"
)

# ---------------------------------------------------------------------------
# Module-scoped SQL fixture (read once)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"Migration file missing at {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Schema lock + grants
# ---------------------------------------------------------------------------


def test_schema_search_path_pinned(sql: str) -> None:
    assert "SET search_path = imobi_scheduling, public;" in sql


def test_schema_created(sql: str) -> None:
    assert "CREATE SCHEMA IF NOT EXISTS imobi_scheduling" in sql


def test_schema_grants_authenticated(sql: str) -> None:
    # PostgREST needs USAGE on the schema for `authenticated` users
    assert "GRANT USAGE ON SCHEMA imobi_scheduling TO anon, authenticated, service_role;" in sql


# ---------------------------------------------------------------------------
# Shared updated_at function (declared once per schema)
# ---------------------------------------------------------------------------


def test_set_updated_at_function_declared(sql: str) -> None:
    assert re.search(
        r"CREATE OR REPLACE FUNCTION imobi_scheduling\.set_updated_at\(\)",
        sql,
    )


def test_updated_at_function_has_security_definer(sql: str) -> None:
    # SECURITY DEFINER + pinned search_path is the platform standard for
    # trigger-firing functions (prevents search-path hijacking).
    assert "SECURITY DEFINER" in sql
    assert "SET search_path = imobi_scheduling, public" in sql


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

EXPECTED_DOMAIN_TABLES = [
    "users",
    "condominiums",
    "properties",
    "services",
    "crew_skills",
    "appointment_requests",
    "appointment_request_services",
    "route_groups",
    "appointments",
    "conversation_messages",
    "conversation_summaries",
    "pending_chat_identities",
    "oauth_credentials",
    "routes",
    "tool_call_audits",
]


@pytest.mark.parametrize("table", EXPECTED_DOMAIN_TABLES)
def test_table_is_created(sql: str, table: str) -> None:
    pattern = rf"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+imobi_scheduling\.{re.escape(table)}\s*\("
    assert re.search(pattern, sql), f"Missing CREATE TABLE for imobi_scheduling.{table}"


@pytest.mark.parametrize("table", EXPECTED_DOMAIN_TABLES)
def test_table_has_rls_enabled(sql: str, table: str) -> None:
    pattern = rf"ALTER TABLE\s+imobi_scheduling\.{re.escape(table)}\s+ENABLE ROW LEVEL SECURITY"
    assert re.search(pattern, sql), f"RLS not enabled for imobi_scheduling.{table}"


# ---------------------------------------------------------------------------
# RLS policy shape — org-bound + subquery jwt() form
# ---------------------------------------------------------------------------

# Every domain table (single-agency v1) at minimum gets a SELECT policy
# bound to the JWT's org_id claim. WITH-CHECK on UPDATE is asserted
# separately below.
ORG_BOUND_TABLES = [t for t in EXPECTED_DOMAIN_TABLES]


@pytest.mark.parametrize("table", ORG_BOUND_TABLES)
def test_table_has_org_scoped_select_policy(sql: str, table: str) -> None:
    # Locate ANY SELECT policy on this table (policy name is not
    # constrained — the M2M tables use a "via parent" naming scheme),
    # then verify the org-id-from-jwt subquery appears in its body.
    pattern = (
        rf'CREATE POLICY "[^"]+"\s+ON\s+imobi_scheduling\.{re.escape(table)}\s+'
        rf"FOR SELECT TO authenticated.*?"
        rf"\(\(SELECT auth\.jwt\(\)\) ->> 'org_id'\)::uuid"
    )
    assert re.search(pattern, sql, re.DOTALL), (
        f"{table}: missing org-scoped SELECT policy (org_id-from-jwt subquery)"
    )


# Tables that allow mutations — assert WITH CHECK on UPDATE policies.
UPDATE_GUARDED_TABLES = [
    "users",
    "condominiums",
    "properties",
    "services",
    "appointment_requests",
    "route_groups",
    "appointments",
    "pending_chat_identities",
    "oauth_credentials",
    "routes",
]


@pytest.mark.parametrize("table", UPDATE_GUARDED_TABLES)
def test_update_policy_has_with_check(sql: str, table: str) -> None:
    # Find the UPDATE policy body for this table and ensure it ships
    # ``WITH CHECK`` (the Engineer-D ERP lesson — UPDATE guards new
    # values, not just pre-image).
    #
    # Strategy: locate the policy by name, capture text up to the
    # next ``CREATE`` statement (or end of file), and assert both
    # ``FOR UPDATE`` and ``WITH CHECK`` appear in that slice. Nested
    # parens in the policy body (``((SELECT auth.jwt()) ->> ...)``)
    # rule out a naïve ``[^)]+`` shape.
    pattern = (
        rf'CREATE POLICY "{re.escape(table)}_update_org"\s+ON\s+imobi_scheduling\.{re.escape(table)}.*?'
        rf"(?=CREATE POLICY|CREATE INDEX|CREATE OR REPLACE TRIGGER|CREATE TABLE|--\s*===)"
    )
    match = re.search(pattern, sql, re.DOTALL)
    assert match, f"{table}: could not locate UPDATE policy block"
    block = match.group(0)
    assert "FOR UPDATE TO authenticated" in block, (
        f"{table}: UPDATE policy not bound to authenticated role"
    )
    assert "USING" in block, f"{table}: UPDATE policy missing USING clause"
    assert "WITH CHECK" in block, (
        f"{table}: UPDATE policy missing WITH CHECK clause"
    )


# Append-only tables explicitly omit UPDATE policies.
APPEND_ONLY_TABLES = ["conversation_messages", "tool_call_audits"]


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_append_only_table_has_no_update_policy(sql: str, table: str) -> None:
    pattern = rf'CREATE POLICY "[^"]*"\s+ON\s+imobi_scheduling\.{re.escape(table)}\s+FOR UPDATE'
    assert not re.search(pattern, sql), (
        f"{table} is append-only; UPDATE policy must not be declared"
    )


# ---------------------------------------------------------------------------
# updated_at triggers (per-table)
# ---------------------------------------------------------------------------

TRIGGER_TABLES = [
    "users",
    "condominiums",
    "properties",
    "services",
    "appointment_requests",
    "route_groups",
    "appointments",
    "pending_chat_identities",
    "oauth_credentials",
    "routes",
]


@pytest.mark.parametrize("table", TRIGGER_TABLES)
def test_updated_at_trigger_declared(sql: str, table: str) -> None:
    pattern = (
        rf"CREATE OR REPLACE TRIGGER set_updated_at_{re.escape(table)}\s+"
        rf"BEFORE UPDATE ON imobi_scheduling\.{re.escape(table)}\s+"
        rf"FOR EACH ROW EXECUTE FUNCTION imobi_scheduling\.set_updated_at\(\);"
    )
    assert re.search(pattern, sql), (
        f"{table}: missing BEFORE-UPDATE trigger wiring to set_updated_at()"
    )


# ---------------------------------------------------------------------------
# Foreign keys + constraints
# ---------------------------------------------------------------------------


def test_users_auth_users_fk(sql: str) -> None:
    # auth.users FK with ON DELETE SET NULL (auth.users may be deleted
    # before product cleanup; keep the product row, drop the link).
    assert re.search(
        r"auth_user_id UUID REFERENCES auth\.users\(id\) ON DELETE SET NULL",
        sql,
    )


def test_properties_fk_to_condominiums(sql: str) -> None:
    assert re.search(
        r"condominium_id UUID NOT NULL REFERENCES imobi_scheduling\.condominiums\(id\) ON DELETE CASCADE",
        sql,
    )


def test_appointment_requests_requester_fk(sql: str) -> None:
    # ON DELETE RESTRICT — protect bookings from accidental cascade.
    assert re.search(
        r"requester_user_id UUID NOT NULL REFERENCES imobi_scheduling\.users\(id\) ON DELETE RESTRICT",
        sql,
    )


def test_appointment_end_after_start_constraint(sql: str) -> None:
    # Domain invariant — booking duration must be positive.
    assert "CHECK (end_at > start_at)" in sql


def test_users_role_check_constraint(sql: str) -> None:
    assert re.search(
        r"role TEXT NOT NULL CHECK \(role IN \('real_estate_agent', 'media_crew', 'admin'\)\)",
        sql,
    )


# ---------------------------------------------------------------------------
# Uniqueness invariants
# ---------------------------------------------------------------------------


def test_unique_phone_per_org(sql: str) -> None:
    assert re.search(r"UNIQUE\s*\(org_id,\s*phone_number\)", sql)


def test_unique_property_code_per_org(sql: str) -> None:
    assert re.search(r"UNIQUE\s*\(org_id,\s*code\)", sql)


def test_unique_route_per_org_pair_provider(sql: str) -> None:
    # Routes cache dedupe key — (org_id, origin, destination, provider).
    assert re.search(
        r"UNIQUE\s*\(\s*org_id,\s*origin_place_id,\s*destination_place_id,\s*provider\s*\)",
        sql,
    )


def test_pending_chat_identity_unique_per_org(sql: str) -> None:
    assert re.search(r"UNIQUE\s*\(org_id,\s*chat_id\)", sql)


# ---------------------------------------------------------------------------
# Indexes — spot-check the most-queried paths
# ---------------------------------------------------------------------------


def test_index_users_phone(sql: str) -> None:
    assert "CREATE INDEX idx_imobi_users_phone ON imobi_scheduling.users(phone_number)" in sql


def test_index_users_linked_identity(sql: str) -> None:
    # LID-aware authorization runs lookups against this index.
    assert (
        "CREATE INDEX idx_imobi_users_linked_identity"
        " ON imobi_scheduling.users(linked_identity)" in sql
    )


def test_index_appointments_start_end(sql: str) -> None:
    assert "CREATE INDEX idx_imobi_appointments_start ON imobi_scheduling.appointments(start_at)" in sql
    assert "CREATE INDEX idx_imobi_appointments_end ON imobi_scheduling.appointments(end_at)" in sql


def test_index_conv_messages_provider_id_unique(sql: str) -> None:
    # provider_message_id is UNIQUE — supports idempotency on WAHA replays.
    assert re.search(r"provider_message_id TEXT UNIQUE", sql)


# ---------------------------------------------------------------------------
# tool_call_audits — seed-template parity (LGPD-sensitive fields preserved)
# ---------------------------------------------------------------------------


def test_tool_call_audits_arguments_jsonb(sql: str) -> None:
    # JSONB shape lifted from the seed template — products may redact
    # arguments at write time per LGPD.
    pattern = (
        r"CREATE TABLE imobi_scheduling\.tool_call_audits\s*\(.*?arguments\s+JSONB"
    )
    assert re.search(pattern, sql, re.DOTALL)


def test_tool_call_audits_result_jsonb(sql: str) -> None:
    pattern = (
        r"CREATE TABLE imobi_scheduling\.tool_call_audits\s*\(.*?result\s+JSONB"
    )
    assert re.search(pattern, sql, re.DOTALL)


# ---------------------------------------------------------------------------
# Append-only invariants — explicit absence of UPDATE policies
# ---------------------------------------------------------------------------


def test_tool_call_audits_append_only(sql: str) -> None:
    # No UPDATE policy on the audit table — rows are immutable once written.
    pattern = (
        r'CREATE POLICY "tool_call_audits[^"]*"\s+ON\s+imobi_scheduling\.tool_call_audits\s+FOR UPDATE'
    )
    assert not re.search(pattern, sql)


def test_conversation_messages_append_only(sql: str) -> None:
    pattern = (
        r'CREATE POLICY "conversation_messages[^"]*"\s+ON\s+imobi_scheduling\.conversation_messages\s+FOR UPDATE'
    )
    assert not re.search(pattern, sql)
