"""Regression tests for `check_org_identity_function_parity` (SEC-2, 2026-09-28).

A keeper that cannot fail is worse than no keeper. These build synthetic trees
carrying the REAL canon sources (roles.py + sql_templates.py copied from this
checkout) so both verdicts are proven against the rendering the fleet actually
uses, plus the silent-pass shapes the detector must report instead of swallow.

Per `KB § PATTERNS/common/regression-test-the-detector.md`.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from tools.noctus.dev.compliance import (
    REPO_ROOT,
    check_org_identity_function_parity,
    org_identity_declarations,
)

_ROLES_PY = Path("seed/lib/backend/noctusai_lib/primitives/roles.py")
_TEMPLATES_PY = Path("seed/lib/backend/noctusai_lib/domain/sql_templates.py")
_ROLES_TS = Path("seed/lib/frontend/src/roles.ts")

_STALE = """\
CREATE OR REPLACE FUNCTION public.current_org_id()
  RETURNS uuid
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid());
$f$;
"""


def _render(name: str) -> str:
    """The canonical rendering, loaded the same file-based way the keeper does."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_t_sql_templates", REPO_ROOT / _TEMPLATES_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.org_identity_function_sql(name, customer_roles={"membro"})


def _tree(tmp_path: Path, *, ts_roles: str = "'membro'", migration: str | None = None) -> Path:
    for rel in (_ROLES_PY, _TEMPLATES_PY):
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / rel, dest)
    ts = tmp_path / _ROLES_TS
    ts.parent.mkdir(parents=True, exist_ok=True)
    ts.write_text(f"export const CUSTOMER_ORG_ROLES: readonly string[] = [{ts_roles}];\n", encoding="utf-8")
    mig = tmp_path / "products" / "demo" / "backend" / "migrations"
    mig.mkdir(parents=True)
    if migration is not None:
        (mig / "001_demo.sql").write_text(migration, encoding="utf-8")
    return tmp_path


class TestOrgIdentityFunctionParity:
    """Named to match the keeper so `check_detector_has_regression_test` finds it."""

    def test_canonical_redeclaration_is_clean(self, tmp_path: Path):
        sql = "SET search_path = demo, public;\n\n" + _render("current_org_id") + "\n"
        assert check_org_identity_function_parity(_tree(tmp_path, migration=sql)) == []

    def test_every_canonical_function_is_clean(self, tmp_path: Path):
        names = ("current_org_id", "current_user_org_id", "current_org_role",
                 "is_customer", "current_customer_org_id")
        sql = "\n\n".join(_render(n) for n in names)
        assert check_org_identity_function_parity(_tree(tmp_path, migration=sql)) == []

    def test_whitespace_and_dollar_tag_are_not_drift(self, tmp_path: Path):
        sql = _render("current_org_id").replace("$f$", "$corpo$").replace("\n  ", "\n        ")
        assert check_org_identity_function_parity(_tree(tmp_path, migration=sql)) == []

    def test_stale_body_is_flagged_critical(self, tmp_path: Path):
        issues = check_org_identity_function_parity(_tree(tmp_path, migration=_STALE))
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert issues[0]["file"].endswith("001_demo.sql:1")
        assert "current_org_id" in issues[0]["issue"]

    def test_commented_out_declaration_is_prose(self, tmp_path: Path):
        sql = "-- CREATE OR REPLACE FUNCTION public.current_org_id() RETURNS uuid AS $x$ SELECT 1 $x$;\n"
        assert check_org_identity_function_parity(_tree(tmp_path, migration=sql)) == []

    def test_paths_scope_limits_the_audit(self, tmp_path: Path):
        root = _tree(tmp_path, migration=_STALE)
        assert check_org_identity_function_parity(root, paths=["products/other/x.sql"]) == []
        flagged = check_org_identity_function_parity(
            root, paths=["products/demo/backend/migrations/001_demo.sql"]
        )
        assert len(flagged) == 1


class TestOrgIdentityFunctionParitySilentPassShapes:
    def test_ts_split_brain_is_flagged(self, tmp_path: Path):
        issues = check_org_identity_function_parity(_tree(tmp_path, ts_roles="'membro', 'cliente'"))
        assert any("split-brain" in i["issue"] for i in issues)

    def test_missing_ts_declaration_is_flagged(self, tmp_path: Path):
        root = _tree(tmp_path)
        (root / _ROLES_TS).write_text("export const OTHER = 1;\n", encoding="utf-8")
        issues = check_org_identity_function_parity(root)
        assert any("CUSTOMER_ORG_ROLES" in i["issue"] for i in issues)

    def test_missing_canon_source_is_critical_not_silent(self, tmp_path: Path):
        root = _tree(tmp_path, migration=_STALE)
        (root / _TEMPLATES_PY).unlink()
        issues = check_org_identity_function_parity(root)
        assert len(issues) == 1 and issues[0]["severity"] == "critical"
        assert "cannot load" in issues[0]["issue"]


def test_declaration_parser_reports_line_numbers():
    decls = org_identity_declarations("\n\n" + _STALE, ("current_org_id",))
    assert [d["line"] for d in decls] == [3]


def test_live_tree_is_clean():
    """The real tree: every re-declaration in every chain matches the canon."""
    assert check_org_identity_function_parity() == []
