"""Structural tests for `054_erase_test_org_audit_logs.sql` (no database
needed).

Load-bearing assertions: the erasure function refuses anything that isn't a
`category = 'test' AND slug LIKE 'test-realdb-%'` organization, it reuses
the exact `core.audit_log_purge` flag `guard_audit_logs_append_only`
(053) and `purge_expired_audit_logs` (053) already gate on — never a new
bypass — it is service_role-only, it only ever deletes from `audit_logs`
(never `organizations` or another table), and the append-only trigger
itself is untouched by this file.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "054_erase_test_org_audit_logs.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_only_number_054_in_this_file_name():
    siblings = [p.name for p in MIGRATION.parent.glob("054_*.sql")]
    assert siblings == [MIGRATION.name]


def test_is_forward_only(code: str):
    assert "DROP TABLE" not in code
    assert "DROP COLUMN" not in code
    assert "TRUNCATE" not in code
    assert "DROP TRIGGER" not in code
    assert "DROP FUNCTION" not in code


def test_append_only_trigger_is_not_redeclared(code: str):
    # This migration must never touch the guard trigger itself — it is a
    # second CALLER of the existing escape hatch, not a new one.
    assert "CREATE TRIGGER" not in code
    assert "CREATE OR REPLACE TRIGGER" not in code
    assert "guard_audit_logs_append_only" not in code


# ── the erasure function itself ────────────────────────────────────────


def test_function_signature(flat: str):
    assert (
        "CREATE OR REPLACE FUNCTION public.erase_test_org_audit_logs(p_org_id UUID) "
        "RETURNS INT" in flat
    )
    assert "SECURITY DEFINER" in flat


def test_function_refuses_unless_test_realdb_org(flat: str):
    body = re.search(
        r"CREATE OR REPLACE FUNCTION public\.erase_test_org_audit_logs.*?\$\$;",
        flat,
        re.DOTALL,
    ).group(0)
    assert (
        "SELECT EXISTS ( SELECT 1 FROM public.organizations WHERE id = p_org_id "
        "AND category = 'test' AND slug LIKE 'test-realdb-%' ) INTO v_is_realdb_test_org;"
        in body
    )
    assert "IF NOT v_is_realdb_test_org THEN" in body
    assert "RAISE EXCEPTION 'org_not_erasable_test_org' USING ERRCODE = 'P0001';" in body


def test_function_reuses_the_053_purge_flag_around_the_delete(flat: str):
    body = re.search(
        r"CREATE OR REPLACE FUNCTION public\.erase_test_org_audit_logs.*?\$\$;",
        flat,
        re.DOTALL,
    ).group(0)
    on_idx = body.index("PERFORM set_config('core.audit_log_purge', 'on', true);")
    delete_idx = body.index("DELETE FROM public.audit_logs WHERE org_id = p_org_id;")
    off_idx = body.index("PERFORM set_config('core.audit_log_purge', 'off', true);")
    assert on_idx < delete_idx < off_idx


def test_function_only_deletes_from_audit_logs(flat: str):
    body = re.search(
        r"CREATE OR REPLACE FUNCTION public\.erase_test_org_audit_logs.*?\$\$;",
        flat,
        re.DOTALL,
    ).group(0)
    deletes = re.findall(r"DELETE\s+FROM\s+(\S+)", body)
    assert deletes == ["public.audit_logs"]


def test_function_returns_row_count(flat: str):
    body = re.search(
        r"CREATE OR REPLACE FUNCTION public\.erase_test_org_audit_logs.*?\$\$;",
        flat,
        re.DOTALL,
    ).group(0)
    assert "GET DIAGNOSTICS v_count = ROW_COUNT;" in body
    assert "RETURN v_count;" in body


def test_function_is_service_role_only(flat: str):
    assert (
        "REVOKE ALL ON FUNCTION public.erase_test_org_audit_logs(UUID) "
        "FROM PUBLIC, anon, authenticated;" in flat
    )
    assert (
        "GRANT EXECUTE ON FUNCTION public.erase_test_org_audit_logs(UUID) "
        "TO service_role;" in flat
    )


# ── the ONE DELETE in this file lives inside the guarded function ──────


def test_only_delete_in_file_lives_inside_the_erasure_function(code: str):
    deletes = [m.start() for m in re.finditer(r"\bDELETE\s+FROM\b", code)]
    assert len(deletes) == 1
    fn_start = code.index("CREATE OR REPLACE FUNCTION public.erase_test_org_audit_logs")
    fn_end = code.index(
        "$$;\n\nREVOKE ALL ON FUNCTION public.erase_test_org_audit_logs"
    )
    assert fn_start < deletes[0] < fn_end
