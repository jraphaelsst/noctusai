"""Static checks for core ``*_org_picker_postgrest_entry``: "every entry is a choice" at the PostgREST layer -- platform staff
on a ready product with no valid live selection resolve NULL in current_org_id_for (owner decision
2026-10-12). The live behaviour is proven by ``noctus.dev.verify_db_guards`` probes (rolled back)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = ROOT / "products/core/backend/migrations"
THIS = migration_path(MIGRATIONS, "org_picker_postgrest_entry")
SQL = THIS.read_text(encoding="utf-8")
#: The declaration this migration supersedes (the org_picker_requires_mfa flag migration).
SQL_PREV = migration_path(MIGRATIONS, "org_picker_mfa_flag").read_text(encoding="utf-8")
FLAT = " ".join(SQL.split())

NO_SELECTION_BRANCH = (
    "IF EXISTS (SELECT 1 FROM public.products p WHERE p.db_schema = p_schema AND p.org_picker_ready "
    "AND (NOT p.org_picker_requires_mfa OR v_claims ->> 'aal' = 'aal2')) THEN RETURN NULL; END IF; "
    "END IF; RETURN v_home;"
)


def _fn(sql: str) -> str:
    m = re.search(r"CREATE OR REPLACE FUNCTION public\.current_org_id_for.*?\$f\$;", sql, re.S)
    assert m is not None
    return " ".join(m.group(0).split())


def test_helper_was_the_canonical_rendering_until_member_selection_superseded_it():
    """078 stays byte-immutable (applied to prod); once a later migration re-declared the helper
    its copy became a RATIFIED HISTORICAL one -- frozen by content hash in the parity baseline,
    and the LAST core declaration (the member-selection migration) carries the canon."""
    baseline = (ROOT / "mcp/noctusai/tests/org_identity_parity_baseline.json").read_text(encoding="utf-8")
    assert f"{THIS.relative_to(ROOT)}::current_org_id_for" in baseline
    assert "org_memberships" not in FLAT  # 078 predates multi-org: staff-only


def test_staff_without_a_selection_on_a_ready_product_resolve_null_not_home():
    assert NO_SELECTION_BRANCH in FLAT


def test_the_only_change_from_the_mfa_flag_declaration_is_the_no_selection_branch():
    """Everything else identical: non-staff home rule, selection lookup, aal1 path, pin header."""
    added = (
        " IF EXISTS (SELECT 1 FROM public.products p WHERE p.db_schema = p_schema AND p.org_picker_ready "
        "AND (NOT p.org_picker_requires_mfa OR v_claims ->> 'aal' = 'aal2')) THEN RETURN NULL; END IF;"
    )
    assert _fn(SQL).replace(added, "", 1) == _fn(SQL_PREV)


def test_execute_stays_with_the_rls_helper_marker():
    assert re.search(r"-- secdef-execute-ok: rls-helper[^\n]*\nCREATE OR REPLACE FUNCTION public\.current_org_id_for", SQL)
    assert "REVOKE EXECUTE ON FUNCTION public.current_org_id_for" not in SQL


def test_declares_the_helper_after_the_mfa_flag_declaration():
    declaring = [
        p.name for p in sorted(MIGRATIONS.glob("[0-9]*.sql"))
        if re.search(r"FUNCTION\s+public\.current_org_id_for\s*\(", p.read_text(encoding="utf-8"))
    ]
    assert declaring.index(THIS.name) == declaring.index(migration_path(MIGRATIONS, "org_picker_mfa_flag").name) + 1
    # the LAST core declaration being canonical is the keeper's job (check_org_identity_function_parity)


def test_remediation_marker_is_closed():
    tpl = (ROOT / "seed/lib/backend/noctusai_lib/domain/sql_templates.py").read_text(encoding="utf-8")
    assert "NOC-REMEDIATE" + "[org-picker-postgrest-entry]" not in tpl


def test_the_file_parses_as_postgres():
    pglast = pytest.importorskip("pglast")
    assert len(pglast.parse_sql(SQL)) >= 3
