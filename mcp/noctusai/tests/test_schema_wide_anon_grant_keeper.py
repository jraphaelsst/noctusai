"""Regression tests for ``noctus.dev.compliance.check_schema_wide_anon_grant``.

THE INCIDENT this keeper exists for (2026-09-20): `products/seed/backend/
migrations/001_seed.sql` used to grant `ALL` on every current AND future
table to `anon` (`GRANT ALL ON ALL TABLES IN SCHEMA seed TO anon, ...` + the
matching `ALTER DEFAULT PRIVILEGES ... GRANT ALL ON TABLES TO anon, ...`),
propagated verbatim into 9 product schemas. In the live `social_wiring`
schema this let the unauthenticated `anon` PostgREST role read AND write 4
out-of-band backup tables (21,567 rows of names/emails/birthdates) that
never got an RLS policy at all.

All tests operate against an isolated ``tmp_path`` tree, never the real
repo — hermetic and fast.

KB § PATTERNS/backend/database-rls.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_schema_wide_anon_grant


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _make_products_root(tmp_path: Path) -> Path:
    (tmp_path / "products").mkdir()
    return tmp_path


class TestLegA_GrantAllTables:
    def test_grant_all_on_all_tables_to_anon_is_flagged(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "GRANT ALL ON ALL TABLES IN SCHEMA demo TO anon, authenticated, service_role;\n",
        )

        issues = check_schema_wide_anon_grant(repo_root=root)

        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert issues[0]["file"] == "products/demo/backend/migrations/001_demo.sql"
        assert "ON ALL TABLES IN SCHEMA demo" in issues[0]["issue"]

    def test_narrower_privilege_list_to_anon_is_still_flagged(self, tmp_path):
        """The canonical shape forbids ANY blanket table grant to anon —
        not just `ALL`. A narrower `SELECT, INSERT, UPDATE, DELETE` blanket
        grant is still a schema-wide anon-facing table grant."""
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA demo TO anon, authenticated;\n",
        )

        issues = check_schema_wide_anon_grant(repo_root=root)

        assert len(issues) == 1

    def test_grant_all_tables_without_anon_is_clean(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "GRANT ALL ON ALL TABLES IN SCHEMA demo TO service_role;\n"
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA demo TO authenticated;\n",
        )

        assert check_schema_wide_anon_grant(repo_root=root) == []

    def test_single_table_grant_to_anon_is_not_flagged(self, tmp_path):
        """The sanctioned exception shape — `status_pagina` in
        `001_seed.sql` — names ONE table, not `ALL TABLES`."""
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "GRANT SELECT ON demo.status_pagina TO anon;\n",
        )

        assert check_schema_wide_anon_grant(repo_root=root) == []


class TestLegB_AlterDefaultPrivileges:
    def test_alter_default_privileges_grant_tables_to_anon_is_flagged(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA demo GRANT ALL ON TABLES TO anon, authenticated, service_role;\n",
        )

        issues = check_schema_wide_anon_grant(repo_root=root)

        assert len(issues) == 1
        assert "FUTURE table" in issues[0]["issue"]

    def test_alter_default_privileges_on_sequences_to_anon_is_not_flagged(self, tmp_path):
        """Sequences are deliberately exempt — no row data, and every
        product on this platform already grants anon sequence USAGE by
        design. Flagging it would make this keeper permanently red against
        the platform's own fix (`001_seed.sql` itself still does this)."""
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA demo GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;\n",
        )

        assert check_schema_wide_anon_grant(repo_root=root) == []

    def test_alter_default_privileges_tables_without_anon_is_clean(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA demo GRANT ALL ON TABLES TO service_role;\n",
        )

        assert check_schema_wide_anon_grant(repo_root=root) == []


class TestCommentsAreStripped:
    def test_prose_citing_the_vulnerable_shape_in_a_comment_is_not_flagged(self, tmp_path):
        """A lockdown migration's own header necessarily QUOTES the
        historical vulnerable statement for the reader's benefit (every
        migration this project shipped alongside this keeper does exactly
        this). Comments must be stripped before matching, or every one of
        those migrations would trip its own keeper."""
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/002_lockdown.sql",
            "-- Closes the exposure from 001_demo.sql:\n"
            "--   GRANT ALL ON ALL TABLES IN SCHEMA demo TO anon, authenticated, service_role;\n"
            "--   ALTER DEFAULT PRIVILEGES IN SCHEMA demo GRANT ALL ON TABLES TO anon, ...;\n"
            "REVOKE ALL ON ALL TABLES IN SCHEMA demo FROM anon;\n"
            "ALTER DEFAULT PRIVILEGES IN SCHEMA demo REVOKE ALL ON TABLES FROM anon;\n",
        )

        assert check_schema_wide_anon_grant(repo_root=root) == []

    def test_block_comment_citing_the_vulnerable_shape_is_not_flagged(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/002_lockdown.sql",
            "/* GRANT ALL ON ALL TABLES IN SCHEMA demo TO anon, authenticated; */\n"
            "REVOKE ALL ON ALL TABLES IN SCHEMA demo FROM anon;\n",
        )

        assert check_schema_wide_anon_grant(repo_root=root) == []


class TestRevokeIsNeverFlagged:
    def test_revoke_all_from_anon_is_not_flagged(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/002_lockdown.sql",
            "REVOKE ALL ON ALL TABLES IN SCHEMA demo FROM anon;\n"
            "ALTER DEFAULT PRIVILEGES IN SCHEMA demo REVOKE ALL ON TABLES FROM anon;\n",
        )

        assert check_schema_wide_anon_grant(repo_root=root) == []


class TestTemplatesScanned:
    def test_templates_product_seed_migrations_are_scanned_in_full_audit_mode(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "templates/product-seed/backend/migrations/001_seed.sql",
            "GRANT ALL ON ALL TABLES IN SCHEMA {{SCHEMA_NAME}} TO anon, authenticated, service_role;\n",
        )

        issues = check_schema_wide_anon_grant(repo_root=root)

        assert len(issues) == 1
        assert issues[0]["file"] == "templates/product-seed/backend/migrations/001_seed.sql"


class TestPathsScoping:
    """Pre-commit's diff-scoped mode (`paths=[...]`) — pre-2026-09-20
    `001_*.sql` immutable history must not re-block every future commit."""

    def test_paths_none_scans_whole_tree(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_history.sql",
            "GRANT ALL ON ALL TABLES IN SCHEMA demo TO anon, authenticated, service_role;\n",
        )

        assert len(check_schema_wide_anon_grant(repo_root=root)) == 1

    def test_paths_scoped_ignores_untouched_violating_history(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_history.sql",
            "GRANT ALL ON ALL TABLES IN SCHEMA demo TO anon, authenticated, service_role;\n",
        )
        _write(
            root,
            "products/demo/backend/migrations/002_unrelated.sql",
            "ALTER TABLE demo.widgets ADD COLUMN foo text;\n",
        )

        issues = check_schema_wide_anon_grant(
            repo_root=root,
            paths=["products/demo/backend/migrations/002_unrelated.sql"],
        )

        assert issues == []

    def test_paths_scoped_still_flags_a_newly_staged_violation(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/003_new.sql",
            "GRANT ALL ON ALL TABLES IN SCHEMA demo TO anon;\n",
        )

        issues = check_schema_wide_anon_grant(
            repo_root=root,
            paths=["products/demo/backend/migrations/003_new.sql"],
        )

        assert len(issues) == 1


class TestNoAllowlistOrSuppression:
    def test_function_has_no_suppression_kwarg(self):
        import inspect

        sig = inspect.signature(check_schema_wide_anon_grant)
        assert "allow_anon_grant" not in sig.parameters
        assert "force" not in sig.parameters
        assert "skip" not in sig.parameters

    def test_every_finding_is_critical_severity(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "GRANT ALL ON ALL TABLES IN SCHEMA demo TO anon;\n"
            "ALTER DEFAULT PRIVILEGES IN SCHEMA demo GRANT ALL ON TABLES TO anon;\n",
        )

        issues = check_schema_wide_anon_grant(repo_root=root)

        assert len(issues) == 2
        assert all(i["severity"] == "critical" for i in issues)


class TestSchemaWideAnonGrant:
    """Convention-named entry point for `check_detector_has_regression_test`.

    That meta-keeper matches a detector to its suite BY CLASS NAME
    (`"Test" + _camel_case(detector.removeprefix("check_"))`), so the
    behaviour-named classes above are invisible to it however thorough they
    are. CI proved it on 2026-09-20: this keeper landed WITH 27 real tests
    and the suite still failed `Detectors missing regression tests`.
    Still asserts a real REFUSAL, not just that the detector ran.
    """

    def test_blanket_anon_grant_is_refused(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "GRANT ALL ON ALL TABLES IN SCHEMA demo TO anon, authenticated, service_role;\n",
        )
        issues = check_schema_wide_anon_grant(repo_root=root)
        assert issues, "a blanket anon table grant must be refused, not passed"
        assert issues[0]["severity"] == "critical"

    def test_anon_usage_only_is_clean(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "GRANT USAGE ON SCHEMA demo TO anon, authenticated, service_role;\n"
            "GRANT ALL ON ALL TABLES IN SCHEMA demo TO service_role;\n",
        )
        assert check_schema_wide_anon_grant(repo_root=root) == []
