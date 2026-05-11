"""Unit tests for ``noctusai_lib.sql.service_role_bypass`` + the canonical
``noctusai_lib.domain.sql_templates.service_role_bypass``.

Mirrors the layout of ``test_sql_helpers.py`` + ``test_sql_templates.py``
(flat, in ``tests/``; class-per-concern; class names ``TestXxx``).

Asserts byte-equal output against the canonical adopter
(``products/therapy-platform/backend/migrations/001_therapy_platform.sql``)
because the platform's ``check_admin_endpoint_service_role_bypass``
detector keys on the literal policy NAME — any drift silently re-opens
the 192 DEFENSE_IN_DEPTH findings classified in
``projects/keeper-trio-platform-triage/phase-0-triage.md`` (2026-05-11).
"""
from __future__ import annotations

import pytest

from noctusai_lib.sql import service_role_bypass
from noctusai_lib.domain.sql_templates import (
    service_role_bypass as canonical_service_role_bypass,
)


# ---------------------------------------------------------------------------
# Wrapper-layer (`noctusai_lib.sql.service_role_bypass`)
# ---------------------------------------------------------------------------


class TestServiceRoleBypassWrapper:
    def test_emits_quoted_policy_name(self):
        out = service_role_bypass("clinics", schema="therapy")
        # Literal policy name MUST appear quoted — the keeper detector
        # heuristic depends on the exact string `"service_role_bypass"`.
        assert '"service_role_bypass"' in out

    def test_default_schema_is_public(self):
        # Brief permits "public" or product schema as default. We default
        # to "public" + recommend passing the product schema explicitly.
        # Verify the default does NOT silently fork to a made-up schema.
        out = service_role_bypass("noctus_users")
        assert "ON public.noctus_users" in out

    def test_explicit_schema_used(self):
        out = service_role_bypass("clientes", schema="erp")
        assert "ON erp.clientes" in out

    def test_for_all_to_service_role_present(self):
        out = service_role_bypass("clinics", schema="therapy")
        assert "FOR ALL TO service_role" in out

    def test_using_true_with_check_true(self):
        out = service_role_bypass("clinics", schema="therapy")
        assert "USING (true)" in out
        assert "WITH CHECK (true)" in out

    def test_terminated_with_semicolon_no_trailing_newline(self):
        out = service_role_bypass("clinics", schema="therapy")
        assert out.endswith(";")
        assert not out.endswith("\n")
        assert not out.endswith(";\n")

    def test_dashed_schema_passes_through(self):
        # `personal-finance` schema works the same as canonical helper —
        # Postgres-quoting is the caller's responsibility upstream.
        out = service_role_bypass("recorrentes", schema="personal-finance")
        assert "ON personal-finance.recorrentes" in out

    def test_delegates_to_canonical(self):
        # Wrapper MUST return byte-equal output to the canonical helper;
        # the wrapper is a thin re-export, no formatting drift.
        wrapper_out = service_role_bypass("clinics", schema="therapy")
        canonical_out = canonical_service_role_bypass("clinics", schema="therapy")
        assert wrapper_out == canonical_out

    def test_empty_table_raises(self):
        with pytest.raises(ValueError, match="non-empty table"):
            service_role_bypass("", schema="erp")

    def test_whitespace_table_raises(self):
        with pytest.raises(ValueError, match="non-empty table"):
            service_role_bypass("   ", schema="erp")

    def test_empty_schema_raises(self):
        with pytest.raises(ValueError, match="non-empty schema"):
            service_role_bypass("clinics", schema="")

    def test_whitespace_schema_raises(self):
        with pytest.raises(ValueError, match="non-empty schema"):
            service_role_bypass("clinics", schema="   ")


# ---------------------------------------------------------------------------
# Canonical-layer (`noctusai_lib.domain.sql_templates.service_role_bypass`)
# ---------------------------------------------------------------------------


class TestServiceRoleBypassCanonical:
    def test_byte_equal_to_therapy_canonical_line(self):
        # Exact byte-match against the canonical adopter shape — therapy's
        # migration emits this line 40+ times. Output drift here would
        # silently keep the 192 findings open.
        out = canonical_service_role_bypass("clinics", schema="therapy")
        expected = (
            'CREATE POLICY "service_role_bypass" ON therapy.clinics '
            'FOR ALL TO service_role USING (true) WITH CHECK (true);'
        )
        assert out == expected

    def test_byte_equal_for_erp_table(self):
        # Confirm shape composes correctly for ERP — the Wave 1
        # `keeper-trio-erp` child will emit this for 14 ERP tables.
        out = canonical_service_role_bypass("clientes", schema="erp")
        expected = (
            'CREATE POLICY "service_role_bypass" ON erp.clientes '
            'FOR ALL TO service_role USING (true) WITH CHECK (true);'
        )
        assert out == expected

    def test_byte_equal_for_dashed_pf_schema(self):
        # PF uses dashed schema; helper passes through unchanged.
        out = canonical_service_role_bypass("recorrentes", schema="personal-finance")
        expected = (
            'CREATE POLICY "service_role_bypass" ON personal-finance.recorrentes '
            'FOR ALL TO service_role USING (true) WITH CHECK (true);'
        )
        assert out == expected

    def test_default_schema_is_public(self):
        out = canonical_service_role_bypass("noctus_users")
        # Caller didn't pass schema; canonical default = "public".
        assert out.startswith('CREATE POLICY "service_role_bypass" ON public.noctus_users')

    def test_empty_table_raises(self):
        with pytest.raises(ValueError, match="non-empty table"):
            canonical_service_role_bypass("")

    def test_empty_schema_raises(self):
        with pytest.raises(ValueError, match="non-empty schema"):
            canonical_service_role_bypass("clinics", schema="")


# ---------------------------------------------------------------------------
# Composition: prelude + service_role_bypass — Wave 1 backfill shape
# ---------------------------------------------------------------------------


class TestComposedBackfillShape:
    """Pin the actual usage shape — `prelude(...)` then N
    `service_role_bypass(...)` lines — so the helper composes into a
    valid-looking backfill migration without surprises.

    Wave 1 children (``keeper-trio-{core,erp,mailing,pf}``) will compose
    this exact shape per product, one line per table needing the policy.
    """

    def test_minimal_backfill_shape(self):
        from noctusai_lib.sql import prelude

        body = "\n".join(
            [
                prelude("erp"),
                service_role_bypass("clientes", schema="erp"),
                service_role_bypass("contratos", schema="erp"),
            ]
        )
        # Schema-lock present from prelude.
        assert "SET search_path = erp, public;" in body
        # Both bypass lines present, named.
        assert body.count('CREATE POLICY "service_role_bypass" ON erp.clientes') == 1
        assert body.count('CREATE POLICY "service_role_bypass" ON erp.contratos') == 1

    def test_one_line_per_table(self):
        # Each bypass call emits exactly one line — no trailing newlines
        # that would let consumers accidentally double-blank the output.
        out = service_role_bypass("clinics", schema="therapy")
        assert "\n" not in out


# ---------------------------------------------------------------------------
# Therapy migration regression — verify the helper output appears in the
# real canonical adopter exactly as the helper emits it.
# ---------------------------------------------------------------------------


class TestAgainstTherapyMigration:
    """Loads therapy's canonical migration and asserts that the helper's
    output appears verbatim. If this test fails, either the helper
    drifted OR therapy's migration was modified — investigate the
    diff before adjusting.
    """

    @staticmethod
    def _therapy_migration_text() -> str:
        from pathlib import Path

        # Walk up from tests/ → backend/ → lib/ → seed/ → noc root.
        # Path is fragile to relocation but the test is opportunistic;
        # skip if the migration isn't reachable (e.g. running in a
        # stripped-down install of just `noctusai_lib`).
        here = Path(__file__).resolve()
        for parent in here.parents:
            candidate = (
                parent
                / "products"
                / "therapy-platform"
                / "backend"
                / "migrations"
                / "001_therapy_platform.sql"
            )
            if candidate.exists():
                return candidate.read_text()
        pytest.skip("therapy migration not reachable from test location")

    def test_helper_output_is_in_therapy_migration(self):
        # Therapy uses `service_role_bypass` policy on `therapy.clinics`.
        # Helper output MUST match verbatim, line included.
        text = self._therapy_migration_text()
        line = service_role_bypass("clinics", schema="therapy")
        assert line in text, (
            f"helper output not found verbatim in therapy migration: {line!r}"
        )

    def test_helper_output_appears_multiple_times_for_multiple_tables(self):
        # Sanity check: therapy applies the policy to 30+ tables.
        # Helper should reproduce at least 5 of them byte-equal.
        text = self._therapy_migration_text()
        sample_tables = [
            "clinics",
            "therapist_profiles",
            "patient_profiles",
            "appointments",
            "wallets",
        ]
        for table in sample_tables:
            line = service_role_bypass(table, schema="therapy")
            assert line in text, (
                f"helper output for {table!r} missing from therapy migration"
            )
