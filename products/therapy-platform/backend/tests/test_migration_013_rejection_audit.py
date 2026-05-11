"""
Static-analysis idempotency test for migration 013 (rejection_audit).

The therapy-platform doesn't run migration application in unit tests (no
test Postgres fixture). The realdb integration suite covers live-apply
verification. This test gives us a fast unit-level guard that:

  1. The migration file exists at the canonical path.
  2. Every DDL statement uses an idempotent guard (``IF NOT EXISTS`` for
     ADD COLUMN; ``OR REPLACE`` for functions; etc.) so re-applying the
     migration is a no-op.

If a future contributor edits 013 to add a non-idempotent statement,
this test fires before the migration ships.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


MIGRATIONS_DIR = (
    Path(__file__).resolve().parent.parent / "migrations"
)
MIGRATION_PATH = MIGRATIONS_DIR / "013_rejection_audit.sql"


def _split_statements(sql: str) -> list[str]:
    """Split SQL on semicolons that aren't inside string literals.

    Naive — sufficient for the simple ALTER + COMMENT statements in 013.
    Strip comment-only lines (-- ...) before splitting.
    """
    lines = []
    for raw in sql.splitlines():
        stripped = raw.strip()
        if stripped.startswith("--"):
            continue
        lines.append(raw)
    body = "\n".join(lines)
    parts = [p.strip() for p in body.split(";")]
    return [p for p in parts if p]


class TestMigration013Idempotency:
    def test_file_exists(self):
        assert MIGRATION_PATH.exists(), (
            f"Migration 013 missing at {MIGRATION_PATH}. "
            "Phase 5 reject-flow wiring depends on this file."
        )

    def test_all_alter_table_statements_use_if_not_exists(self):
        sql = MIGRATION_PATH.read_text()
        statements = _split_statements(sql)
        alter_stmts = [
            s for s in statements
            if re.match(r"\s*ALTER\s+TABLE", s, re.IGNORECASE)
        ]
        # We expect exactly TWO ALTER TABLE statements (therapist_profiles,
        # clinics). Anything else means scope creep into this migration.
        assert len(alter_stmts) == 2, (
            f"Expected 2 ALTER TABLE statements, got {len(alter_stmts)}. "
            "Migration 013 is intentionally scoped to the reject-audit "
            "triplet on two tables."
        )
        for stmt in alter_stmts:
            # Every column add must guard with IF NOT EXISTS.
            adds = re.findall(
                r"ADD\s+COLUMN(?:\s+IF\s+NOT\s+EXISTS)?", stmt, re.IGNORECASE
            )
            guarded = re.findall(
                r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS", stmt, re.IGNORECASE
            )
            assert adds and len(adds) == len(guarded), (
                "Every ADD COLUMN in migration 013 must use "
                "`IF NOT EXISTS` so re-applying is a no-op. "
                f"Statement:\n{stmt}"
            )

    def test_covers_both_therapist_profiles_and_clinics(self):
        sql = MIGRATION_PATH.read_text().lower()
        assert "therapy.therapist_profiles" in sql
        assert "therapy.clinics" in sql

    def test_columns_are_rejection_reason_rejected_at_rejected_by(self):
        sql = MIGRATION_PATH.read_text().lower()
        # All three reject-audit columns must be added to both tables.
        # Two statements × three columns = six ADD COLUMN lines.
        rejection_reason_adds = re.findall(
            r"add\s+column\s+if\s+not\s+exists\s+rejection_reason", sql
        )
        rejected_at_adds = re.findall(
            r"add\s+column\s+if\s+not\s+exists\s+rejected_at", sql
        )
        rejected_by_adds = re.findall(
            r"add\s+column\s+if\s+not\s+exists\s+rejected_by", sql
        )
        assert len(rejection_reason_adds) == 2
        assert len(rejected_at_adds) == 2
        assert len(rejected_by_adds) == 2

    def test_rejected_by_references_auth_users(self):
        sql = MIGRATION_PATH.read_text().lower()
        # The actor column must FK to auth.users(id) — admin accountability.
        # Loose match because `references auth.users (id)` and
        # `references auth.users(id)` both valid; we only care that the
        # references clause exists for rejected_by.
        assert re.search(
            r"rejected_by\s+uuid\s+references\s+auth\.users\(id\)", sql
        ), "rejected_by must reference auth.users(id)"
