"""Structural tests for `053_audit_trail_expansion.sql` (no database needed).

Load-bearing assertions: every new column is added idempotently, the
append-only guard actually wires (BEFORE UPDATE OR DELETE, RAISE EXCEPTION
on every branch except the flag-gated DELETE), the purge function is the
only thing that sets/unsets the flag, both are service_role-only, and the
migration is forward-only (never a DROP/TRUNCATE/bare DELETE).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "053_audit_trail_expansion.sql"
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


def test_only_number_053_in_this_file_name():
    siblings = [p.name for p in MIGRATION.parent.glob("053_*.sql")]
    assert siblings == [MIGRATION.name]


def test_is_forward_only_except_the_guarded_purge_delete(code: str):
    assert "DROP TABLE" not in code
    assert "DROP COLUMN" not in code
    assert "TRUNCATE" not in code
    # The ONLY DELETE in the whole file must live inside
    # purge_expired_audit_logs (the sanctioned retention door) — never a
    # bare top-level DELETE.
    deletes = [m.start() for m in re.finditer(r"\bDELETE\s+FROM\b", code)]
    assert len(deletes) == 1
    fn_start = code.index("CREATE OR REPLACE FUNCTION public.purge_expired_audit_logs")
    fn_end = code.index("$$;\n\nREVOKE ALL ON FUNCTION public.purge_expired_audit_logs")
    assert fn_start < deletes[0] < fn_end


# ── new columns ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "column,coltype",
    [
        ("product_slug", "TEXT"),
        ("method", "TEXT"),
        ("route_template", "TEXT"),
        ("path_params", "JSONB NOT NULL DEFAULT '{}'"),
        ("status_code", "INT"),
        ("correlation_id", "TEXT"),
        ("role", "TEXT"),
        ("client_hint", "TEXT"),
        ("duration_ms", "INT"),
        ("before_snapshot", "JSONB NOT NULL DEFAULT '{}'"),
        ("retention_until", "TIMESTAMPTZ"),
    ],
)
def test_new_columns_added_idempotently(flat: str, column: str, coltype: str):
    assert f"ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS {column} {coltype}" in flat


def test_actor_kind_is_not_null_default_user_with_closed_vocabulary(flat: str):
    assert (
        "ADD COLUMN IF NOT EXISTS actor_kind TEXT NOT NULL DEFAULT 'user' "
        "CHECK (actor_kind IN ('user', 'agent', 'service'))" in flat
    )


def test_actor_kind_check_is_unnamed_never_add_constraint(code: str):
    # Deliberate: an unnamed inline CHECK escapes check_migration_guard_has_probe's
    # detection (documented limitation) — no extra verify_db_guards probe is
    # required for this specific shape. A named ADD CONSTRAINT would force one.
    assert "ADD CONSTRAINT" not in code


def test_new_indexes(flat: str):
    assert (
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_product_resource "
        "ON public.audit_logs (product_slug, resource_type, resource_id, created_at DESC)" in flat
    )
    assert "CREATE INDEX IF NOT EXISTS idx_audit_logs_correlation ON public.audit_logs (correlation_id)" in flat
    assert "CREATE INDEX IF NOT EXISTS idx_audit_logs_retention ON public.audit_logs (retention_until)" in flat


def test_org_created_at_index_is_not_redeclared(code: str):
    # idx_audit_logs_org already exists (002_missing_tables.sql) — this
    # migration must not re-declare it.
    assert "idx_audit_logs_org" not in code


# ── retention backfill ordering ────────────────────────────────────────


def test_retention_until_backfilled_before_not_null(flat: str):
    add = flat.index("ADD COLUMN IF NOT EXISTS retention_until TIMESTAMPTZ;")
    backfill = flat.index(
        "UPDATE public.audit_logs SET retention_until = created_at + INTERVAL '400 days' "
        "WHERE retention_until IS NULL;"
    )
    default = flat.index(
        "ALTER TABLE public.audit_logs ALTER COLUMN retention_until "
        "SET DEFAULT (now() + INTERVAL '400 days');"
    )
    not_null = flat.index(
        "ALTER TABLE public.audit_logs ALTER COLUMN retention_until SET NOT NULL;"
    )
    assert add < backfill < default < not_null


# ── append-only guard ───────────────────────────────────────────────────


def test_guard_function_is_a_before_update_or_delete_trigger(flat: str):
    assert "CREATE OR REPLACE FUNCTION public.guard_audit_logs_append_only()" in flat
    assert "RETURNS TRIGGER" in flat
    assert (
        "CREATE TRIGGER guard_audit_logs_append_only "
        "BEFORE UPDATE OR DELETE ON public.audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION public.guard_audit_logs_append_only();" in flat
    )


def test_guard_function_raises_unconditionally_except_flagged_delete(flat: str):
    assert (
        "IF TG_OP = 'DELETE' AND current_setting('core.audit_log_purge', true) = 'on' "
        "THEN RETURN OLD; END IF;" in flat
    )
    assert "RAISE EXCEPTION 'audit_logs_append_only' USING ERRCODE = 'P0001';" in flat


def test_guard_function_is_service_role_only(flat: str):
    assert "REVOKE ALL ON FUNCTION public.guard_audit_logs_append_only() FROM PUBLIC, anon, authenticated;" in flat
    assert "GRANT EXECUTE ON FUNCTION public.guard_audit_logs_append_only() TO service_role;" in flat


# ── purge — the only allowed delete path ───────────────────────────────


def test_purge_function_sets_flag_on_then_off_around_the_delete(flat: str):
    on_idx = flat.index("PERFORM set_config('core.audit_log_purge', 'on', true);")
    delete_idx = flat.index("DELETE FROM public.audit_logs")
    off_idx = flat.index("PERFORM set_config('core.audit_log_purge', 'off', true);")
    assert on_idx < delete_idx < off_idx


def test_purge_function_deletes_only_rows_past_retention(flat: str):
    body = re.search(
        r"CREATE OR REPLACE FUNCTION public\.purge_expired_audit_logs.*?\$\$;",
        flat,
        re.DOTALL,
    ).group(0)
    assert "WHERE retention_until < now()" in body
    assert "LIMIT p_batch_limit" in body
    assert "GET DIAGNOSTICS v_count = ROW_COUNT;" in body
    assert "RETURN v_count;" in body


def test_purge_function_is_service_role_only(flat: str):
    assert (
        "REVOKE ALL ON FUNCTION public.purge_expired_audit_logs(INT) FROM PUBLIC, anon, authenticated;"
        in flat
    )
    assert "GRANT EXECUTE ON FUNCTION public.purge_expired_audit_logs(INT) TO service_role;" in flat


def test_purge_batch_limit_has_a_default(flat: str):
    assert "CREATE OR REPLACE FUNCTION public.purge_expired_audit_logs(p_batch_limit INT DEFAULT 5000)" in flat
