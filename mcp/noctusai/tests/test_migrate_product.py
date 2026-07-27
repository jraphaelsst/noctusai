"""Tests for ``noctus.dev.migrate_product``.

All tests are fully hermetic — they use ``FakeSqlExecutor`` and a tmp-path
products directory, so zero real Supabase calls are made.

Test seam design:
  - ``executor=FakeSqlExecutor(...)`` injection avoids network.
  - ``products_dir=tmp_path/"products"`` injection avoids PRODUCTS_DIR.
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

from tools.noctus.dev.migrate_product import (  # noqa: E402
    FakeSqlExecutor,
    SupabaseMgmtExecutor,
    _checksum,
    _ensure_tracking_table_sql,
    _fetch_applied_sql,
    _record_migration_sql,
    _slug_to_schema,
    _sorted_migrations,
    make_sql_executor,
    migrate_product,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_products_dir(tmp_path: Path) -> Path:
    p = tmp_path / "products"
    p.mkdir()
    return p


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
        assert "CREATE TABLE IF NOT EXISTS orbity.schema_migrations" in sql
        assert "filename" in sql
        assert "checksum" in sql

    def test_ensure_tracking_table_creates_schema(self):
        sql = _ensure_tracking_table_sql("erp_imobiliario")
        assert "CREATE SCHEMA IF NOT EXISTS erp_imobiliario" in sql

    def test_fetch_applied_selects_filename(self):
        sql = _fetch_applied_sql("orbity")
        assert "SELECT filename" in sql
        assert "orbity.schema_migrations" in sql

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

        result = migrate_product("orbity", confirm=False, executor=fake, products_dir=products)

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
        migrate_product("orbity", confirm=False, executor=fake, products_dir=products)
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
        result = migrate_product("orbity", confirm=False, executor=fake, products_dir=products)

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

        result = migrate_product("orbity", confirm=True, executor=fake, products_dir=products)

        assert result["status"] == "applied"
        assert result["applied"] == ["001_seed.sql", "002_crm.sql"]
        assert result["pending"] == []
        assert result["error"] is None

    def test_applied_files_are_executed(self, tmp_path):
        products = _make_products_dir(tmp_path)
        sql_001 = "CREATE SCHEMA IF NOT EXISTS orbity;"
        _make_migration_files(products, "orbity", [("001_seed.sql", sql_001)])
        fake = FakeSqlExecutor()

        migrate_product("orbity", confirm=True, executor=fake, products_dir=products)

        # executed should contain: ensure_table + fetch_applied + migration_sql + record_sql
        assert any(sql_001 in s for s in fake.executed), "migration body was not executed"
        assert any("INSERT INTO orbity.schema_migrations" in s for s in fake.executed), (
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

        result = migrate_product("orbity", confirm=True, executor=fake, products_dir=products)

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

        result = migrate_product("orbity", confirm=True, executor=fake, products_dir=products)

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
        )

        assert result["status"] == "error"
        assert "999_does_not_exist.sql" in result["error"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_migrations_dir_returns_up_to_date(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [])
        fake = FakeSqlExecutor()

        result = migrate_product("orbity", confirm=True, executor=fake, products_dir=products)

        assert result["status"] == "up_to_date"
        assert result["applied"] == []
        assert result["pending"] == []

    def test_missing_product_dir_returns_error(self, tmp_path):
        products = _make_products_dir(tmp_path)
        fake = FakeSqlExecutor()

        result = migrate_product("nonexistent", confirm=False, executor=fake, products_dir=products)

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

        result = migrate_product("orbity", confirm=False, executor=fake, products_dir=products)

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

        result = migrate_product("orbity", products_dir=products)  # no executor

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
        )

        assert result["schema"] == "custom_schema"
        # Verify tracking table was created in the custom schema
        assert any("custom_schema.schema_migrations" in s for s in fake.executed)

    def test_ensure_table_failure_returns_error(self, tmp_path):
        """If tracking table creation fails, return error immediately."""
        products = _make_products_dir(tmp_path)
        _make_migration_files(
            products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")]
        )
        fake = FakeSqlExecutor(fail_on={"CREATE TABLE IF NOT EXISTS"})

        result = migrate_product("orbity", confirm=True, executor=fake, products_dir=products)

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
