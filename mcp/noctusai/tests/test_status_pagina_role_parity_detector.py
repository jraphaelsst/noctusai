"""Regression tests for `check_status_pagina_role_parity`.

A keeper that cannot fail is worse than no keeper — it reads as coverage while
guarding nothing. These build synthetic trees so both verdicts are proven, and
they pin the two silent-pass shapes the detector deliberately reports instead
of swallowing (missing `DEV_ROLES`, unparseable SQL role array).

Per `KB § PATTERNS/common/regression-test-the-detector.md`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.noctus.dev.compliance import check_status_pagina_role_parity

_POLICY_SQL = """\
SET search_path = {schema}, public;

DROP POLICY IF EXISTS "dev_veem_desenvolvimento" ON {schema}.status_pagina;
CREATE POLICY "dev_veem_desenvolvimento" ON {schema}.status_pagina
    FOR SELECT TO authenticated
    USING (
        status = 'desenvolvimento'
        AND public.current_org_role() = ANY (ARRAY[{roles}])
    );
"""


def _tree(tmp_path: Path, *, fe_roles: str | None, sql_roles: str | None) -> Path:
    """Build a minimal repo: a seed roles.ts + one product migration."""
    roles_dir = tmp_path / "seed" / "lib" / "frontend" / "src"
    roles_dir.mkdir(parents=True)
    if fe_roles is not None:
        (roles_dir / "roles.ts").write_text(
            f"export const DEV_ROLES: OrgRole[] = [{fe_roles}];\n", encoding="utf-8"
        )
    else:
        # Present but without the declaration — the "cannot verify" shape.
        (roles_dir / "roles.ts").write_text("export const OTHER = 1;\n", encoding="utf-8")

    mig = tmp_path / "products" / "demo" / "backend" / "migrations"
    mig.mkdir(parents=True)
    body = (
        _POLICY_SQL.format(schema="demo", roles=sql_roles)
        if sql_roles is not None
        else "-- a dev-visibility migration with no recognisable role array\n"
    )
    (mig / "007_status_pagina_dev_visibility.sql").write_text(body, encoding="utf-8")
    return tmp_path


class TestStatusPaginaRoleParity:
    """Clean cases. Named to match `check_status_pagina_role_parity` so
    `check_detector_has_regression_test` can find this file — the meta-keeper
    discovers coverage by class name, not by filename."""

    def test_identical_role_sets_are_clean(self, tmp_path: Path):
        root = _tree(
            tmp_path,
            fe_roles="'owner', 'dev', 'admin'",
            sql_roles="'owner', 'dev', 'admin'",
        )
        assert check_status_pagina_role_parity(repo_root=root) == []

    def test_ordering_and_quote_style_are_not_differences(self, tmp_path: Path):
        # The contract is the SET of roles. A reformat must not fire the gate,
        # or the team learns to ignore it.
        root = _tree(
            tmp_path,
            fe_roles="'admin',\n  'owner',\n  'dev',",
            sql_roles='"dev", "admin", "owner"',
        )
        assert check_status_pagina_role_parity(repo_root=root) == []


class TestParityBreaks:
    def test_role_only_in_sql_is_flagged(self, tmp_path: Path):
        root = _tree(
            tmp_path, fe_roles="'owner', 'dev'", sql_roles="'owner', 'dev', 'admin'"
        )
        issues = check_status_pagina_role_parity(repo_root=root)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert "only-in-SQL=['admin']" in issues[0]["issue"]

    def test_role_only_in_frontend_is_flagged(self, tmp_path: Path):
        root = _tree(
            tmp_path, fe_roles="'owner', 'dev', 'admin'", sql_roles="'owner', 'dev'"
        )
        issues = check_status_pagina_role_parity(repo_root=root)
        assert len(issues) == 1
        assert "only-in-FE=['admin']" in issues[0]["issue"]

    def test_every_drifted_migration_is_reported_not_just_the_first(
        self, tmp_path: Path
    ):
        root = _tree(
            tmp_path, fe_roles="'owner'", sql_roles="'owner', 'dev'"
        )
        second = tmp_path / "products" / "other" / "backend" / "migrations"
        second.mkdir(parents=True)
        (second / "003_status_pagina_dev_visibility.sql").write_text(
            _POLICY_SQL.format(schema="other", roles="'owner', 'admin'"),
            encoding="utf-8",
        )
        issues = check_status_pagina_role_parity(repo_root=root)
        assert len(issues) == 2
        assert {i["product"] for i in issues} == {"demo", "other"}


class TestUnverifiableIsReportedNotSwallowed:
    def test_missing_dev_roles_declaration_is_an_issue(self, tmp_path: Path):
        root = _tree(tmp_path, fe_roles=None, sql_roles="'owner', 'dev'")
        issues = check_status_pagina_role_parity(repo_root=root)
        assert len(issues) == 1
        assert "cannot locate" in issues[0]["issue"]
        assert issues[0]["severity"] == "high"

    def test_unparseable_sql_role_array_is_an_issue(self, tmp_path: Path):
        root = _tree(tmp_path, fe_roles="'owner', 'dev'", sql_roles=None)
        issues = check_status_pagina_role_parity(repo_root=root)
        assert len(issues) == 1
        assert "no `current_org_role() = ANY (ARRAY[...])` predicate" in issues[0]["issue"]

    def test_no_migrations_at_all_is_not_a_violation(self, tmp_path: Path):
        # A tree with no dev-visibility migrations has no contract to break.
        (tmp_path / "seed" / "lib" / "frontend" / "src").mkdir(parents=True)
        (tmp_path / "seed" / "lib" / "frontend" / "src" / "roles.ts").write_text(
            "export const DEV_ROLES: OrgRole[] = ['owner'];\n", encoding="utf-8"
        )
        assert check_status_pagina_role_parity(repo_root=tmp_path) == []

    def test_absent_repo_root_returns_empty(self, tmp_path: Path):
        assert check_status_pagina_role_parity(repo_root=tmp_path / "nope") == []


class TestLiveTree:
    def test_the_real_repo_is_in_parity(self):
        """The fleet itself must satisfy the contract this keeper encodes."""
        from settings import REPO_ROOT

        assert check_status_pagina_role_parity(repo_root=Path(REPO_ROOT)) == []
