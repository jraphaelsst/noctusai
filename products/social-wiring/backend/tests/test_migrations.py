"""
Structural (parse-based) tests for `migrations/001_social-wiring.sql`.

No database required — these tests read the SQL migration file as text and
assert that the expected structural elements are declared. They catch
regressions like "someone deleted a policy" or "renamed a column" before
they hit a real Supabase instance.

Scoped to the `social_wiring.api_tokens` table added by the
platform-auth-modernization Wave 1 (E-MIGRATION, 2026-05-20). Extend this
file with additional table-level static assertions as needed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "migrations" / "001_social-wiring.sql"
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
