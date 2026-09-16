"""Structural (parse-based) tests for `121_jobs.sql`.

The file is a byte-for-byte instantiation of
`noctusai_lib/domain/jobs/migrations/jobs.sql.template`
({{SCHEMA_NAME}} -> social_wiring) — these tests pin that the
substitution landed cleanly and nothing else drifted.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "121_jobs.sql"
TEMPLATE = (
    Path(__file__).resolve().parents[4]
    / "seed"
    / "lib"
    / "backend"
    / "noctusai_lib"
    / "domain"
    / "jobs"
    / "migrations"
    / "jobs.sql.template"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    collapsed = " ".join(code.split())
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", collapsed))


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


def test_is_forward_only(code: str):
    assert "DROP TABLE" not in code
    assert "DROP COLUMN" not in code


def test_no_unsubstituted_placeholder_remains(code: str):
    """`code` has comment lines stripped — the header prose legitimately
    MENTIONS the `{{SCHEMA_NAME}}` placeholder to document the
    substitution; only the actual DDL must be placeholder-free."""
    assert "{{SCHEMA_NAME}}" not in code


def test_table_and_hardening_columns_present(flat: str):
    assert "CREATE TABLE IF NOT EXISTS social_wiring.jobs" in flat
    for col in ("dedupe_key", "worker_id", "lease_expires_at", "retry_count", "max_retries"):
        assert col in flat


def test_four_rpcs_present(flat: str):
    for fn in ("claim_next_job", "fail_job", "complete_job", "extend_lease"):
        assert f"CREATE OR REPLACE FUNCTION social_wiring.{fn}(" in flat


def test_rls_enabled_with_no_default_authenticated_policy(flat: str, code: str):
    assert "ALTER TABLE social_wiring.jobs ENABLE ROW LEVEL SECURITY" in flat
    # Canonical default ships NO policy beyond RLS-on — service_role
    # bypasses; anon/authenticated denied by omission.
    assert "CREATE POLICY" not in code


def test_body_matches_the_seed_template(sql: str):
    """Only the {{SCHEMA_NAME}} substitution + a small attribution header
    may differ — the RPC bodies themselves must be byte-identical to the
    seed template (the whole point of instantiating from it)."""
    if not TEMPLATE.is_file():
        pytest.skip(f"seed template not found at {TEMPLATE}")
    template_body = TEMPLATE.read_text(encoding="utf-8").replace("{{SCHEMA_NAME}}", "social_wiring")
    assert template_body.strip() in sql
