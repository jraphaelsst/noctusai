"""Regression tests for ``noctus.dev.compliance.check_storage_bucket_public``
— the STATIC half of the zero-public-bucket gate.

THE INCIDENT this keeper exists for (2026-09-17): `erp-certidoes` (102
CPF-bearing objects) + `erp-geral` were declared `public = true` in
`products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql` +
`011_storage_buckets.sql`. `storage.objects` had RLS enabled with 17
policies and gave ZERO protection, because a PUBLIC bucket serves objects
via `/object/public/{bucket}/{path}`, a route that bypasses RLS entirely.

All tests operate against an isolated ``tmp_path`` tree, never the real
repo — keeps the suite hermetic and fast, and means this file's own Leg B/C
fixture strings for the public-URL API (Python's get_public_url / JS's
getPublicUrl, each called as a function) and for runtime bucket creation
(create_bucket, called as a function) never leak into a real full-tree scan
of ``mcp/`` — those three trigger strings are built by concatenation below
(mirrors ``test_conflict_markers_detector.py``'s "markers built by
character repetition, not written literally" idiom) so this test file
cannot trip the detector it is testing when CI runs the keeper's own
full-tree audit mode over ``mcp/``.

KB § PATTERNS/backend/database-rls.md § Storage buckets — never public.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_storage_bucket_public

# Built by concatenation — see module docstring for why.
_GET_PUBLIC_URL_CALL = "get_public_url" + "(" + "path)"
_GET_PUBLIC_URL_JS_CALL = "getPublicUrl" + "(" + "path)"
_CREATE_BUCKET_CALL_PUBLIC_TRUE = "create_bucket" + "('x', public=True)"
_CREATE_BUCKET_CALL_PUBLIC_FALSE = "create_bucket" + "('x', public=False)"
_CREATE_BUCKET_CALL_NO_PUBLIC_KWARG = "create_bucket" + "('x')"


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _make_products_root(tmp_path: Path) -> Path:
    # Leg A globs `products/*/backend/migrations/*.sql` off `repo_root`.
    (tmp_path / "products").mkdir()
    return tmp_path


class TestLegA_MigrationInsert:
    def test_insert_with_explicit_column_list_public_true_is_flagged(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_buckets.sql",
            "INSERT INTO storage.buckets (id, name, public)\n"
            "VALUES ('demo-bucket', 'demo-bucket', true)\n"
            "ON CONFLICT (id) DO NOTHING;\n",
        )

        issues = check_storage_bucket_public(repo_root=root)

        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert issues[0]["file"] == "products/demo/backend/migrations/001_buckets.sql"
        assert "public = true" in issues[0]["issue"]

    def test_insert_with_explicit_column_list_public_false_is_clean(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_buckets.sql",
            "INSERT INTO storage.buckets (id, name, public)\n"
            "VALUES ('demo-bucket', 'demo-bucket', false)\n"
            "ON CONFLICT (id) DO NOTHING;\n",
        )

        assert check_storage_bucket_public(repo_root=root) == []

    def test_insert_with_no_column_list_is_not_flagged(self, tmp_path):
        """Documented precision limit: Supabase's own column default for
        `public` is `false`, so an INSERT that never names the column
        cannot make a bucket public — not flagged."""
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_buckets.sql",
            "INSERT INTO storage.buckets\nVALUES ('demo-bucket', 'demo-bucket', true);\n",
        )

        assert check_storage_bucket_public(repo_root=root) == []

    def test_multiple_bucket_tuples_flags_the_public_one_only(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_buckets.sql",
            "INSERT INTO storage.buckets (id, name, public)\n"
            "VALUES\n"
            "    ('private-one', 'private-one', false),\n"
            "    ('public-one', 'public-one', true)\n"
            "ON CONFLICT (id) DO NOTHING;\n",
        )

        issues = check_storage_bucket_public(repo_root=root)

        assert len(issues) == 1


class TestLegA_MigrationUpdate:
    def test_update_set_public_true_is_flagged(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/002_reopen.sql",
            "UPDATE storage.buckets SET public = true WHERE id = 'demo-bucket';\n",
        )

        issues = check_storage_bucket_public(repo_root=root)

        assert len(issues) == 1
        assert "re-opens" in issues[0]["issue"]

    def test_update_set_public_false_is_clean(self, tmp_path):
        """THE SANCTIONED SHAPE — migration 048's own UPDATE statement.
        Its WHERE clause also contains the literal text `public = true`
        (the read predicate), which must NOT be mistaken for the SET
        clause — this is the regression for exactly that confusion."""
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/048_storage_no_public_buckets.sql",
            "UPDATE storage.buckets\n"
            "SET public = false\n"
            "WHERE id IN ('erp-certidoes', 'erp-geral')\n"
            "  AND public = true;\n",
        )

        assert check_storage_bucket_public(repo_root=root) == []


class TestLegB_GetPublicUrlCallSite:
    def test_python_get_public_url_call_is_flagged(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/app/services/storage_service.py",
            f"public_url = self.client.storage.from_(bucket).{_GET_PUBLIC_URL_CALL}\n",
        )

        issues = check_storage_bucket_public(repo_root=root)

        assert len(issues) == 1
        assert "public-URL API" in issues[0]["issue"]

    def test_js_getpublicurl_call_is_flagged(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/frontend/src/lib/storage.ts",
            f"const {{ data }} = supabase.storage.from(bucket).{_GET_PUBLIC_URL_JS_CALL};\n",
        )

        issues = check_storage_bucket_public(repo_root=root)

        assert len(issues) == 1

    def test_get_public_url_mentioned_without_a_call_is_not_flagged(self, tmp_path):
        """`.get_public_url.return_value = ...` (a Mock attribute access,
        the real shape in the pre-fix test suite) has no open-paren
        immediately following the identifier and is not a call site."""
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/tests/services/test_storage_service.py",
            "mock_bucket.get_public_url.return_value = 'https://example.com'\n",
        )

        assert check_storage_bucket_public(repo_root=root) == []


class TestLegC_RuntimeCreateBucket:
    def test_create_bucket_public_true_is_flagged(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/app/services/storage_admin.py",
            f"client.storage.{_CREATE_BUCKET_CALL_PUBLIC_TRUE}\n",
        )

        issues = check_storage_bucket_public(repo_root=root)

        assert len(issues) == 1
        assert "runtime" in issues[0]["issue"]

    def test_create_bucket_public_false_is_not_flagged(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/app/services/storage_admin.py",
            f"client.storage.{_CREATE_BUCKET_CALL_PUBLIC_FALSE}\n",
        )

        assert check_storage_bucket_public(repo_root=root) == []

    def test_create_bucket_with_no_public_kwarg_is_not_flagged(self, tmp_path):
        """Documented precision limit — this leg does not model per-SDK
        default values for an omitted `public` kwarg."""
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/app/services/storage_admin.py",
            f"client.storage.{_CREATE_BUCKET_CALL_NO_PUBLIC_KWARG}\n",
        )

        assert check_storage_bucket_public(repo_root=root) == []


class TestPathsScoping:
    """Pre-commit's diff-scoped mode (`paths=[...]`) — 001/011-shaped
    immutable history must not re-block every future commit; see the
    function's own docstring for the full reasoning."""

    def test_paths_none_scans_whole_tree(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_history.sql",
            "INSERT INTO storage.buckets (id, name, public)\n"
            "VALUES ('demo-bucket', 'demo-bucket', true);\n",
        )

        assert len(check_storage_bucket_public(repo_root=root)) == 1

    def test_paths_scoped_ignores_untouched_violating_file(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_history.sql",
            "INSERT INTO storage.buckets (id, name, public)\n"
            "VALUES ('demo-bucket', 'demo-bucket', true);\n",
        )
        _write(
            root,
            "products/demo/backend/migrations/002_unrelated.sql",
            "ALTER TABLE demo.widgets ADD COLUMN foo text;\n",
        )

        issues = check_storage_bucket_public(
            repo_root=root,
            paths=["products/demo/backend/migrations/002_unrelated.sql"],
        )

        assert issues == []

    def test_paths_scoped_still_flags_a_newly_staged_violation(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/003_new.sql",
            "INSERT INTO storage.buckets (id, name, public)\n"
            "VALUES ('demo-bucket', 'demo-bucket', true);\n",
        )

        issues = check_storage_bucket_public(
            repo_root=root,
            paths=["products/demo/backend/migrations/003_new.sql"],
        )

        assert len(issues) == 1


class TestNoAllowlistOrSuppression:
    """Owner directive (2026-09-17): this keeper carries NO allowlist, NO
    suppression marker, and NO accept-with-rationale escape hatch —
    a deliberate exception to this file's own convention."""

    def test_function_has_no_suppression_kwarg(self):
        import inspect

        sig = inspect.signature(check_storage_bucket_public)
        assert "allow_public_bucket" not in sig.parameters
        assert "force" not in sig.parameters
        assert "accept" not in sig.parameters
        assert "skip" not in sig.parameters

    def test_every_finding_is_critical_severity(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_buckets.sql",
            "INSERT INTO storage.buckets (id, name, public)\n"
            "VALUES ('demo-bucket', 'demo-bucket', true);\n",
        )

        issues = check_storage_bucket_public(repo_root=root)

        assert all(i["severity"] == "critical" for i in issues)

    def test_every_finding_names_the_sanctioned_alternative(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_buckets.sql",
            "INSERT INTO storage.buckets (id, name, public)\n"
            "VALUES ('demo-bucket', 'demo-bucket', true);\n",
        )

        issues = check_storage_bucket_public(repo_root=root)

        assert "signed URL" in issues[0]["issue"]
        assert "get_signed_url" in issues[0]["issue"]
