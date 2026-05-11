"""Static-analysis idempotency + shape tests for migrations 029 + 030.

These migrations close the keeper-trio findings for core (Wave 1 child A
of `projects/keeper-trio-platform-triage/`):

- **029_billing_events.sql** — creates `public.billing_events` (Stripe
  webhook audit log) that `app/routers/billing.py:284` writes to. Closes
  the unknown_table REAL_BUG.
- **030_service_role_bypass_backfill.sql** — adds canonical
  `service_role_bypass` policies to 12 admin-touched tables that
  already have ``<table>_service`` policies but were flagged by the
  detector because the policy NAME literal didn't match.

The unit-level guard here:

1. Migration files exist at the canonical paths.
2. 029 creates `public.billing_events` with the expected shape (PK,
   columns, RLS enabled).
3. Every CREATE POLICY line uses the LITERAL name
   ``service_role_bypass`` (the keeper detector requires this).
4. 030 covers every table identified in
   ``projects/keeper-trio-platform-triage/phase-0-triage.md`` core
   section.
5. Every policy uses the canonical
   ``FOR ALL TO service_role USING (true) WITH CHECK (true)`` shape
   emitted by ``noctusai_lib.sql.service_role_bypass``.
6. Both migrations are idempotent (DROP POLICY IF EXISTS guards).

A drift-detection test guards against the helper canonical shape
changing under us — we re-emit each policy via the helper and
byte-compare.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
MIGRATION_029 = MIGRATIONS_DIR / "029_billing_events.sql"
MIGRATION_030 = MIGRATIONS_DIR / "030_service_role_bypass_backfill.sql"

# Tables backfilled by 030 (from phase-0-triage.md, core section, table
# counts in the DEFENSE_IN_DEPTH cluster). billing_events is covered by
# 029 — not in this list.
BACKFILL_TABLES_030 = [
    "noctus_users",
    "subscriptions",
    "roles",
    "licenses",
    "plans",
    "webhook_endpoints",
    "webhook_deliveries",
    "org_settings",
    "audit_logs",
    "api_keys",
    "platform_settings",
    "notifications",
]


# Load the seed helper for drift testing. The helper lives at
# seed/lib/backend/noctusai_lib/sql/service_role_bypass.py.
_SEED_LIB = Path(__file__).resolve().parents[4] / "seed" / "lib" / "backend"
if str(_SEED_LIB) not in sys.path:
    sys.path.insert(0, str(_SEED_LIB))


class TestMigration029BillingEvents:
    def test_file_exists(self):
        assert MIGRATION_029.exists(), (
            f"Migration 029 missing at {MIGRATION_029}. "
            "Closes the billing_events unknown_table REAL_BUG."
        )

    def test_creates_billing_events_table(self):
        sql = MIGRATION_029.read_text()
        assert re.search(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.billing_events",
            sql,
            re.IGNORECASE,
        ), "029 must create public.billing_events with IF NOT EXISTS guard."

    def test_billing_events_has_pk_on_stripe_event_id(self):
        sql = MIGRATION_029.read_text()
        # PK is declared on the column line.
        assert re.search(
            r"stripe_event_id\s+TEXT\s+PRIMARY\s+KEY", sql, re.IGNORECASE
        ), (
            "billing_events.stripe_event_id must be PRIMARY KEY — the "
            "Stripe event id is the idempotency anchor."
        )

    def test_billing_events_required_columns(self):
        sql = MIGRATION_029.read_text()
        for col in ("event_type", "stripe_customer_id", "org_id", "payload", "created_at"):
            assert re.search(
                rf"\b{col}\b", sql, re.IGNORECASE
            ), f"billing_events column {col!r} missing from migration 029."

    def test_billing_events_rls_enabled(self):
        sql = MIGRATION_029.read_text()
        assert re.search(
            r"ALTER\s+TABLE\s+public\.billing_events\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
            sql,
            re.IGNORECASE,
        ), "billing_events must ENABLE ROW LEVEL SECURITY."

    def test_billing_events_has_service_role_bypass_policy(self):
        sql = MIGRATION_029.read_text()
        # Match the canonical policy line — keeper detector keys on
        # the LITERAL policy name `service_role_bypass`.
        assert re.search(
            r'CREATE\s+POLICY\s+"service_role_bypass"\s+ON\s+public\.billing_events\s+'
            r"FOR\s+ALL\s+TO\s+service_role\s+USING\s*\(true\)\s+WITH\s+CHECK\s*\(true\)",
            sql,
            re.IGNORECASE,
        ), (
            "029 must create the canonical service_role_bypass policy on "
            "public.billing_events. The policy NAME literal is required by "
            "check_admin_endpoint_service_role_bypass — renaming re-opens "
            "the keeper finding."
        )

    def test_idempotent_drop_policy_guard(self):
        sql = MIGRATION_029.read_text()
        assert re.search(
            r'DROP\s+POLICY\s+IF\s+EXISTS\s+"service_role_bypass"\s+ON\s+public\.billing_events',
            sql,
            re.IGNORECASE,
        ), "029 must guard CREATE POLICY with DROP POLICY IF EXISTS so re-apply is no-op."


class TestMigration030ServiceRoleBypassBackfill:
    def test_file_exists(self):
        assert MIGRATION_030.exists(), (
            f"Migration 030 missing at {MIGRATION_030}. "
            "Closes the 149 DEFENSE_IN_DEPTH keeper findings for core."
        )

    def test_covers_every_backfill_table(self):
        sql = MIGRATION_030.read_text()
        for table in BACKFILL_TABLES_030:
            assert re.search(
                rf'CREATE\s+POLICY\s+"service_role_bypass"\s+ON\s+public\.{re.escape(table)}\b',
                sql,
                re.IGNORECASE,
            ), (
                f"030 missing CREATE POLICY on public.{table}. "
                "Backfill must cover every admin-touched core table from "
                "phase-0-triage.md."
            )

    def test_every_policy_uses_canonical_shape(self):
        """Every CREATE POLICY must use the literal name + canonical shape."""
        sql = MIGRATION_030.read_text()
        policy_lines = [
            line for line in sql.splitlines()
            if "CREATE POLICY" in line.upper()
            and not line.lstrip().startswith("--")
        ]
        # 12 backfill tables → 12 policies in 030.
        assert len(policy_lines) == len(BACKFILL_TABLES_030), (
            f"Expected {len(BACKFILL_TABLES_030)} policies, got {len(policy_lines)}. "
            "Each backfill table requires exactly one canonical policy."
        )
        for line in policy_lines:
            assert re.search(
                r'CREATE\s+POLICY\s+"service_role_bypass"\s+ON\s+public\.[A-Za-z_]+\s+'
                r"FOR\s+ALL\s+TO\s+service_role\s+USING\s*\(true\)\s+WITH\s+CHECK\s*\(true\)",
                line,
                re.IGNORECASE,
            ), f"Policy line does not match canonical shape: {line!r}"

    def test_idempotent_drop_policy_guards(self):
        sql = MIGRATION_030.read_text()
        drop_guards = re.findall(
            r'DROP\s+POLICY\s+IF\s+EXISTS\s+"service_role_bypass"\s+ON\s+public\.[A-Za-z_]+',
            sql,
            re.IGNORECASE,
        )
        assert len(drop_guards) == len(BACKFILL_TABLES_030), (
            f"Expected {len(BACKFILL_TABLES_030)} DROP POLICY IF EXISTS guards, "
            f"got {len(drop_guards)}. Every CREATE POLICY needs a sibling "
            "DROP guard for idempotent re-apply."
        )

    def test_does_not_include_billing_events_policy(self):
        """billing_events is covered by 029, not 030. Avoid duplicate policies."""
        sql = MIGRATION_030.read_text()
        # Strip comments before scanning — billing_events appears in
        # explanatory comments (table list) but must not appear in any
        # executable statement.
        body_lines = [
            line for line in sql.splitlines()
            if not line.lstrip().startswith("--")
        ]
        body = "\n".join(body_lines)
        assert "billing_events" not in body, (
            "billing_events policy must not appear in 030's executable SQL — "
            "it's covered by 029. Duplicating would be confusing (which "
            "migration owns it?)."
        )


class TestPolicyShapeMatchesSeedHelper:
    """Drift guard: every policy line must be byte-equal to the helper output.

    The seed helper at `noctusai_lib.sql.service_role_bypass(table, schema)`
    is the canonical source. If the helper string changes (e.g. someone
    adds `IF NOT EXISTS`), this test fires + test_sql_templates fires
    simultaneously.
    """
    def test_029_billing_events_policy_matches_helper(self):
        from noctusai_lib.sql import service_role_bypass

        expected = service_role_bypass("billing_events", schema="public")
        sql = MIGRATION_029.read_text()
        assert expected in sql, (
            f"029 service_role_bypass line does not match seed helper output.\n"
            f"Expected: {expected!r}\n"
            "If the helper changed, regenerate 029."
        )

    def test_030_every_backfill_policy_matches_helper(self):
        from noctusai_lib.sql import service_role_bypass

        sql = MIGRATION_030.read_text()
        for table in BACKFILL_TABLES_030:
            expected = service_role_bypass(table, schema="public")
            assert expected in sql, (
                f"030 service_role_bypass line for {table!r} does not match "
                f"seed helper output.\nExpected: {expected!r}"
            )
