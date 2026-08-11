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


class TestDevReachability:
    """The BLIND SPOT half, added 2026-08-10.

    The parity loop above iterates over dev-visibility migrations that EXIST.
    A product with none of them has nothing to compare, so the keeper returned
    green over the worse defect: every `status_pagina` policy filters on
    'producao', so a 'desenvolvimento' row reaches NOBODY and the frontend's
    dev/owner branch is unreachable code. That is the original fleet-wide bug
    the parity check was written in response to — and the check could not see
    it. Found on `adconnect` + `dev-team`, both of which got the migration.
    """

    def _product(self, tmp_path: Path, name: str, *sql_bodies: str) -> Path:
        roles_dir = tmp_path / "seed" / "lib" / "frontend" / "src"
        roles_dir.mkdir(parents=True, exist_ok=True)
        (roles_dir / "roles.ts").write_text(
            "export const DEV_ROLES: OrgRole[] = ['owner', 'dev', 'admin'];\n",
            encoding="utf-8",
        )
        mig = tmp_path / "products" / name / "backend" / "migrations"
        mig.mkdir(parents=True, exist_ok=True)
        for i, body in enumerate(sql_bodies, start=1):
            (mig / f"{i:03d}_init.sql").write_text(body, encoding="utf-8")
        return tmp_path

    PRODUCAO_ONLY = (
        'CREATE POLICY "todos_veem_producao" ON demo.status_pagina\n'
        "    FOR SELECT USING (status = 'producao');\n"
    )
    DEV_POLICY = (
        'CREATE POLICY "dev_veem_desenvolvimento" ON demo.status_pagina\n'
        "    FOR SELECT TO authenticated USING (\n"
        "        status = 'desenvolvimento'\n"
        "        AND public.current_org_role() = ANY (ARRAY['owner', 'dev', 'admin'])\n"
        "    );\n"
    )

    def test_producao_only_product_is_flagged(self, tmp_path: Path):
        root = self._product(tmp_path, "demo", self.PRODUCAO_ONLY)
        issues = check_status_pagina_role_parity(repo_root=root)
        assert len(issues) == 1
        assert issues[0]["product"] == "demo"
        assert "returned to NOBODY" in issues[0]["issue"]

    def test_adding_the_dev_policy_clears_it(self, tmp_path: Path):
        root = self._product(
            tmp_path, "demo", self.PRODUCAO_ONLY, self.DEV_POLICY
        )
        assert check_status_pagina_role_parity(repo_root=root) == []

    def test_a_non_producao_policy_of_ANY_shape_clears_it(self, tmp_path: Path):
        """erp-imobiliario predates the seed shape: its dev visibility comes
        from `has_role(uid,'dev') AND tipo_pagina='geral'`, with no status
        predicate at all. That is a genuinely reachable branch, so it must
        pass WITHOUT an allowlist entry — the check is derived, not rostered."""
        erp_shape = (
            'CREATE POLICY "Devs podem ver paginas gerais" ON demo.status_pagina\n'
            "    FOR SELECT USING (has_role(auth.uid(), 'dev') AND tipo_pagina = 'geral');\n"
        )
        root = self._product(tmp_path, "demo", self.PRODUCAO_ONLY, erp_shape)
        assert check_status_pagina_role_parity(repo_root=root) == []

    def test_a_later_drop_retires_an_earlier_create(self, tmp_path: Path):
        """Policies are replayed in migration order, as the database sees
        them — a dev policy that a later migration DROPs must re-flag."""
        drop = 'DROP POLICY IF EXISTS "dev_veem_desenvolvimento" ON demo.status_pagina;\n'
        root = self._product(
            tmp_path, "demo", self.PRODUCAO_ONLY, self.DEV_POLICY, drop
        )
        issues = check_status_pagina_role_parity(repo_root=root)
        assert len(issues) == 1
        assert "returned to NOBODY" in issues[0]["issue"]

    def test_product_without_status_pagina_is_ignored(self, tmp_path: Path):
        root = self._product(
            tmp_path, "demo", "CREATE TABLE demo.widgets (id uuid primary key);\n"
        )
        assert check_status_pagina_role_parity(repo_root=root) == []


class TestLiveTree:
    def test_the_real_repo_is_in_parity(self):
        """The fleet itself must satisfy the contract this keeper encodes —
        BOTH halves: role parity and dev reachability."""
        from settings import REPO_ROOT

        assert check_status_pagina_role_parity(repo_root=Path(REPO_ROOT)) == []
