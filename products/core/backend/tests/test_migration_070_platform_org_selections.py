"""Core 070 -- platform org picker. Static contract tests over the SQL file (the live
behaviour is proven by ``noctus.dev.verify_db_guards`` probes, rolled back)."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SQL = (ROOT / "products/core/backend/migrations/070_platform_org_selections.sql").read_text(encoding="utf-8")


def _declared_schemas() -> dict[str, str]:
    out: dict[str, str] = {}
    for main in sorted((ROOT / "products").glob("*/backend/app/main.py")):
        slug = main.parts[-4]
        if slug == "core":
            continue
        for node in ast.walk(ast.parse(main.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "create_product_app":
                for kw in node.keywords:
                    if kw.arg == "schema" and isinstance(kw.value, ast.Constant):
                        out[slug] = kw.value.value
    return out


def test_backfill_equals_every_products_create_product_app_schema():
    declared = _declared_schemas()
    block = SQL.split("FROM (VALUES", 1)[1].split(") AS v(slug, db_schema)", 1)[0]
    backfill = dict(re.findall(r"\('([^']+)',\s*'([^']+)'\)", block))
    # `store` etc. may have no catalog row yet; every on-disk product must be MAPPED.
    assert backfill == declared


def test_picker_is_expand_only_and_ready_defaults_false():
    assert "org_picker_ready boolean NOT NULL DEFAULT false" in SQL
    assert not re.search(r"\bDROP\s+(TABLE|COLUMN)\b", SQL, re.IGNORECASE)
    assert "ADD COLUMN IF NOT EXISTS db_schema text" in SQL
    # current_org_id()/current_user_org_id() are NOT redeclared here (home-only forever)
    assert not re.search(r"FUNCTION\s+public\.current_(user_)?org_id\s*\(", SQL)


def test_table_is_service_role_only_with_the_contract_constraints():
    assert "ENABLE ROW LEVEL SECURITY" in SQL
    assert "REVOKE ALL ON public.platform_org_selections FROM PUBLIC, anon, authenticated" in SQL
    assert not re.search(r"CREATE\s+POLICY[^;]*platform_org_selections", SQL, re.IGNORECASE)
    assert "CHECK ((ended_at IS NULL) = (ended_by IS NULL))" in SQL
    assert "ON public.platform_org_selections (user_id, product_id) WHERE ended_at IS NULL" in SQL
    assert "(user_id, product_id, auth_session_id) WHERE ended_at IS NULL" in SQL
    for reason in ("replaced", "exit", "logout", "new_session", "revoked"):
        assert f"'{reason}'" in SQL


@pytest.mark.parametrize("sig", [
    "platform_org_selection_set(uuid, text, uuid, uuid)",
    "platform_org_selection_end(uuid, text, text)",
])
def test_rpcs_are_service_role_only(sig):
    assert f"REVOKE EXECUTE ON FUNCTION public.{sig} FROM PUBLIC, anon, authenticated" in SQL
    assert f"GRANT  EXECUTE ON FUNCTION public.{sig} TO service_role" in SQL


def test_rpc_error_codes_and_staff_rule():
    for code in ("not_platform_staff", "target_not_licensed", "product_not_ready"):
        assert f"platform_org_selection:{code}" in SQL
    assert "u.role = 'admin'" in SQL and "o.is_platform" in SQL


def test_revocation_triggers_cover_every_premise():
    assert "AFTER UPDATE OF org_id, org_role, role ON public.noctus_users" in SQL
    assert "AFTER UPDATE OF is_platform ON public.organizations" in SQL
    assert "AFTER UPDATE OF status, fim, org_id, product_id OR DELETE ON public.licenses" in SQL
    assert "AFTER UPDATE OF org_picker_ready, db_schema ON public.products" in SQL
    assert "REVOKE EXECUTE ON FUNCTION public.platform_org_selection_revoke_product() FROM PUBLIC, anon, authenticated" in SQL
    assert SQL.count("ended_by = 'revoked'") == 4


def test_helper_keeps_caller_execute_with_the_rls_helper_marker():
    marker = re.search(r"-- secdef-execute-ok: rls-helper[^\n]*\nCREATE OR REPLACE FUNCTION public\.current_org_id_for", SQL)
    assert marker is not None
    assert "REVOKE EXECUTE ON FUNCTION public.current_org_id_for" not in SQL


def test_helper_requires_ready_product_live_auth_session_and_denies_on_pin_mismatch():
    assert "AND p.org_picker_ready" in SQL
    assert "EXISTS (SELECT 1 FROM auth.sessions se WHERE se.id = s.auth_session_id)" in SQL
    assert "v_org_role IN ('owner', 'admin')" in SQL
    # a present pin that differs from the result returns NULL (deny), target OR home fall-through
    assert SQL.count("RETURN NULL;") >= 4


def test_rpc_requires_owner_or_admin_org_role_for_staff():
    assert "u.org_role IN ('owner', 'admin')" in SQL


def test_the_last_core_declaration_of_the_helper_is_the_canonical_rendering():
    """070 is a historical copy once a later core migration re-declares the helper (073 put
    aal2 behind products.org_picker_requires_mfa); the canonical rendering must live in the
    LAST core migration declaring it -- the one a fresh core apply leaves behind."""
    import importlib.util

    tpl = ROOT / "seed/lib/backend/noctusai_lib/domain/sql_templates.py"
    spec = importlib.util.spec_from_file_location("_t070_sql_templates", tpl)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    canon = " ".join(mod.org_identity_function_sql("current_org_id_for").split())
    declaring = [
        p for p in sorted((ROOT / "products/core/backend/migrations").glob("[0-9]*.sql"))
        if re.search(r"FUNCTION\s+public\.current_org_id_for\s*\(", p.read_text(encoding="utf-8"))
    ]
    assert declaring and declaring[0].name.startswith("070_")
    assert canon in " ".join(declaring[-1].read_text(encoding="utf-8").split()), declaring[-1].name


def test_the_file_parses_as_postgres():
    pglast = pytest.importorskip("pglast")
    assert len(pglast.parse_sql(SQL)) > 20
