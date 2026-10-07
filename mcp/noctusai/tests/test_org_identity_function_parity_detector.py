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


def _with_baseline(root: Path, entries: dict[str, str]) -> None:
    import json

    f = root / "mcp" / "noctusai" / "tests" / "org_identity_parity_baseline.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"legacy": entries}), encoding="utf-8")


def _hash_of(sql: str, name: str = "current_org_id") -> str:
    from tools.noctus.dev.compliance import _oif_decl_hash

    return _oif_decl_hash(org_identity_declarations(sql, (name,))[0])


class TestFrozenBaselineAndLastWriter:
    REL = "products/demo/backend/migrations/001_demo.sql"

    def test_baselined_historical_copy_is_tolerated(self, tmp_path: Path):
        root = _tree(tmp_path, migration=_STALE)
        _with_baseline(root, {f"{self.REL}::current_org_id": _hash_of(_STALE)})
        assert check_org_identity_function_parity(root) == []

    def test_changed_baselined_file_is_flagged(self, tmp_path: Path):
        root = _tree(tmp_path, migration=_STALE + "\n")
        edited = _STALE.replace("SELECT org_id", "SELECT org_id, 1")
        (root / self.REL).write_text(edited, encoding="utf-8")
        _with_baseline(root, {f"{self.REL}::current_org_id": _hash_of(_STALE)})
        assert len(check_org_identity_function_parity(root)) == 1

    def test_new_stale_file_not_in_baseline_is_flagged(self, tmp_path: Path):
        root = _tree(tmp_path, migration=_STALE)
        _with_baseline(root, {})
        assert len(check_org_identity_function_parity(root)) == 1

    def _core(self, root: Path, name: str, sql: str) -> None:
        d = root / "products" / "core" / "backend" / "migrations"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(sql, encoding="utf-8")

    def test_last_core_redeclaration_must_be_canonical(self, tmp_path: Path):
        root = _tree(tmp_path)
        self._core(root, "001_core.sql", _render("current_org_id") + "\n" + _render("current_user_org_id"))
        self._core(root, "070_later.sql", _STALE)
        _with_baseline(root, {"products/core/backend/migrations/070_later.sql::current_org_id": _hash_of(_STALE)})
        issues = check_org_identity_function_parity(root)
        assert any("LAST core migration" in i["issue"] for i in issues)

    def test_last_core_canonical_passes(self, tmp_path: Path):
        root = _tree(tmp_path)
        both = _render("current_org_id") + "\n" + _render("current_user_org_id")
        self._core(root, "001_core.sql", _STALE)
        self._core(root, "067_canon.sql", both)
        _with_baseline(root, {"products/core/backend/migrations/001_core.sql::current_org_id": _hash_of(_STALE)})
        assert check_org_identity_function_parity(root) == []


def test_live_tree_is_clean():
    """The real tree: every NEW/changed re-declaration matches the canon (historical
    copies are frozen in org_identity_parity_baseline.json) and the last core
    re-declaration (067, after act-as-org was removed) is canonical."""
    assert check_org_identity_function_parity() == []
