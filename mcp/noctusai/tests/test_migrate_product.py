"""Tests for ``noctus.dev.migrate_product``.

All tests are fully hermetic — they use ``FakeSqlExecutor`` / ``FakeGitRunner``
and a tmp-path products directory, so zero real Supabase calls AND zero real
git processes are made.

Test seam design:
  - ``executor=FakeSqlExecutor(...)`` injection avoids network.
  - ``products_dir=tmp_path/"products"`` injection avoids PRODUCTS_DIR.
  - ``git_runner=FakeGitRunner(...)`` injection avoids shelling out to real
    git (the stale-tree refusal gate's DI seam — every call below that
    doesn't specifically test that gate uses ``_clean_git_runner()``, a
    canned "fresh, clean, up-to-date" tree, so unrelated tests never trip
    the new default-on refusal nor touch the real repo).
  - ``live_products_fn=_live_catalog_fn(<slug>)`` injection avoids the real
    Supabase catalog / ``build-scope.txt`` fallback (the catalog-scope
    refusal gate's DI seam — every call below that isn't specifically
    testing ``TestMigrateProductCatalogScopeGate`` whitelists the product
    under test so it never trips the new default-on refusal).
  - No monkey-patching of our own code (per KB § PATTERNS/compliance/testing.md).
  - ``patch.object`` is only used on ``urllib.request`` (external service) in
    the ``SupabaseMgmtExecutor`` smoke test, which is the allowed carve-out.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Wire the MCP package to be importable in tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

from tools.noctus.dev import build_scope as BS  # noqa: E402
from tools.noctus.dev.migrate_product import (  # noqa: E402
    FakeGitRunner,
    FakeSqlExecutor,
    GitQueryError,
    SupabaseMgmtExecutor,
    _check_tree_staleness,
    _checksum,
    _copy_ledger_rows_sql,
    _delete_phantom_ledger_rows_sql,
    _dirty_migration_paths,
    _ensure_tracking_table_sql,
    _fetch_applied_sql,
    _quote_ident,
    _record_migration_sql,
    _resolve_schema,
    _schema_from_main_py,
    _schema_migrations_exists_sql,
    _slug_to_schema,
    _sorted_migrations,
    make_sql_executor,
    migrate_product,
    repair_schema_migrations_ledger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_products_dir(tmp_path: Path) -> Path:
    p = tmp_path / "products"
    p.mkdir()
    return p


def _clean_git_runner() -> FakeGitRunner:
    """A FakeGitRunner reporting a fresh, clean, up-to-date tree.

    Used by every test below that is NOT specifically exercising the
    stale-tree refusal gate, so those tests keep testing what they were
    testing (Supabase migration logic) without tripping the new
    default-on gate — and without shelling out to the real repo.
    """
    return FakeGitRunner(
        responses={
            ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
            ("rev-list", "--count", "HEAD..origin/dev"): "0",
            ("status", "--porcelain"): "",
        }
    )


def _sha_git_runner(sha: str, extra: dict[tuple, str] | None = None, fail_on=None) -> FakeGitRunner:
    """R3: `_clean_git_runner()` plus whatever `ls-tree`/`show` responses a
    sha-mode test needs — same "clean, up-to-date" staleness answers by
    default (most sha tests don't care), merged with the caller's overrides.
    Also auto-answers F8(b)'s `rev-parse --verify <sha>^{commit}` resolve-
    and-pin call with `sha` itself (i.e. "already a full, verified sha") —
    every sha-mode test needs this to reach its own scenario; override via
    `extra` to test resolution failure specifically."""
    responses = {
        ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
        ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
        ("rev-list", "--count", "HEAD..origin/dev"): "0",
        ("status", "--porcelain"): "",
        ("rev-parse", "--verify", f"{sha}^{{commit}}"): sha,
    }
    responses.update(extra or {})
    return FakeGitRunner(responses=responses, fail_on=fail_on or set())


def _live_catalog_fn(*slugs: str):
    """An in-scope catalog stub — same DI-seam role as ``_clean_git_runner()``,
    but for the 2026-09-17 catalog-scope guard. Every test below that is NOT
    specifically exercising the catalog-scope refusal injects this (with the
    product slug under test) so that new default-on gate never fires for
    unrelated Supabase-migration-logic tests, and none of them touch the
    real catalog / ``build-scope.txt`` fallback file."""
    return lambda: list(slugs)


def _make_main_py(products_dir: Path, product_slug: str, body: str) -> Path:
    """Write a fake ``app/main.py`` — the source `_schema_from_main_py` reads."""
    app_dir = products_dir / product_slug / "backend" / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    main_py = app_dir / "main.py"
    main_py.write_text(body, encoding="utf-8")
    return main_py


def _make_migration_files(
    products_dir: Path,
    product_slug: str,
    files: list[tuple[str, str]],  # (filename, sql_content)
) -> Path:
    mig_dir = products_dir / product_slug / "backend" / "migrations"
    mig_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files:
        (mig_dir / name).write_text(content, encoding="utf-8")
    return mig_dir


# ---------------------------------------------------------------------------
# Unit: helper functions
# ---------------------------------------------------------------------------


class TestSlugToSchema:
    def test_simple(self):
        assert _slug_to_schema("orbity") == "orbity"

    def test_hyphen_to_underscore(self):
        assert _slug_to_schema("erp-imobiliario") == "erp_imobiliario"

    def test_multiple_hyphens(self):
        assert _slug_to_schema("daily-life") == "daily_life"


class TestSortedMigrations:
    def test_sorted_by_numeric_prefix(self, tmp_path):
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        for name in ["003_third.sql", "001_first.sql", "002_second.sql"]:
            (mig_dir / name).write_text("-- stub")
        result = _sorted_migrations(mig_dir)
        assert [f.name for f in result] == [
            "001_first.sql",
            "002_second.sql",
            "003_third.sql",
        ]

    def test_non_numbered_files_skipped(self, tmp_path):
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        (mig_dir / "001_valid.sql").write_text("-- valid")
        (mig_dir / "README.md").write_text("# notes")
        (mig_dir / "scratch.sql").write_text("-- scratch, no prefix")
        result = _sorted_migrations(mig_dir)
        assert [f.name for f in result] == ["001_valid.sql"]

    def test_empty_directory(self, tmp_path):
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        assert _sorted_migrations(mig_dir) == []


class TestChecksum:
    def test_deterministic(self):
        sql = "CREATE TABLE foo (id SERIAL);"
        assert _checksum(sql) == _checksum(sql)

    def test_different_sql_different_checksum(self):
        assert _checksum("SELECT 1;") != _checksum("SELECT 2;")

    def test_returns_hex_string(self):
        result = _checksum("CREATE SCHEMA orbity;")
        assert all(c in "0123456789abcdef" for c in result)
        assert len(result) == 64  # SHA-256 hex


class TestSqlBuilders:
    def test_ensure_tracking_table_has_create_if_not_exists(self):
        sql = _ensure_tracking_table_sql("orbity")
        # Schema identifiers are always double-quoted (required for a
        # hyphenated schema like "personal-finance"; a no-op for "orbity").
        assert 'CREATE TABLE IF NOT EXISTS "orbity".schema_migrations' in sql
        assert "filename" in sql
        assert "checksum" in sql

    def test_ensure_tracking_table_creates_schema(self):
        sql = _ensure_tracking_table_sql("erp_imobiliario")
        assert 'CREATE SCHEMA IF NOT EXISTS "erp_imobiliario"' in sql

    def test_ensure_tracking_table_quotes_hyphenated_schema(self):
        """personal-finance's hyphen is not a valid unquoted identifier char —
        unquoted, CREATE SCHEMA IF NOT EXISTS personal-finance is a syntax
        error (parsed as `personal` MINUS a bareword `finance`)."""
        sql = _ensure_tracking_table_sql("personal-finance")
        assert 'CREATE SCHEMA IF NOT EXISTS "personal-finance"' in sql
        assert '"personal-finance".schema_migrations' in sql

    def test_ensure_tracking_table_locks_down_rls(self):
        """schema_migrations is exposed via PostgREST like any other table in
        the schema — without RLS + a revoke, anon/authenticated can read or
        edit the ledger over REST (e.g. insert a filename to make a future
        migrate_product run silently skip a real migration). Verified live
        on nyplttplcoyiiqjrvtiw 2026-09-16: an anon REST call returned 42501
        after this fix; the Management-API executor (table owner) was
        unaffected."""
        sql = _ensure_tracking_table_sql("orbity")
        assert 'ALTER TABLE "orbity".schema_migrations ENABLE ROW LEVEL SECURITY' in sql
        assert 'REVOKE ALL ON "orbity".schema_migrations FROM anon, authenticated' in sql

    def test_ensure_tracking_table_locks_down_rls_hyphenated_schema(self):
        sql = _ensure_tracking_table_sql("personal-finance")
        assert (
            'ALTER TABLE "personal-finance".schema_migrations ENABLE ROW LEVEL SECURITY'
            in sql
        )
        assert (
            'REVOKE ALL ON "personal-finance".schema_migrations FROM anon, authenticated'
            in sql
        )

    def test_fetch_applied_selects_filename(self):
        sql = _fetch_applied_sql("orbity")
        assert "SELECT filename" in sql
        assert '"orbity".schema_migrations' in sql

    def test_record_migration_uses_on_conflict(self):
        sql = _record_migration_sql("orbity", "001_seed.sql", "abc123")
        assert "ON CONFLICT (filename) DO NOTHING" in sql
        assert "001_seed.sql" in sql
        assert "abc123" in sql


# ---------------------------------------------------------------------------
# FakeSqlExecutor
# ---------------------------------------------------------------------------


class TestFakeSqlExecutor:
    def test_records_executed(self):
        fake = FakeSqlExecutor()
        fake.execute("SELECT 1;")
        fake.execute("SELECT 2;")
        assert len(fake.executed) == 2

    def test_preset_rows_matched_by_substring(self):
        rows = [{"filename": "001_seed.sql"}]
        fake = FakeSqlExecutor(preset_rows={"schema_migrations": rows})
        result = fake.execute("SELECT filename FROM orbity.schema_migrations;")
        assert result["ok"] is True
        assert result["rows"] == rows

    def test_fail_on_fragment(self):
        fake = FakeSqlExecutor(fail_on={"DROP TABLE"})
        result = fake.execute("DROP TABLE orbity.foo;")
        assert result["ok"] is False
        assert "fake-failure" in result["error"]

    def test_no_match_returns_empty_rows(self):
        fake = FakeSqlExecutor()
        result = fake.execute("CREATE SCHEMA IF NOT EXISTS foo;")
        assert result["ok"] is True
        assert result["rows"] == []


# ---------------------------------------------------------------------------
# migrate_product — dry-run behaviour
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_lists_pending_without_applying(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products,
            "orbity",
            [
                ("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;"),
                ("002_crm.sql", "CREATE TABLE orbity.contacts (id SERIAL);"),
            ],
        )
        fake = FakeSqlExecutor()  # tracking table returns no rows → all pending

        result = migrate_product("orbity", confirm=False, executor=fake, products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"))

        assert result["status"] == "dry_run"
        assert result["pending"] == ["001_seed.sql", "002_crm.sql"]
        assert result["applied"] == []
        assert result["skipped_already_applied"] == []
        assert result["error"] is None

    def test_dry_run_does_not_apply(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")]
        )
        fake = FakeSqlExecutor()
        migrate_product("orbity", confirm=False, executor=fake, products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"))
        # The only SQL calls should be ensure-table + fetch-applied (2), NOT
        # the migration body itself.
        assert len(fake.executed) == 2

    def test_dry_run_skips_already_applied(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products,
            "orbity",
            [
                ("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;"),
                ("002_crm.sql", "CREATE TABLE orbity.contacts (id SERIAL);"),
            ],
        )
        # Simulate 001 already applied
        fake = FakeSqlExecutor(
            preset_rows={
                "SELECT filename": [{"filename": "001_seed.sql"}]
            }
        )
        result = migrate_product("orbity", confirm=False, executor=fake, products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"))

        assert result["status"] == "dry_run"
        assert result["pending"] == ["002_crm.sql"]
        assert result["skipped_already_applied"] == ["001_seed.sql"]


# ---------------------------------------------------------------------------
# migrate_product — confirm=True (apply)
# ---------------------------------------------------------------------------


class TestConfirmApply:
    def test_applies_pending_and_records(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products,
            "orbity",
            [
                ("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;"),
                ("002_crm.sql", "CREATE TABLE orbity.contacts (id SERIAL);"),
            ],
        )
        fake = FakeSqlExecutor()

        result = migrate_product("orbity", confirm=True, executor=fake, products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"))

        assert result["status"] == "applied"
        assert result["applied"] == ["001_seed.sql", "002_crm.sql"]
        assert result["pending"] == []
        assert result["error"] is None

    def test_applied_files_are_executed(self, tmp_path):
        products = _make_products_dir(tmp_path)
        sql_001 = "CREATE SCHEMA IF NOT EXISTS orbity;"
        _make_migration_files(products, "orbity", [("001_seed.sql", sql_001)])
        fake = FakeSqlExecutor()

        migrate_product("orbity", confirm=True, executor=fake, products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"))

        # executed should contain: ensure_table + fetch_applied + migration_sql + record_sql
        assert any(sql_001 in s for s in fake.executed), "migration body was not executed"
        assert any('INSERT INTO "orbity".schema_migrations' in s for s in fake.executed), (
            "tracking INSERT was not executed"
        )

    def test_skips_already_applied_on_rerun(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products,
            "orbity",
            [
                ("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;"),
                ("002_crm.sql", "CREATE TABLE orbity.contacts (id SERIAL);"),
            ],
        )
        # Simulate both already applied
        fake = FakeSqlExecutor(
            preset_rows={
                "SELECT filename": [
                    {"filename": "001_seed.sql"},
                    {"filename": "002_crm.sql"},
                ]
            }
        )

        result = migrate_product("orbity", confirm=True, executor=fake, products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"))

        assert result["status"] == "up_to_date"
        assert result["applied"] == []
        assert result["skipped_already_applied"] == ["001_seed.sql", "002_crm.sql"]

    def test_apply_stops_on_first_failure(self, tmp_path):
        products = _make_products_dir(tmp_path)
        sql_001 = "CREATE SCHEMA IF NOT EXISTS orbity;"
        sql_002 = "INTENTIONALLY_BAD_SQL;"
        _make_migration_files(
            products,
            "orbity",
            [
                ("001_seed.sql", sql_001),
                ("002_bad.sql", sql_002),
                ("003_would_be_skipped.sql", "SELECT 1;"),
            ],
        )
        fake = FakeSqlExecutor(fail_on={sql_002})

        result = migrate_product("orbity", confirm=True, executor=fake, products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"))

        assert result["status"] == "error"
        assert "002_bad.sql" in result["error"]
        assert result["applied"] == ["001_seed.sql"]
        # 003 must still be listed as pending (not applied, not skipped)
        assert "003_would_be_skipped.sql" in result["pending"]


# ---------------------------------------------------------------------------
# target= (single-file filter)
# ---------------------------------------------------------------------------


class TestTargetFilter:
    def test_target_limits_to_one_file(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products,
            "orbity",
            [
                ("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;"),
                ("002_crm.sql", "CREATE TABLE orbity.contacts (id SERIAL);"),
            ],
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity",
            confirm=False,
            target="001_seed.sql",
            executor=fake,
            products_dir=products,
            git_runner=_clean_git_runner(),
            live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["pending"] == ["001_seed.sql"]

    def test_target_not_found_returns_error(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")]
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity",
            confirm=False,
            target="999_does_not_exist.sql",
            executor=fake,
            products_dir=products,
            git_runner=_clean_git_runner(),
            live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "error"
        assert "999_does_not_exist.sql" in result["error"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestMigrateProductShaSource:
    """R3 (release-no-freeze): sha= reads migration FILES via `git show`,
    never the working tree — and skips the stale-tree refusal entirely
    (there is nothing "stale" about a pinned historical commit)."""

    def test_dry_run_lists_pending_from_the_sha_not_the_working_tree(self, tmp_path):
        products = _make_products_dir(tmp_path)
        # The WORKING TREE has NOTHING — proves the sha path, not this, is used.
        _make_migration_files(products, "orbity", [])
        sha = "deadbeef" * 5
        runner = _sha_git_runner(sha, {
            ("ls-tree", "--name-only", "-r", sha, "--", "products/orbity/backend/migrations"):
                "products/orbity/backend/migrations/001_seed.sql\n"
                "products/orbity/backend/migrations/002_more.sql\n",
            ("show", f"{sha}:products/orbity/backend/migrations/001_seed.sql"):
                "CREATE SCHEMA IF NOT EXISTS orbity;",
            ("show", f"{sha}:products/orbity/backend/migrations/002_more.sql"):
                "CREATE TABLE orbity.x (id int);",
        })
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=False, sha=sha, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "dry_run", result
        assert result["pending"] == ["001_seed.sql", "002_more.sql"]
        assert result["sha"] == sha

    def test_confirmed_apply_reads_content_via_git_show(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [])
        sha = "cafebabe" * 5
        runner = _sha_git_runner(sha, {
            ("ls-tree", "--name-only", "-r", sha, "--", "products/orbity/backend/migrations"):
                "products/orbity/backend/migrations/001_seed.sql\n",
            ("show", f"{sha}:products/orbity/backend/migrations/001_seed.sql"):
                "CREATE SCHEMA IF NOT EXISTS orbity;",
            # N3 (compliance review, 2026-09-24): configure a real,
            # readable main.py so schema_source != 'slug_fallback' — this
            # test is about the confirm=True apply path, not schema
            # derivation, and N3 refuses confirm=True on an unverified
            # (slug_fallback) schema.
            ("show", f"{sha}:products/orbity/backend/app/main.py"):
                'app = create_product_app(name="Orbity", schema="orbity")\n',
        })
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=True, sha=sha, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "applied", result
        assert result["applied"] == ["001_seed.sql"]
        assert any("CREATE SCHEMA IF NOT EXISTS orbity" in s for s in fake.executed)

    def test_unreadable_sha_is_an_error_not_a_silent_working_tree_fallback(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")]
        )
        sha = "0000000" * 5
        runner = _sha_git_runner(sha, fail_on={
            ("ls-tree", "--name-only", "-r", sha, "--", "products/orbity/backend/migrations"),
        })
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=False, sha=sha, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "error"
        assert sha in result["error"]
        assert result["pending"] == []  # never silently fell back to the working tree

    def test_sha_bypasses_the_stale_tree_refusal(self, tmp_path):
        """A tree behind its upstream would normally refuse — sha= pins a
        historical commit, so staleness of the CHECKOUT is moot."""
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [])
        sha = "abc12340" * 5
        runner = FakeGitRunner(responses={
            ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
            ("rev-list", "--count", "HEAD..origin/dev"): "3",  # BEHIND upstream
            ("status", "--porcelain"): "",
            ("rev-parse", "--verify", f"{sha}^{{commit}}"): sha,
            ("ls-tree", "--name-only", "-r", sha, "--", "products/orbity/backend/migrations"):
                "products/orbity/backend/migrations/001_seed.sql\n",
            ("show", f"{sha}:products/orbity/backend/migrations/001_seed.sql"):
                "CREATE SCHEMA IF NOT EXISTS orbity;",
        })
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=False, sha=sha, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "dry_run", result  # NOT refused_stale_tree
        assert result["stale_tree"]["stale"] is True  # still computed, still visible
        assert result["pending"] == ["001_seed.sql"]

    def test_no_sha_behind_upstream_still_refuses_unchanged(self, tmp_path):
        """Regression guard: the pre-R3 (no sha) behaviour is untouched."""
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [("001_seed.sql", "x;")])
        runner = FakeGitRunner(responses={
            ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
            ("rev-list", "--count", "HEAD..origin/dev"): "3",
            ("status", "--porcelain"): "",
        })
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=False, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "refused_stale_tree"

    def test_sha_with_a_missing_migrations_dir_at_that_commit_is_an_error(self, tmp_path):
        """F8(a) (compliance review, 2026-09-24): git has no concept of an
        empty directory — a completely empty `ls-tree` means the migrations
        PATH ITSELF does not exist at this sha (wrong slug, or the product
        didn't exist yet), never a legitimate 'nothing to apply'. Must
        surface as status='error', never a misleadingly clean up_to_date."""
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [])
        sha = "1111111" * 5
        runner = _sha_git_runner(sha, {
            ("ls-tree", "--name-only", "-r", sha, "--", "products/orbity/backend/migrations"): "",
            # N3: real, readable main.py — this test is about F8(a)'s
            # missing-dir refusal, not schema derivation.
            ("show", f"{sha}:products/orbity/backend/app/main.py"):
                'app = create_product_app(name="Orbity", schema="orbity")\n',
        })
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=True, sha=sha, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "error"
        assert "does not exist" in result["error"]

    def test_sha_with_only_non_migration_files_present_is_up_to_date(self, tmp_path):
        """The LEGITIMATE 'nothing to apply yet' case: the migrations dir
        DOES exist at this sha (ls-tree returns real entries) but none of
        them are numbered .sql files — distinct from F8(a)'s "dir missing
        entirely" case above, which must error instead."""
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [])
        sha = "2222222" * 5
        runner = _sha_git_runner(sha, {
            ("ls-tree", "--name-only", "-r", sha, "--", "products/orbity/backend/migrations"):
                "products/orbity/backend/migrations/README.md\n",
            # N3: real, readable main.py — this test is about the
            # dir-exists-but-no-.sql-files up_to_date case, not schema
            # derivation.
            ("show", f"{sha}:products/orbity/backend/app/main.py"):
                'app = create_product_app(name="Orbity", schema="orbity")\n',
        })
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=True, sha=sha, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "up_to_date"

    def test_sha_is_resolved_once_and_pinned_to_the_full_sha(self, tmp_path):
        """F8(b) (compliance review, 2026-09-24): a SHORT/abbreviated sha is
        resolved to a FULL, verified commit sha via `git rev-parse --verify
        <sha>^{commit}` exactly once — every downstream use (schema
        derivation, migration listing, the result payload) sees the SAME
        pinned full sha, never the caller's original short form."""
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [])
        short = "cafe123"
        full = "cafe123" + "0" * 33  # 40 hex chars total
        runner = FakeGitRunner(responses={
            ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
            ("rev-list", "--count", "HEAD..origin/dev"): "0",
            ("status", "--porcelain"): "",
            ("rev-parse", "--verify", f"{short}^{{commit}}"): full,
            ("ls-tree", "--name-only", "-r", full, "--", "products/orbity/backend/migrations"):
                "products/orbity/backend/migrations/001_seed.sql\n",
            ("show", f"{full}:products/orbity/backend/migrations/001_seed.sql"):
                "CREATE SCHEMA IF NOT EXISTS orbity;",
        })
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=False, sha=short, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "dry_run", result
        assert result["sha"] == full  # pinned to the FULL sha, not the caller's short form
        assert result["pending"] == ["001_seed.sql"]

    def test_sha_that_does_not_resolve_to_a_commit_is_an_error(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [])
        sha = "notarealsha" * 4
        runner = FakeGitRunner(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
                ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
                ("rev-list", "--count", "HEAD..origin/dev"): "0",
                ("status", "--porcelain"): "",
            },
            fail_on={("rev-parse", "--verify", f"{sha}^{{commit}}")},
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=False, sha=sha, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "error"
        assert "does not resolve to a real commit" in result["error"]
        # never silently fell back to the working tree
        assert result.get("applied", []) == [] and result.get("pending", []) == []

    def test_checksum_uses_raw_bytes_not_rstripped_git_show_output(self, tmp_path):
        """F8(d) (compliance review, 2026-09-24): the SAME migration content
        must checksum identically whether read from the working tree
        (`Path.read_text()`, never stripped) or via `git show` at a sha —
        `GitRunner.run` deliberately `.rstrip()`s (correct for porcelain
        queries), which would silently drop this file's trailing newline
        and produce a DIFFERENT checksum than the working-tree path. Proven
        here via the recorded migration's checksum matching the raw
        (trailing-newline-preserving) content, not the rstripped one."""
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [])
        sha = "deadf00d" * 5
        raw_sql = "CREATE SCHEMA IF NOT EXISTS orbity;\n\n"  # trailing blank line + newline
        runner = _sha_git_runner(sha, {
            ("ls-tree", "--name-only", "-r", sha, "--", "products/orbity/backend/migrations"):
                "products/orbity/backend/migrations/001_seed.sql\n",
            ("show", f"{sha}:products/orbity/backend/migrations/001_seed.sql"): raw_sql,
            # N3: real, readable main.py — this test is about checksum
            # byte-fidelity, not schema derivation.
            ("show", f"{sha}:products/orbity/backend/app/main.py"):
                'app = create_product_app(name="Orbity", schema="orbity")\n',
        })
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=True, sha=sha, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "applied", result
        record_calls = [s for s in fake.executed if "INSERT" in s and "schema_migrations" in s]
        assert record_calls, fake.executed
        expected_checksum = _checksum(raw_sql)  # the RAW, un-rstripped content
        assert expected_checksum in record_calls[0]
        assert _checksum(raw_sql.rstrip()) not in record_calls[0]

    def test_schema_is_derived_from_main_py_at_the_sha_not_the_working_tree(self, tmp_path):
        """F8(e) (compliance review, 2026-09-24, closes NOC-REMEDIATE[migrate-
        product-sha-schema]): in sha= mode, the schema is AST-derived from
        `app/main.py` AS IT EXISTED AT THAT SHA — proven here by the
        WORKING TREE declaring a DIFFERENT schema than the sha does, and
        the sha's schema winning."""
        products = _make_products_dir(tmp_path)
        # Working tree declares "workingtree_schema" — must be IGNORED.
        main_py = products / "orbity" / "backend" / "app" / "main.py"
        main_py.parent.mkdir(parents=True)
        main_py.write_text(
            'app = create_product_app(name="Orbity", schema="workingtree_schema")\n'
        )
        mig_dir = products / "orbity" / "backend" / "migrations"
        mig_dir.mkdir(parents=True)
        sha = "5ca1ab1e" * 5
        runner = _sha_git_runner(sha, {
            ("show", f"{sha}:products/orbity/backend/app/main.py"):
                'app = create_product_app(name="Orbity", schema="sha_schema")\n',
            ("ls-tree", "--name-only", "-r", sha, "--", "products/orbity/backend/migrations"):
                "products/orbity/backend/migrations/001_seed.sql\n",
            ("show", f"{sha}:products/orbity/backend/migrations/001_seed.sql"):
                "CREATE TABLE x (id int);",
        })
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=False, sha=sha, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["schema"] == "sha_schema"
        assert result["schema_source"] == "main_py_declaration_at_sha"

    def test_confirm_true_refuses_when_schema_source_is_slug_fallback(self, tmp_path):
        """N3 (compliance review, 2026-09-24): in sha= mode, a GUESSED
        schema (`app/main.py` unreadable/undeclared at that sha, so
        `_resolve_schema` fell all the way back to the naive slug-transform)
        must refuse a confirm=True write — applying DDL against an
        unverified target is exactly the silent-wrong-schema class F8(e)
        exists to close for the readable case. Proven by `show` on
        `main.py` failing (`fail_on`), driving `schema_source` to
        `'slug_fallback'`."""
        products = _make_products_dir(tmp_path)
        mig_dir = products / "orbity" / "backend" / "migrations"
        mig_dir.mkdir(parents=True)
        sha = "5ca1ab1e" * 5
        runner = _sha_git_runner(sha, {
            ("ls-tree", "--name-only", "-r", sha, "--", "products/orbity/backend/migrations"):
                "products/orbity/backend/migrations/001_seed.sql\n",
            ("show", f"{sha}:products/orbity/backend/migrations/001_seed.sql"):
                "CREATE TABLE x (id int);",
        }, fail_on={("show", f"{sha}:products/orbity/backend/app/main.py")})
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=True, sha=sha, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "error"
        assert result["schema_source"] == "slug_fallback"
        assert "slug_fallback" in result["error"]
        assert "GUESS" in result["error"]
        # Nothing was ever sent to the executor — refused before touching DB.
        assert fake.executed == []

    def test_confirm_false_still_dry_runs_when_schema_source_is_slug_fallback(self, tmp_path):
        """N3's refusal is confirm=True-only — a dry-run against a GUESSED
        schema is still useful (shows what WOULD be pending) and carries no
        write risk, so it must NOT be refused."""
        products = _make_products_dir(tmp_path)
        mig_dir = products / "orbity" / "backend" / "migrations"
        mig_dir.mkdir(parents=True)
        sha = "5ca1ab1e" * 5
        runner = _sha_git_runner(sha, {
            ("ls-tree", "--name-only", "-r", sha, "--", "products/orbity/backend/migrations"):
                "products/orbity/backend/migrations/001_seed.sql\n",
        }, fail_on={("show", f"{sha}:products/orbity/backend/app/main.py")})
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=False, sha=sha, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "dry_run"
        assert result["schema_source"] == "slug_fallback"
        assert result["pending"] == ["001_seed.sql"]

    def test_all_pending_content_is_read_before_any_ddl_runs(self, tmp_path):
        """F8(c) (compliance review, 2026-09-24): if a LATER pending file's
        content can't be read, NOTHING must have been applied yet — not even
        the earlier files in the set. Reading every pending file BEFORE
        running any DDL is what makes that guarantee possible; proven here
        by asserting the FIRST (readable) migration's DDL was never
        executed even though it sorts before the unreadable second one."""
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [])
        sha = "badc0ffee" * 4 + "b"  # 40 chars
        runner = _sha_git_runner(sha, {
            ("ls-tree", "--name-only", "-r", sha, "--", "products/orbity/backend/migrations"):
                "products/orbity/backend/migrations/001_first.sql\n"
                "products/orbity/backend/migrations/002_second.sql\n",
            ("show", f"{sha}:products/orbity/backend/migrations/001_first.sql"):
                "CREATE TABLE orbity.first (id int);",
            # N3 (compliance review, 2026-09-24): real, readable main.py —
            # this test is about F8(c)'s read-before-DDL ordering, not
            # schema derivation; without this, N3's slug_fallback refusal
            # would fire first and mask what this test actually exercises.
            ("show", f"{sha}:products/orbity/backend/app/main.py"):
                'app = create_product_app(name="Orbity", schema="orbity")\n',
            # 002_second.sql's `show` is deliberately UNCONFIGURED — falls
            # through FakeGitRunner's default empty-string return, which is
            # fine for `ls-tree` but here simulates "unreadable content" via
            # fail_on instead, so the read genuinely raises.
        }, fail_on={("show", f"{sha}:products/orbity/backend/migrations/002_second.sql")})
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=True, sha=sha, executor=fake, products_dir=products,
            git_runner=runner, live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "error"
        assert "before applying any DDL" in result["error"]
        # the FIRST migration's DDL was never sent to the executor at all —
        # proof the read-everything-first pass ran BEFORE any apply loop.
        assert not any("CREATE TABLE orbity.first" in s for s in fake.executed)
        assert result["applied"] == []

    def test_pending_read_refuses_on_undecodable_bytes(self, tmp_path):
        """N5 (compliance review, 2026-09-24): a pending migration file with
        invalid-UTF-8 bytes on disk must be caught by the SAME pre-read
        guard as an unreadable (`OSError`/`GitQueryError`) file — a
        `UnicodeDecodeError` is just as much a "could not verify this
        file's content before running any DDL" case as either of those, and
        the working-tree path (real `Path.read_text()`, not the git-blob
        seam) is exactly where real-world invalid bytes would show up."""
        products = _make_products_dir(tmp_path)
        mig_dir = products / "orbity" / "backend" / "migrations"
        mig_dir.mkdir(parents=True)
        (mig_dir / "001_bad_bytes.sql").write_bytes(b"CREATE TABLE x (\xff\xfe id int);")
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity", confirm=True, executor=fake, products_dir=products,
            git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "error"
        assert "before applying any DDL" in result["error"]
        # The migration's own DDL was never sent to the executor — only the
        # tracking-table-ensure/fetch-applied bookkeeping SQL that legitimately
        # runs before the pending-content pre-read (same shape as
        # `test_all_pending_content_is_read_before_any_ddl_runs` above).
        assert not any("001_bad_bytes" in s or "id int" in s for s in fake.executed)
        assert result["applied"] == []


class TestEdgeCases:
    def test_empty_migrations_dir_returns_up_to_date(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [])
        fake = FakeSqlExecutor()

        result = migrate_product("orbity", confirm=True, executor=fake, products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"))

        assert result["status"] == "up_to_date"
        assert result["applied"] == []
        assert result["pending"] == []

    def test_missing_product_dir_returns_error(self, tmp_path):
        products = _make_products_dir(tmp_path)
        fake = FakeSqlExecutor()

        result = migrate_product("nonexistent", confirm=False, executor=fake, products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("nonexistent"))

        assert result["status"] == "error"
        assert "nonexistent" in result["error"]

    def test_malformed_prefix_files_are_skipped(self, tmp_path):
        """Files without NNN_ prefix are silently skipped (logged at DEBUG)."""
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products,
            "orbity",
            [
                ("001_valid.sql", "CREATE SCHEMA IF NOT EXISTS orbity;"),
                ("no_prefix.sql", "-- scratch"),
                ("also_bad.sql", "-- also bad"),
            ],
        )
        fake = FakeSqlExecutor()

        result = migrate_product("orbity", confirm=False, executor=fake, products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"))

        assert result["pending"] == ["001_valid.sql"]

    def test_not_configured_when_no_token(self, tmp_path, monkeypatch):
        """When SUPABASE_ACCESS_TOKEN is absent and no executor injected, returns not_configured."""
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")]
        )
        monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
        # Neutralize the DB-first tier so this stays hermetic (no real DB read).
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda *a, **k: None,
        )

        result = migrate_product("orbity", products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"))  # no executor

        assert result["status"] == "not_configured"
        assert "SUPABASE_ACCESS_TOKEN" in result["error"]
        assert "NOC-REMEDIATE" in result["error"]

    def test_schema_override(self, tmp_path):
        """schema= arg overrides slug-derived schema."""
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS custom;")]
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity",
            confirm=False,
            schema="custom_schema",
            executor=fake,
            products_dir=products,
            git_runner=_clean_git_runner(),
            live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["schema"] == "custom_schema"
        # Verify tracking table was created in the custom schema
        assert any('"custom_schema".schema_migrations' in s for s in fake.executed)

    def test_ensure_table_failure_returns_error(self, tmp_path):
        """If tracking table creation fails, return error immediately."""
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")]
        )
        fake = FakeSqlExecutor(fail_on={"CREATE TABLE IF NOT EXISTS"})

        result = migrate_product("orbity", confirm=True, executor=fake, products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"))

        assert result["status"] == "error"
        assert "schema_migrations" in result["error"]

    def test_returns_correct_project_ref(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")]
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity",
            confirm=False,
            project_ref="testrefabcdef1234567",
            executor=fake,
            products_dir=products,
            git_runner=_clean_git_runner(),
            live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["project_ref"] == "testrefabcdef1234567"


# ---------------------------------------------------------------------------
# make_sql_executor factory
# ---------------------------------------------------------------------------


class TestMakeSqlExecutor:
    def test_returns_none_when_no_token(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
        # No DB row either — neutralize the DB-first tier deterministically.
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda *a, **k: None,
        )
        result = make_sql_executor()
        assert result is None

    def test_returns_executor_when_env_token_set(self, monkeypatch):
        # DB tier misses → falls back to the env token (Tier 3).
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda *a, **k: None,
        )
        monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "test-token-abc")
        result = make_sql_executor()
        assert result is not None
        assert isinstance(result, SupabaseMgmtExecutor)

    def test_db_first_token_resolution(self, monkeypatch):
        """No env token, but resolve_credential (DB platform_settings) provides one."""
        monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda key, org_id=None: (
                "db-token-xyz" if key == "supabase_access_token" else None
            ),
        )
        result = make_sql_executor()
        assert isinstance(result, SupabaseMgmtExecutor)

    def test_explicit_token_wins(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
        result = make_sql_executor(access_token="explicit-token")
        assert result is not None
        assert isinstance(result, SupabaseMgmtExecutor)


# ---------------------------------------------------------------------------
# Schema derivation — the 2026-09 fix: read the product's OWN declaration
# (create_product_app(schema="...") in app/main.py) instead of always
# guessing via the naive slug transform.
# ---------------------------------------------------------------------------


class TestSchemaFromMainPy:
    def test_derives_from_create_product_app_kwarg(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_main_py(
            products,
            "erp-imobiliario",
            'from noctusai_seed import create_product_app\n'
            'app = create_product_app(\n'
            '    name="ERP Imobiliario",\n'
            '    schema="erp",\n'
            '    settings=settings,\n'
            '    routers=[],\n'
            ')\n',
        )
        assert _schema_from_main_py("erp-imobiliario", products) == "erp"

    def test_derives_hyphenated_schema(self, tmp_path):
        """personal-finance declares its schema WITH the hyphen — the exact
        shape the naive slug transform can never produce."""
        products = _make_products_dir(tmp_path)
        _make_main_py(
            products,
            "personal-finance",
            'app = create_product_app(\n'
            '    name="Financas Pessoais",\n'
            '    schema="personal-finance",\n'
            '    settings=settings,\n'
            '    routers=[],\n'
            ')\n',
        )
        assert _schema_from_main_py("personal-finance", products) == "personal-finance"

    def test_derives_therapy_schema(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_main_py(
            products,
            "therapy-platform",
            'app = create_product_app(name="Therapy", schema="therapy", settings=settings, routers=[])\n',
        )
        assert _schema_from_main_py("therapy-platform", products) == "therapy"

    def test_missing_main_py_returns_none(self, tmp_path):
        products = _make_products_dir(tmp_path)
        assert _schema_from_main_py("nonexistent", products) is None

    def test_unparseable_main_py_returns_none(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "broken", "def f(:\n  this is not python\n")
        assert _schema_from_main_py("broken", products) is None

    def test_no_create_product_app_call_returns_none(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "weird", "x = 1\n")
        assert _schema_from_main_py("weird", products) is None

    def test_non_literal_schema_kwarg_returns_none(self, tmp_path):
        """schema=some_variable can't be derived without executing the
        module — must fall through to the caller's fallback, never guess."""
        products = _make_products_dir(tmp_path)
        _make_main_py(
            products,
            "dynamic",
            'SCHEMA = compute_schema()\n'
            'app = create_product_app(name="X", schema=SCHEMA, settings=settings, routers=[])\n',
        )
        assert _schema_from_main_py("dynamic", products) is None


class TestResolveSchema:
    def test_explicit_override_wins(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_main_py(
            products, "erp-imobiliario",
            'app = create_product_app(name="X", schema="erp", settings=settings, routers=[])\n',
        )
        schema, source = _resolve_schema("erp-imobiliario", "custom", products)
        assert (schema, source) == ("custom", "explicit_override")

    def test_main_py_declaration_used_when_no_override(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_main_py(
            products, "erp-imobiliario",
            'app = create_product_app(name="X", schema="erp", settings=settings, routers=[])\n',
        )
        schema, source = _resolve_schema("erp-imobiliario", None, products)
        assert (schema, source) == ("erp", "main_py_declaration")

    def test_falls_back_to_slug_transform_when_undeclared(self, tmp_path):
        products = _make_products_dir(tmp_path)
        # No main.py at all for "orbity" in this tmp tree.
        schema, source = _resolve_schema("orbity", None, products)
        assert (schema, source) == ("orbity", "slug_fallback")

    def test_falls_back_for_hyphenated_slug_when_undeclared(self, tmp_path):
        products = _make_products_dir(tmp_path)
        schema, source = _resolve_schema("erp-imobiliario", None, products)
        # No main.py present → the naive (WRONG) transform, but honestly
        # labelled as a fallback rather than masquerading as verified.
        assert (schema, source) == ("erp_imobiliario", "slug_fallback")


class TestQuoteIdent:
    def test_quotes_simple_identifier(self):
        assert _quote_ident("erp") == '"erp"'

    def test_quotes_hyphenated_identifier(self):
        assert _quote_ident("personal-finance") == '"personal-finance"'

    def test_escapes_embedded_quote(self):
        assert _quote_ident('we"ird') == '"we""ird"'


# ---------------------------------------------------------------------------
# migrate_product end-to-end with schema DERIVED from main.py (not just the
# schema= override the pre-fix tests exercised).
# ---------------------------------------------------------------------------


class TestMigrateProductUsesDerivedSchema:
    def test_writes_ledger_to_declared_schema_not_slug_transform(self, tmp_path):
        """The regression this whole fix exists for: erp-imobiliario's ledger
        must land in "erp", never "erp_imobiliario"."""
        products = _make_products_dir(tmp_path)
        _make_main_py(
            products, "erp-imobiliario",
            'app = create_product_app(name="X", schema="erp", settings=settings, routers=[])\n',
        )
        _make_migration_files(
            products, "erp-imobiliario",
            [("043_api_tokens.sql", "CREATE TABLE erp.api_tokens (id SERIAL);")],
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "erp-imobiliario", confirm=True, executor=fake, products_dir=products,
            git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("erp-imobiliario"),
        )

        assert result["schema"] == "erp"
        assert result["schema_source"] == "main_py_declaration"
        assert any('"erp".schema_migrations' in s for s in fake.executed)
        assert not any('"erp_imobiliario"' in s for s in fake.executed)

    def test_dry_run_reports_schema_source(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [])
        fake = FakeSqlExecutor()

        result = migrate_product("orbity", confirm=False, executor=fake, products_dir=products, git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"))

        assert result["schema"] == "orbity"
        assert result["schema_source"] == "slug_fallback"


# ---------------------------------------------------------------------------
# repair_schema_migrations_ledger — move rows stranded in the phantom schema
# (the naive slug transform) to the real one.
# ---------------------------------------------------------------------------


class TestRepairLedger:
    def _make_main_py_for(self, products, slug, schema):
        _make_main_py(
            products, slug,
            f'app = create_product_app(name="X", schema="{schema}", settings=settings, routers=[])\n',
        )

    def test_no_op_when_phantom_equals_target(self, tmp_path):
        products = _make_products_dir(tmp_path)
        # "orbity" declares schema="orbity" — same as its slug transform.
        self._make_main_py_for(products, "orbity", "orbity")
        fake = FakeSqlExecutor()

        result = repair_schema_migrations_ledger(
            "orbity", confirm=False, executor=fake, products_dir=products
        )

        assert result["status"] == "no_op"
        assert fake.executed == []  # never even queried — nothing phantom to check

    def test_no_op_when_phantom_table_does_not_exist(self, tmp_path):
        products = _make_products_dir(tmp_path)
        self._make_main_py_for(products, "erp-imobiliario", "erp")
        # FakeSqlExecutor with no preset rows → to_regclass probe returns
        # empty rows (falsy) → phantom_exists is False.
        fake = FakeSqlExecutor()

        result = repair_schema_migrations_ledger(
            "erp-imobiliario", confirm=False, executor=fake, products_dir=products
        )

        assert result["status"] == "no_op"
        assert result["phantom_schema"] == "erp_imobiliario"
        assert result["target_schema"] == "erp"

    def test_dry_run_reports_rows_to_move(self, tmp_path):
        products = _make_products_dir(tmp_path)
        self._make_main_py_for(products, "erp-imobiliario", "erp")
        fake = FakeSqlExecutor(
            preset_rows={
                "to_regclass": [{"exists_": True}],
                '"erp_imobiliario".schema_migrations': [
                    {"filename": "001_a.sql"},
                    {"filename": "002_b.sql"},
                ],
            }
        )

        result = repair_schema_migrations_ledger(
            "erp-imobiliario", confirm=False, executor=fake, products_dir=products
        )

        assert result["status"] == "dry_run"
        assert result["rows_to_move"] == ["001_a.sql", "002_b.sql"]
        assert result["moved"] == []
        # Nothing written in dry-run.
        assert not any(s.startswith("INSERT INTO") for s in fake.executed)
        assert not any(s.startswith("DELETE FROM") for s in fake.executed)

    def test_confirm_copies_and_clears_phantom(self, tmp_path):
        products = _make_products_dir(tmp_path)
        self._make_main_py_for(products, "erp-imobiliario", "erp")

        class _SequencedFake(FakeSqlExecutor):
            """FakeSqlExecutor's substring-keyed preset_rows can't distinguish
            the phantom exists-probe from the target exists-probe (both hit
            `to_regclass`), so this subclass answers by CALL ORDER for the
            two `to_regclass` probes migrate_product's repair path issues —
            phantom first, target second — which is exactly the sequence
            `repair_schema_migrations_ledger` executes."""

            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self._regclass_calls = 0

            def execute(self, sql):
                self.executed.append(sql)
                if "to_regclass" in sql:
                    self._regclass_calls += 1
                    # 1st call: phantom exists. 2nd call: target does NOT
                    # exist yet (never migrated correctly before).
                    exists = self._regclass_calls == 1
                    return {"ok": True, "rows": [{"exists_": exists}], "error": None}
                if '"erp_imobiliario".schema_migrations' in sql and "SELECT filename" in sql:
                    return {
                        "ok": True,
                        "rows": [{"filename": "001_a.sql"}, {"filename": "002_b.sql"}],
                        "error": None,
                    }
                return {"ok": True, "rows": [], "error": None}

        fake = _SequencedFake()

        result = repair_schema_migrations_ledger(
            "erp-imobiliario", confirm=True, executor=fake, products_dir=products
        )

        assert result["status"] == "repaired"
        assert result["moved"] == ["001_a.sql", "002_b.sql"]
        assert any(
            'INSERT INTO "erp".schema_migrations' in s
            and 'FROM "erp_imobiliario".schema_migrations' in s
            for s in fake.executed
        ), "copy INSERT..SELECT was not executed"
        assert any(
            'DELETE FROM "erp_imobiliario".schema_migrations' in s
            and "001_a.sql" in s
            and "002_b.sql" in s
            for s in fake.executed
        ), "phantom rows were not cleared"

    def test_not_configured_when_no_token(self, tmp_path, monkeypatch):
        products = _make_products_dir(tmp_path)
        self._make_main_py_for(products, "erp-imobiliario", "erp")
        monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda *a, **k: None,
        )

        result = repair_schema_migrations_ledger("erp-imobiliario", products_dir=products)

        assert result["status"] == "not_configured"
        assert "NOC-REMEDIATE" in result["error"]

    def test_sql_builders_quote_schemas(self):
        sql = _copy_ledger_rows_sql("erp_imobiliario", "erp")
        assert 'INSERT INTO "erp".schema_migrations' in sql
        assert 'FROM "erp_imobiliario".schema_migrations' in sql
        assert "ON CONFLICT (filename) DO NOTHING" in sql

        del_sql = _delete_phantom_ledger_rows_sql("erp_imobiliario", ["001_a.sql", "b'c.sql"])
        assert 'DELETE FROM "erp_imobiliario".schema_migrations' in del_sql
        assert "'001_a.sql'" in del_sql
        assert "b''c.sql" in del_sql  # embedded quote escaped

        exists_sql = _schema_migrations_exists_sql("personal-finance")
        assert "to_regclass" in exists_sql
        assert '"personal-finance".schema_migrations' in exists_sql


# ---------------------------------------------------------------------------
# Stale-tree refusal (the 2026-09-17 incident) —
# KB § PATTERNS/backend/migrate-product-mcp-tool.md "STALE-TREE REFUSAL"
# ---------------------------------------------------------------------------


class TestCheckTreeStaleness:
    """Unit tests for the `_check_tree_staleness` helper in isolation."""

    def test_clean_tree_is_not_stale(self, tmp_path):
        result = _check_tree_staleness(tmp_path, git_runner=_clean_git_runner())
        assert result["stale"] is False
        assert result["check"] is None
        assert result["commits_behind"] == 0
        assert result["dirty_migration_files"] == []

    def test_behind_upstream_is_stale(self, tmp_path):
        runner = FakeGitRunner(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): "main",
                ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
                ("rev-list", "--count", "HEAD..origin/dev"): "26",
            }
        )
        result = _check_tree_staleness(tmp_path, git_runner=runner)
        assert result["stale"] is True
        assert result["check"] == "behind"
        assert result["commits_behind"] == 26
        assert result["upstream"] == "origin/dev"
        assert "26 commit" in result["detail"]

    def test_dirty_migrations_is_stale(self, tmp_path):
        runner = FakeGitRunner(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
                ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
                ("rev-list", "--count", "HEAD..origin/dev"): "0",
                ("status", "--porcelain"): (
                    " M products/erp-imobiliario/backend/migrations/"
                    "134_contrato_assinatura.sql\n"
                ),
            }
        )
        result = _check_tree_staleness(tmp_path, git_runner=runner)
        assert result["stale"] is True
        assert result["check"] == "dirty_migrations"
        assert result["dirty_migration_files"] == [
            "products/erp-imobiliario/backend/migrations/134_contrato_assinatura.sql"
        ]

    def test_untracked_migration_file_counts_as_dirty(self, tmp_path):
        """Untracked (not just modified) files under migrations/ also count —
        an added-but-uncommitted migration is exactly the unreviewed state
        this gate exists to catch."""
        runner = FakeGitRunner(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
                ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
                ("rev-list", "--count", "HEAD..origin/dev"): "0",
                ("status", "--porcelain"): (
                    "?? products/erp-imobiliario/backend/migrations/999_new.sql\n"
                ),
            }
        )
        result = _check_tree_staleness(tmp_path, git_runner=runner)
        assert result["stale"] is True
        assert result["check"] == "dirty_migrations"

    def test_dirty_files_outside_migrations_are_ignored(self, tmp_path):
        runner = FakeGitRunner(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
                ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
                ("rev-list", "--count", "HEAD..origin/dev"): "0",
                ("status", "--porcelain"): (
                    " M products/erp-imobiliario/backend/app/main.py\n?? scratch.txt\n"
                ),
            }
        )
        result = _check_tree_staleness(tmp_path, git_runner=runner)
        assert result["stale"] is False

    def test_not_a_git_repo_refuses(self, tmp_path):
        """Branch detection failing (e.g. `fatal: not a git repository`) is
        a query failure — refuse, never silently assume clean."""
        runner = FakeGitRunner(fail_on={("rev-parse", "--abbrev-ref", "HEAD")})
        result = _check_tree_staleness(tmp_path, git_runner=runner)
        assert result["stale"] is True
        assert result["check"] == "query_failed"

    def test_no_upstream_configured_refuses(self, tmp_path):
        runner = FakeGitRunner(
            responses={("rev-parse", "--abbrev-ref", "HEAD"): "feat/x"},
            fail_on={("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")},
        )
        result = _check_tree_staleness(tmp_path, git_runner=runner)
        assert result["stale"] is True
        assert result["check"] == "query_failed"
        assert result["branch"] == "feat/x"

    def test_rev_list_failure_refuses(self, tmp_path):
        runner = FakeGitRunner(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
                ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
            },
            fail_on={("rev-list", "--count", "HEAD..origin/dev")},
        )
        result = _check_tree_staleness(tmp_path, git_runner=runner)
        assert result["stale"] is True
        assert result["check"] == "query_failed"

    def test_status_query_failure_refuses(self, tmp_path):
        runner = FakeGitRunner(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
                ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
                ("rev-list", "--count", "HEAD..origin/dev"): "0",
            },
            fail_on={("status", "--porcelain")},
        )
        result = _check_tree_staleness(tmp_path, git_runner=runner)
        assert result["stale"] is True
        assert result["check"] == "query_failed"


class TestDirtyMigrationPaths:
    def test_extracts_migration_paths_only(self):
        porcelain = (
            " M products/erp-imobiliario/backend/migrations/134_x.sql\n"
            "?? products/orbity/backend/migrations/002_new.sql\n"
            " M products/erp-imobiliario/backend/app/main.py\n"
        )
        assert _dirty_migration_paths(porcelain) == [
            "products/erp-imobiliario/backend/migrations/134_x.sql",
            "products/orbity/backend/migrations/002_new.sql",
        ]

    def test_handles_rename_shape(self):
        porcelain = (
            "R  products/orbity/backend/migrations/001_old.sql -> "
            "products/orbity/backend/migrations/001_new.sql\n"
        )
        assert _dirty_migration_paths(porcelain) == [
            "products/orbity/backend/migrations/001_new.sql"
        ]

    def test_empty_output_is_clean(self):
        assert _dirty_migration_paths("") == []


class TestMigrateProductStaleTreeGate:
    """Integration: `migrate_product()` refuses / proceeds per the
    stale-tree gate end-to-end."""

    @staticmethod
    def _behind_git_runner(n: int = 26) -> FakeGitRunner:
        return FakeGitRunner(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): "main",
                ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
                ("rev-list", "--count", "HEAD..origin/dev"): str(n),
            }
        )

    @staticmethod
    def _dirty_git_runner() -> FakeGitRunner:
        return FakeGitRunner(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
                ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
                ("rev-list", "--count", "HEAD..origin/dev"): "0",
                ("status", "--porcelain"): (
                    " M products/erp-imobiliario/backend/migrations/"
                    "134_contrato_assinatura.sql\n"
                ),
            }
        )

    @staticmethod
    def _query_failure_git_runner() -> FakeGitRunner:
        return FakeGitRunner(fail_on={("rev-parse", "--abbrev-ref", "HEAD")})

    def _make_fake_worktree(self, root: Path) -> Path:
        """Same shape as `test_scaffold_migration.py`'s helper of the same
        name — a directory `resolve_caller_root` accepts as a real worktree
        (a `.git` entry + the `.noctusai-workspace` marker)."""
        root.mkdir(parents=True, exist_ok=True)
        (root / ".git").write_text("gitdir: /tmp/fake/.git\n", encoding="utf-8")
        (root / ".noctusai-workspace").write_text(
            "workspace_kind=primary\n"
            "workspace_name=fake\n"
            f"noctusai_home={root}\n",
            encoding="utf-8",
        )
        return root

    def test_behind_upstream_tree_refuses(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")]
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity",
            confirm=False,
            executor=fake,
            products_dir=products,
            repo_root=tmp_path,
            git_runner=self._behind_git_runner(26),
            live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "refused_stale_tree"
        assert result["exit_code"] == 1
        assert result["pending"] == []
        assert result["applied"] == []
        assert result["stale_tree"]["stale"] is True
        assert result["stale_tree"]["check"] == "behind"
        assert result["stale_tree"]["commits_behind"] == 26
        # The message names the tree (absolute path), the branch, the
        # commits-behind count, and the exact remedy.
        assert str(tmp_path) in result["error"]
        assert "'main'" in result["error"]
        assert "26" in result["error"]
        assert "git merge --ff-only origin/dev" in result["error"]
        assert "worktree_path" in result["error"]
        # Refuses BEFORE touching Supabase at all.
        assert fake.executed == []

    def test_dirty_migrations_tree_refuses(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")]
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity",
            confirm=False,
            executor=fake,
            products_dir=products,
            repo_root=tmp_path,
            git_runner=self._dirty_git_runner(),
            live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "refused_stale_tree"
        assert result["exit_code"] == 1
        assert result["stale_tree"]["check"] == "dirty_migrations"
        assert "134_contrato_assinatura.sql" in result["error"]
        assert fake.executed == []

    def test_clean_up_to_date_tree_proceeds(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")]
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity",
            confirm=False,
            executor=fake,
            products_dir=products,
            repo_root=tmp_path,
            git_runner=_clean_git_runner(),
            live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "dry_run"
        assert result["exit_code"] == 0
        assert result["pending"] == ["001_seed.sql"]
        assert result["stale_tree"]["stale"] is False
        assert result["error"] is None

    def test_allow_stale_tree_bypasses_and_records_refusal(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")]
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity",
            confirm=False,
            executor=fake,
            products_dir=products,
            repo_root=tmp_path,
            git_runner=self._behind_git_runner(26),
            live_products_fn=_live_catalog_fn("orbity"),
            allow_stale_tree=True,
        )

        assert result["status"] == "dry_run"
        assert result["exit_code"] == 0
        assert result["pending"] == ["001_seed.sql"]
        assert result["allow_stale_tree"] is True
        # The bypass is recorded, never silent: the verdict still rides on
        # the result even though it was not acted on.
        assert result["stale_tree"]["stale"] is True
        assert result["stale_tree"]["check"] == "behind"
        assert result["stale_tree"]["commits_behind"] == 26

    def test_failed_git_query_refuses_never_assumes_clean(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")]
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity",
            confirm=False,
            executor=fake,
            products_dir=products,
            repo_root=tmp_path,
            git_runner=self._query_failure_git_runner(),
            live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "refused_stale_tree"
        assert result["exit_code"] == 1
        assert result["stale_tree"]["check"] == "query_failed"
        assert fake.executed == []

    def test_worktree_path_pins_the_inspected_and_read_tree(self, tmp_path):
        """worktree_path= pins BOTH which tree the staleness check inspects
        AND where migrations are read from — mirrors predeploy_check's
        parameter of the same name and semantics exactly."""
        wt = self._make_fake_worktree(tmp_path / "wt")
        _make_migration_files(
            wt / "products",
            "orbity",
            [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")],
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity",
            confirm=False,
            executor=fake,
            worktree_path=str(wt),
            git_runner=_clean_git_runner(),
            live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "dry_run"
        assert result["pending"] == ["001_seed.sql"]

    def test_worktree_path_stale_tree_refuses(self, tmp_path):
        """The pinned worktree, not the primary, is what gets judged."""
        wt = self._make_fake_worktree(tmp_path / "wt")
        _make_migration_files(
            wt / "products",
            "orbity",
            [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")],
        )
        fake = FakeSqlExecutor()

        result = migrate_product(
            "orbity",
            confirm=False,
            executor=fake,
            worktree_path=str(wt),
            git_runner=self._behind_git_runner(3),
            live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "refused_stale_tree"
        assert str(wt.resolve()) in result["error"]


# ---------------------------------------------------------------------------
# Catalog-scope refusal gate (2026-09-17 incident — same day as the
# stale-tree gate above, same shape, different question: "should this
# product be touched at all?" rather than "is the tree trustworthy?").
# ---------------------------------------------------------------------------


class TestMigrateProductCatalogScopeGate:
    """Integration: `migrate_product()` refuses / proceeds per the
    catalog-scope gate end-to-end. Zero real Supabase / catalog I/O —
    `live_products_fn` is injected exactly like `git_runner` is above."""

    def _fixture(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "erp-imobiliario",
            [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS erp;")],
        )
        return products, FakeSqlExecutor()

    def test_inactive_product_refuses(self, tmp_path):
        """ativo=false — the exact erp-imobiliario incident shape: the
        product simply isn't in the catalog's live set at all."""
        products, fake = self._fixture(tmp_path)

        result = migrate_product(
            "erp-imobiliario", confirm=False, executor=fake, products_dir=products,
            git_runner=_clean_git_runner(),
            live_products_fn=_live_catalog_fn("orbity", "core"),
        )

        assert result["status"] == "refused_catalog_scope"
        assert result["exit_code"] == 1
        assert result["pending"] == []
        assert result["applied"] == []
        assert result["catalog_scope"]["in_scope"] is False
        assert "erp-imobiliario" in result["error"]
        assert "2026-09-17" in result["error"]
        assert "allow_inactive" in result["error"]
        # Refuses BEFORE touching Supabase at all — no credential, no SQL.
        assert fake.executed == []

    def test_deploy_scope_dev_refuses(self, tmp_path):
        """ativo=true but deploy_scope='dev' — CLAUDE.md §1's other
        non-live combination ('ativo+dev ⇒ dev only'). The live-catalog
        query (`ativo=true AND deploy_scope='live'`) already excludes this
        row server-side, so from the guard's perspective it is the same
        'not in the live set' — this test pins that the dev-scope case is
        covered too, not just the fully-inactive one."""
        products, fake = self._fixture(tmp_path)

        result = migrate_product(
            "erp-imobiliario", confirm=True, executor=fake, products_dir=products,
            git_runner=_clean_git_runner(),
            live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "refused_catalog_scope"
        assert result["exit_code"] == 1
        assert fake.executed == []

    def test_ativo_live_product_proceeds(self, tmp_path):
        """The normal case: the product IS in the catalog's live set —
        migrate_product proceeds exactly as before, and the (now-passing)
        catalog_scope verdict still rides on the result."""
        products, fake = self._fixture(tmp_path)

        result = migrate_product(
            "erp-imobiliario", confirm=False, executor=fake, products_dir=products,
            git_runner=_clean_git_runner(),
            live_products_fn=_live_catalog_fn("erp-imobiliario", "orbity"),
        )

        assert result["status"] == "dry_run"
        assert result["exit_code"] == 0
        assert result["pending"] == ["001_seed.sql"]
        assert result["catalog_scope"]["in_scope"] is True

    def test_allow_inactive_bypasses_and_records_finding(self, tmp_path):
        """The documented escape hatch: proceeds despite the product being
        out of catalog scope, but the bypass is never silent — the
        unfavorable catalog_scope verdict still rides on the result."""
        products, fake = self._fixture(tmp_path)

        result = migrate_product(
            "erp-imobiliario", confirm=False, executor=fake, products_dir=products,
            git_runner=_clean_git_runner(),
            live_products_fn=_live_catalog_fn("orbity"),
            allow_inactive=True,
        )

        assert result["status"] == "dry_run"
        assert result["exit_code"] == 0
        assert result["pending"] == ["001_seed.sql"]
        assert result["allow_inactive"] is True
        assert result["catalog_scope"]["in_scope"] is False

    def test_catalog_lookup_failure_refuses_never_assumes_live(self, tmp_path, monkeypatch):
        """Fail-closed: when neither the live catalog NOR the checked-in
        build-scope.txt fallback can answer the question, migrate_product
        refuses — 'cannot tell' is never 'allowed'."""
        products, fake = self._fixture(tmp_path)
        monkeypatch.setattr(BS, "SCOPE_PATH", tmp_path / "nope.txt")

        def _boom():
            raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set")

        result = migrate_product(
            "erp-imobiliario", confirm=False, executor=fake, products_dir=products,
            git_runner=_clean_git_runner(),
            live_products_fn=_boom,
        )

        assert result["status"] == "refused_catalog_scope"
        assert result["exit_code"] == 1
        assert result["catalog_scope"]["catalog_source"] == "unavailable"
        assert result["catalog_scope"]["in_scope"] is False
        assert fake.executed == []

    def test_catalog_scope_refusal_precedes_stale_tree_check(self, tmp_path):
        """The catalog-scope gate is checked first — a product that is
        BOTH out-of-scope AND behind an upstream tree is refused for being
        out-of-scope, the higher-level question."""
        products, fake = self._fixture(tmp_path)
        behind = FakeGitRunner(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): "main",
                ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
                ("rev-list", "--count", "HEAD..origin/dev"): "26",
            }
        )

        result = migrate_product(
            "erp-imobiliario", confirm=False, executor=fake, products_dir=products,
            repo_root=tmp_path, git_runner=behind,
            live_products_fn=_live_catalog_fn("orbity"),
        )

        assert result["status"] == "refused_catalog_scope"
        # The staleness verdict still computed (it rides on every result),
        # even though it was never the reason for the refusal.
        assert result["stale_tree"]["stale"] is True


# ---------------------------------------------------------------------------
# Registration smoke-test
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_tool_registers_on_server(self):
        """noctus.dev.migrate_product appears in the server's tool registry."""
        from mcp.server.fastmcp import FastMCP  # type: ignore[import]
        from tools.noctus.dev.migrate_product import register

        server = FastMCP(name="test-migrate-product")
        register(server)

        assert "noctus.dev.migrate_product" in server._tool_manager._tools

    def test_repair_tool_registers_on_server(self):
        from mcp.server.fastmcp import FastMCP  # type: ignore[import]
        from tools.noctus.dev.migrate_product import register

        server = FastMCP(name="test-migrate-product-repair")
        register(server)

        assert "noctus.dev.repair_migration_ledger" in server._tool_manager._tools
