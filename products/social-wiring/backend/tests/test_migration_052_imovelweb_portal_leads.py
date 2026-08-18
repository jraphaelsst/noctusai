"""Structural tests for `052_imovelweb_portal_leads.sql`.

Parse-based, like `test_migrations.py`: the SQL is read as text, so these
need no database and no `pglast` (the three `test_migration_04*` files skip
silently without it, which is exactly the coverage gap this style avoids).

They exist for four guarantees that are invisible at runtime until the day
they are not:

1. **The `service_role_bypass` policies are named literally that.** The
   `check_admin_endpoint_service_role_bypass` keeper matches on the NAME, so
   a descriptive one is invisible to it — migration 051 used
   `olx_lead_events_service_role` and is not seen by the keeper at all.
2. **The `integration_accounts` provider CHECK is a SUPERSET of 051's.**
   Both migrations rewrite that constraint by dynamic lookup and the LATER
   one wins outright, so dropping `'olx'` here would break the OLX picker
   the moment 052 runs — with no error from either migration.
3. **No CPF column exists, and the columns that can hold one say so.** The
   LGPD guarantee is a *shape* guarantee: it holds because a column is
   absent, and nothing else would notice it reappearing.
4. **The shared `leads` idempotency pair is guarded**, so 052 is correct
   whether 051 ran, will run, or never runs.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "052_imovelweb_portal_leads.sql"
)

TABLES = ("imovelweb_lead_events", "imovelweb_leads", "imovelweb_agencies")


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


class TestTables:
    @pytest.mark.parametrize("table", TABLES)
    def test_each_table_is_created_idempotently(self, sql, table):
        assert re.search(
            rf"CREATE TABLE IF NOT EXISTS social_wiring\.{table}\b", sql
        ), f"{table} is not created with IF NOT EXISTS"

    def test_the_inbox_is_keyed_on_the_event_not_the_contact(self, sql):
        # `eventId` is the DELIVERY. `originLeadId` is the CONTACT and fans
        # out to several events — keying on it would collapse real leads.
        block = _table_block(sql, "imovelweb_lead_events")
        assert re.search(r"id\s+TEXT PRIMARY KEY", block)

    def test_the_inbox_org_is_nullable(self, sql):
        # NULL org_id IS the `unresolved` state: the tenant could not be
        # determined and NOTHING was written, rather than guessed.
        block = _table_block(sql, "imovelweb_lead_events")
        assert re.search(r"org_id\s+UUID,", block), "org_id must be nullable"

    def test_the_ledger_org_is_not_null(self, sql):
        # A ledger row always belongs to a resolved tenant — it is only
        # written once the org is known.
        block = _table_block(sql, "imovelweb_leads")
        assert re.search(r"org_id\s+UUID NOT NULL", block)

    def test_the_agency_index_is_not_unique(self, sql):
        # One org legitimately holds several agency codes (a group with
        # several imobiliárias, or one per brand).
        assert "CREATE INDEX IF NOT EXISTS idx_sw_imovelweb_agencies_org" in sql
        assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_sw_imovelweb_agencies_org" not in sql


class TestRls:
    @pytest.mark.parametrize("table", TABLES)
    def test_rls_is_enabled(self, sql, table):
        assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY" in sql

    @pytest.mark.parametrize("table", TABLES)
    def test_the_select_policy_is_org_scoped(self, sql, table):
        # `\s+` not a literal space: the longer table names wrap the
        # `ON social_wiring.…` onto the next line, and a space-only pattern
        # would pass for two tables and fail for the third — which is a
        # test that reports formatting, not policy.
        assert re.search(
            rf'CREATE POLICY "{table}_select_own_org"\s+ON social_wiring\.{table}',
            sql,
        )

    @pytest.mark.parametrize("table", TABLES)
    def test_the_bypass_policy_uses_the_literal_keeper_name(self, sql, table):
        """🔴 The keeper matches the LITERAL name `service_role_bypass`.

        Migration 051 named its equivalents `olx_lead_events_service_role` /
        `olx_leads_service_role`, which are functionally identical and
        invisible to `check_admin_endpoint_service_role_bypass`. A policy the
        keeper cannot see is a policy nobody is checking.
        """
        assert re.search(
            rf'CREATE POLICY "service_role_bypass" ON social_wiring\.{table}', sql
        ), f"{table} must name its bypass policy literally `service_role_bypass`"


class TestSharedIdempotencyKey:
    def test_the_leads_columns_are_added_guarded(self, sql):
        # 051 adds these too. IF NOT EXISTS makes 052 correct whether 051
        # ran, will run, or never runs.
        assert "ADD COLUMN IF NOT EXISTS external_source" in sql
        assert "ADD COLUMN IF NOT EXISTS external_lead_id" in sql

    def test_the_unique_index_is_guarded_and_partial(self, sql):
        assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_leads_org_external_lead" in sql
        # Partial: the vast majority of leads are spreadsheet imports with no
        # external id, and they must not collide with each other on NULL.
        assert "WHERE external_lead_id IS NOT NULL" in sql

    def test_no_third_per_source_column_is_introduced(self, sql):
        # 041 added `meta_lead_id`; 051 replaced that approach with the
        # generic pair. A third would make it a pattern.
        assert "imovelweb_lead_id" not in sql


class TestProviderCheckOrdering:
    def test_the_constraint_is_dropped_by_dynamic_lookup(self, sql):
        # Migration 005 declared it inline, so its name is whatever Postgres
        # generated on that database; a named DROP silently no-ops.
        assert "pg_get_constraintdef(con.oid) LIKE '%provider%'" in sql

    def test_the_provider_list_is_a_superset_of_051s(self, sql):
        """🔴 The ordering hazard, and the reason this test exists.

        Both 051 and 052 rewrite this CHECK by dynamic lookup, and the LATER
        one wins outright. So 052's list must contain everything 051's did —
        dropping `'olx'` here would break the OLX account picker the moment
        052 runs, and neither migration would report anything.
        """
        match = re.search(
            r"ADD CONSTRAINT integration_accounts_provider_check\s*\n\s*CHECK \(provider IN \(([^)]*)\)",
            sql,
        )
        assert match, "the provider CHECK was not found in its expected shape"
        declared = {p.strip().strip("'") for p in match.group(1).split(",") if p.strip()}

        # 051's list, verbatim.
        required = {
            "youtube", "google_drive", "gmail", "meta", "n8n", "instagram", "olx",
        }
        assert required <= declared, (
            f"052 drops provider(s) {sorted(required - declared)} that 051 allows; "
            "the later migration wins, so this silently breaks them"
        )
        assert "imovelweb" in declared


class TestLgpdShape:
    def test_there_is_no_cpf_column(self, sql):
        """The minimization guarantee is a SHAPE guarantee: it holds because
        the column is absent, and nothing at runtime would notice it coming
        back.

        Comments are stripped first. The migration deliberately CONTAINS the
        string `identification_id` — in a comment explaining why there is no
        such column — so a raw text search would fail on the very prose that
        documents the guarantee.
        """
        assert "identification_id" not in _strip_comments(sql)

    def test_the_prose_explaining_the_omission_survives(self, sql):
        # Guards the guard: if someone deletes the comment, the test above
        # still passes and the next reader has no idea the omission was
        # deliberate rather than forgotten.
        assert "NO `identification_id` column" in sql

    @pytest.mark.parametrize(
        "column",
        [
            "social_wiring.imovelweb_lead_events.payload",
            "social_wiring.imovelweb_leads.raw",
        ],
    )
    def test_the_cpf_bearing_columns_are_commented(self, sql, column):
        # These two ARE personal data — the CPF survives inside them even
        # though it is never projected. The COMMENT is what tells the next
        # reader that, and what a schema dump carries.
        assert f"COMMENT ON COLUMN {column} IS" in sql
        block = sql.split(f"COMMENT ON COLUMN {column} IS", 1)[1][:400]
        assert "CPF" in block

    def test_smartlead_is_nullable(self, sql):
        # Enrichment sits downstream of the durable write; its failure must
        # be a degradation, never a lost lead.
        block = _table_block(sql, "imovelweb_leads")
        assert re.search(r"smartlead\s+JSONB,", block), (
            "smartlead must be nullable — a NOT NULL would make enrichment "
            "failure block the ledger write"
        )


class TestDeliverySemantics:
    def test_the_source_check_names_both_paths(self, sql):
        # The reconcile share is the operator-visible symptom of missing the
        # vendor's 1.5s budget, so the column has to distinguish them.
        assert "source IN ('callback', 'reconcile')" in sql

    def test_the_status_check_matches_the_service_constants(self, sql):
        from app.modules.portal_leads.services.imovelweb_webhook_service import (
            PENDING_STATUSES,
            STATUS_IGNORED,
            STATUS_PROCESSED,
        )

        match = re.search(r"status IN \(([^)]*)\)", sql)
        assert match
        declared = {s.strip().strip("'") for s in match.group(1).split(",")}
        expected = set(PENDING_STATUSES) | {STATUS_PROCESSED, STATUS_IGNORED}
        assert declared == expected, (
            "the migration's CHECK and the service's status constants have "
            f"drifted: SQL={sorted(declared)} vs code={sorted(expected)}"
        )

    def test_the_drain_predicate_has_a_matching_partial_index(self, sql):
        from app.modules.portal_leads.services.imovelweb_webhook_service import (
            PENDING_STATUSES,
        )

        assert "idx_sw_imovelweb_lead_events_pending" in sql
        for status in PENDING_STATUSES:
            assert f"'{status}'" in sql


def _strip_comments(sql: str) -> str:
    """Drop `--` line comments. Crude on purpose: this migration has no
    string literal containing `--`, and a real SQL parser here would mean a
    dependency that makes the test skip silently (which is precisely what
    the `pglast`-gated migration tests already do)."""
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def _table_block(sql: str, table: str) -> str:
    """The `CREATE TABLE …( … )` body for one table."""
    start = sql.index(f"CREATE TABLE IF NOT EXISTS social_wiring.{table}")
    return sql[start : sql.index(");", start)]
