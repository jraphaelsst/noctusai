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
    _copy_ledger_rows_sql,
    _delete_phantom_ledger_rows_sql,
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
        assert any('"custom_schema".schema_migrations' in s for s in fake.executed)

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
            "erp-imobiliario", confirm=True, executor=fake, products_dir=products
        )

        assert result["schema"] == "erp"
        assert result["schema_source"] == "main_py_declaration"
        assert any('"erp".schema_migrations' in s for s in fake.executed)
        assert not any('"erp_imobiliario"' in s for s in fake.executed)

    def test_dry_run_reports_schema_source(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [])
        fake = FakeSqlExecutor()

        result = migrate_product("orbity", confirm=False, executor=fake, products_dir=products)

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
