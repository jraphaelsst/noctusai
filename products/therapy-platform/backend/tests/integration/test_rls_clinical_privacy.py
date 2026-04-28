"""Schema-level regression guard for the clinical-privacy RLS contract.

Introduced 2026-04-22 by `projects/compliance-audit-reconciliation/` Phase 3
after dropping `platform_admin` (and `clinic_admin` on clinical_longitudinal)
from clinical-table RLS policies per user Q2 decision + `GRAVACAO_SESSOES_LEGAL.md`.

This test parses the authoritative migration files and asserts that the
LATEST policy definition for each clinical table does NOT grant access to
the dropped roles. Works against the migration files (not the live DB) so
it remains a deterministic offline check that runs on every clone.

If a future migration re-adds `platform_admin` or `clinic_admin` to any of
the guarded clinical-table policies, this test fails — surfacing the drift
before it ships. Same "no silent errors" lens that fired on finding 3.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

CLINICAL_TABLES = [
    "session_records",
    "session_summary_versions",
    "session_observations",
    "session_audio_segments",
    "session_interruptions",
    "patient_session_notes",
    "clinical_longitudinal_analyses",
    "patient_longitudinal_analyses",
]

EXTRA_DENIED_ROLES_PER_TABLE: dict[str, list[str]] = {
    "clinical_longitudinal_analyses": ["clinic_admin"],
}

DENIED_ROLE_FOR_CLINICAL = "platform_admin"


def _latest_policy_body(table: str) -> str:
    """Return the CREATE POLICY block body for the latest definition of the
    given clinical table's policy across all migration files.

    Policies accumulate chronologically across migrations: the LAST
    CREATE POLICY for a table is the one currently in force.
    """
    policy_pattern = re.compile(
        rf"CREATE\s+POLICY\s+\w+\s+ON\s+therapy\.{table}\b[^;]*?USING\s*\(([^;]*?)\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    latest_body: str | None = None
    for mig_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        content = mig_file.read_text()
        for match in policy_pattern.finditer(content):
            latest_body = match.group(1)
    if latest_body is None:
        pytest.fail(
            f"Could not locate a CREATE POLICY ... USING(...) for therapy.{table} "
            f"in any migration. Either the table doesn't use RLS, or the regex "
            f"needs updating for new DDL patterns."
        )
    return latest_body


class TestClinicalRlsPrivacy:
    @pytest.mark.parametrize("table", CLINICAL_TABLES)
    def test_platform_admin_not_in_clinical_policy(self, table: str):
        """platform_admin must not appear in any clinical-table policy body."""
        body = _latest_policy_body(table)
        assert DENIED_ROLE_FOR_CLINICAL not in body, (
            f"therapy.{table}'s latest CREATE POLICY body references "
            f"'{DENIED_ROLE_FOR_CLINICAL}' — violates the clinical-privacy "
            f"contract locked 2026-04-22 by `compliance-audit-reconciliation`. "
            f"Policy body:\n\n{body}"
        )

    @pytest.mark.parametrize(
        "table,role",
        [(t, r) for t, roles in EXTRA_DENIED_ROLES_PER_TABLE.items() for r in roles],
    )
    def test_extra_denied_roles_per_table(self, table: str, role: str):
        """Per-table extra denials (clinical_longitudinal_analyses drops clinic_admin)."""
        body = _latest_policy_body(table)
        assert role not in body, (
            f"therapy.{table}'s latest CREATE POLICY body references '{role}' — "
            f"violates the Q2 decision that clinical_longitudinal_analyses is "
            f"therapist-only (no clinic_admin). Policy body:\n\n{body}"
        )
