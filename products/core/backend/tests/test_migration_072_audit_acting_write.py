"""Core 072 -- acting-write audit trigger. Static contract tests over the SQL file (the live
behaviour is proven by the ``noctus.dev.verify_db_guards`` acting_audit probes, rolled back)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pglast = pytest.importorskip("pglast")
from pglast import parse_sql  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
SQL = (ROOT / "products/core/backend/migrations/072_audit_acting_write.sql").read_text(encoding="utf-8")


def _body(name: str) -> str:
    m = re.search(rf"FUNCTION public\.{name}\(.*?AS \$\$(.*?)\$\$;", SQL, re.DOTALL)
    assert m, name
    return m.group(1)


def test_parses():
    assert len(parse_sql(SQL)) >= 8


@pytest.mark.parametrize("sig", ["audit_acting_write\\(\\)", "attach_acting_audit_triggers\\(text, text\\)"])
def test_secdef_pinned_and_execute_revoked(sig):
    name = sig.split("\\")[0]
    head = re.search(rf"CREATE OR REPLACE FUNCTION public\.{name}\((.*?)AS \$\$", SQL, re.DOTALL).group(0)
    assert "SECURITY DEFINER" in head and "SET search_path TO 'public'" in head
    assert re.search(rf"REVOKE EXECUTE ON FUNCTION public\.{sig} FROM PUBLIC, anon, authenticated", SQL)
    assert re.search(rf"GRANT\s+EXECUTE ON FUNCTION public\.{sig} TO service_role", SQL)


def test_trigger_is_noop_without_a_user_and_when_not_acting():
    b = _body("audit_acting_write")
    assert "v_uid IS NULL" in b  # service_role / migrations: auth.uid() is NULL
    assert "current_org_id_for(v_schema)" in b and "public.current_org_id()" in b
    assert "v_target IS NULL OR v_target IS NOT DISTINCT FROM v_home" in b


def test_audit_row_shape_ids_and_column_names_only():
    b = _body("audit_acting_write")
    for token in ("'platform_support'", "acting_org_id", "act_as_session_id", "lower(TG_OP)", "v_target"):
        assert token in b
    ins = b.split("INSERT INTO public.audit_logs", 1)[1]
    # no row payload: neither NEW/OLD nor the jsonb row is stored, only column NAMES
    assert "before_snapshot" not in ins
    assert "'columns', v_cols" in ins
    assert "v_row," not in ins and "to_jsonb(NEW)," not in ins


def test_attach_is_idempotent_skips_underscored_and_needs_org_id():
    b = _body("attach_acting_audit_triggers")
    assert "DROP TRIGGER IF EXISTS audit_acting_write" in b
    assert "left(c.relname, 1) <> '_'" in b and "a.attname = 'org_id'" in b
    assert "c.relkind IN ('r', 'p')" in b
    assert "AFTER INSERT OR UPDATE OR DELETE" in b and "FOR EACH ROW" in b
