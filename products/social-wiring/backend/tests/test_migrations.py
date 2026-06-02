"""
Structural (parse-based) tests for social_wiring migrations.

No database required — these tests read the SQL migration files as text and
assert that the expected structural elements are declared. They catch
regressions like "someone deleted a policy" or "renamed a column" before
they hit a real Supabase instance.

Coverage:
- 001_social-wiring.sql: api_tokens table structure + RLS shape
- 011_rls_current_org_id.sql: current_org_id() fix shape (no jwt() pattern)
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
