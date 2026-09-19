"""Tests for ``noctus.dev.schema_drift``.

All tests are fully hermetic — they use ``migrate_product.FakeSqlExecutor``
and a tmp-path products directory (mirrors ``test_migrate_product.py`` /
``test_ensure_schema_exposure.py``). No real Supabase calls, no monkey-
patching of our own code (per ``KB § PATTERNS/compliance/testing.md``).

Fixtures below use the THREE real bugs the slice brief names
(``erp.assinaturas.external_id`` / ``erp.tool_call_audits`` /
``erp.llm_preferences``) as the "best possible test cases" — each is
recreated in miniature: a migration declares a table/column, the live
schema (via the Fake executor) simulates the pre-repair state where it was
absent.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

from tools.noctus.dev.migrate_product import FakeSqlExecutor  # noqa: E402
from tools.noctus.dev.schema_drift import (  # noqa: E402
    _compare,
    _compare_orm_vs_migrations,
    _downgrade_dynamic_ddl_false_positives,
    _dynamic_blind_spot_detail,
    _live_columns_sql,
    _migration_declared_schema,
    _orm_declared_schema,
    _rows_to_live_schema,
    check_schema_drift,
)


def _make_main_py(products_dir: Path, slug: str, schema: str) -> None:
    app_dir = products_dir / slug / "backend" / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "main.py").write_text(
        f'app = create_product_app(name="X", schema="{schema}")\n',
        encoding="utf-8",
    )


def _make_migrations(products_dir: Path, slug: str, files: list[tuple[str, str]]) -> Path:
    mig_dir = products_dir / slug / "backend" / "migrations"
    mig_dir.mkdir(parents=True, exist_ok=True)
    for name, sql in files:
        (mig_dir / name).write_text(sql, encoding="utf-8")
    return mig_dir


def _make_model(products_dir: Path, slug: str, filename: str, body: str) -> Path:
    models_dir = products_dir / slug / "backend" / "app" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "__init__.py").write_text(
        'from sqlalchemy.orm import declarative_base\nBase = declarative_base()\nSCHEMA = "erp"\n',
        encoding="utf-8",
    )
    (models_dir / filename).write_text(body, encoding="utf-8")
    return models_dir


_LIVE_COLS_KEY = "information_schema.columns"


def _live_executor(rows: list[dict]) -> FakeSqlExecutor:
    return FakeSqlExecutor(preset_rows={_LIVE_COLS_KEY: rows})


# ---------------------------------------------------------------------------
# _migration_declared_schema
# ---------------------------------------------------------------------------


class TestMigrationDeclaredSchema:
    def test_no_migrations_dir_returns_empty_and_not_found(self, tmp_path):
        products_dir = tmp_path / "products"
        products_dir.mkdir()
        declared, found, blind = _migration_declared_schema("ghost", products_dir)
        assert declared == {}
        assert found is False
        assert blind == []

    def test_parses_create_table(self, tmp_path):
        products_dir = tmp_path / "products"
        _make_migrations(products_dir, "erp-imobiliario", [
            ("017_llm_preferences.sql", (
                "SET search_path = erp, public;\n"
                "CREATE TABLE IF NOT EXISTS erp.llm_preferences (\n"
                "    org_id UUID PRIMARY KEY,\n"
                "    provider TEXT NOT NULL\n"
                ");\n"
            )),
        ])
        declared, found, blind = _migration_declared_schema("erp-imobiliario", products_dir)
        assert found is True
        assert declared["erp.llm_preferences"] == {"org_id", "provider"}
        assert blind == []

    def test_parses_add_column_bug_1_shape(self, tmp_path):
        """erp.assinaturas.external_id — an ALTER TABLE ADD COLUMN on top
        of an earlier CREATE TABLE, exactly the 047 migration's shape."""
        products_dir = tmp_path / "products"
        _make_migrations(products_dir, "erp-imobiliario", [
            ("001_assinaturas.sql", (
                "CREATE TABLE erp.assinaturas (id UUID PRIMARY KEY, status TEXT);\n"
            )),
            ("047_assinaturas_external_id.sql", (
                "SET search_path = erp, public;\n"
                "ALTER TABLE erp.assinaturas\n"
                "    ADD COLUMN IF NOT EXISTS external_id text;\n"
            )),
        ])
        declared, found, blind = _migration_declared_schema("erp-imobiliario", products_dir)
        assert found is True
        assert declared["erp.assinaturas"] == {"id", "status", "external_id"}
        assert blind == []


# ---------------------------------------------------------------------------
# _orm_declared_schema
# ---------------------------------------------------------------------------


class TestOrmDeclaredSchema:
    def test_no_models_dir_returns_empty(self, tmp_path):
        products_dir = tmp_path / "products"
        products_dir.mkdir()
        declared, blind = _orm_declared_schema("ghost", "erp", products_dir)
        assert declared == {}
        assert blind == []

    def test_extracts_tablename_and_columns(self, tmp_path):
        products_dir = tmp_path / "products"
        _make_model(products_dir, "erp-imobiliario", "tool_call_audit.py", (
            "from sqlalchemy import BigInteger, Column, String\n"
            "from app.models import Base, SCHEMA\n\n"
            "class ToolCallAudit(Base):\n"
            "    __tablename__ = \"tool_call_audits\"\n"
            "    __table_args__ = {\"schema\": SCHEMA}\n\n"
            "    id = Column(BigInteger, primary_key=True)\n"
            "    tool_name = Column(String(80), nullable=False)\n"
        ))
        declared, blind = _orm_declared_schema("erp-imobiliario", "erp", products_dir)
        assert declared["erp.tool_call_audits"] == {"id", "tool_name"}
        # __table_args__ used an imported name (SCHEMA), not a literal — falls
        # back to the default schema AND records why.
        assert len(blind) == 1
        assert "not a string literal" in blind[0]

    def test_literal_schema_in_table_args_resolves_without_blind_spot(self, tmp_path):
        products_dir = tmp_path / "products"
        _make_model(products_dir, "core", "tool_call_audit.py", (
            "from sqlalchemy import Column, Integer\n"
            "from app.models import Base\n\n"
            "class ToolCallAudit(Base):\n"
            "    __tablename__ = \"tool_call_audits\"\n"
            "    __table_args__ = {\"schema\": \"public\"}\n\n"
            "    id = Column(Integer, primary_key=True)\n"
        ))
        declared, blind = _orm_declared_schema("core", "public", products_dir)
        assert declared["public.tool_call_audits"] == {"id"}
        assert blind == []

    def test_unparseable_model_file_is_a_blind_spot_not_a_crash(self, tmp_path):
        products_dir = tmp_path / "products"
        models_dir = products_dir / "erp-imobiliario" / "backend" / "app" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "broken.py").write_text("class Broken(:\n", encoding="utf-8")
        declared, blind = _orm_declared_schema("erp-imobiliario", "erp", products_dir)
        assert declared == {}
        assert len(blind) == 1
        assert "could not parse" in blind[0]


# ---------------------------------------------------------------------------
# _rows_to_live_schema / _live_columns_sql
# ---------------------------------------------------------------------------


class TestLiveSchemaHelpers:
    def test_rows_grouped_by_table(self):
        rows = [
            {"table_name": "llm_preferences", "column_name": "org_id"},
            {"table_name": "llm_preferences", "column_name": "provider"},
            {"table_name": "assinaturas", "column_name": "id"},
        ]
        live = _rows_to_live_schema("erp", rows)
        assert live == {
            "erp.llm_preferences": {"org_id", "provider"},
            "erp.assinaturas": {"id"},
        }

    def test_empty_rows_returns_empty_map(self):
        assert _rows_to_live_schema("erp", []) == {}
        assert _rows_to_live_schema("erp", None) == {}

    def test_sql_scopes_to_schema_and_escapes_quotes(self):
        sql = _live_columns_sql("weird'schema")
        assert "table_schema = 'weird''schema'" in sql
        assert "information_schema.columns" in sql


# ---------------------------------------------------------------------------
# _compare / _compare_orm_vs_migrations
# ---------------------------------------------------------------------------


class TestCompare:
    def test_missing_table_reported(self):
        declared = {"erp.llm_preferences": {"org_id"}}
        findings = _compare(declared, {}, source="migrations")
        assert len(findings) == 1
        assert findings[0]["kind"] == "missing_table"
        assert findings[0]["table"] == "erp.llm_preferences"

    def test_missing_column_reported(self):
        declared = {"erp.assinaturas": {"id", "external_id"}}
        live = {"erp.assinaturas": {"id"}}
        findings = _compare(declared, live, source="migrations")
        assert len(findings) == 1
        assert findings[0]["kind"] == "missing_column"
        assert findings[0]["column"] == "external_id"

    def test_fully_matching_schema_has_no_findings(self):
        declared = {"erp.assinaturas": {"id", "external_id"}}
        live = {"erp.assinaturas": {"id", "external_id", "status"}}  # live may have extra
        assert _compare(declared, live, source="migrations") == []

    def test_orm_declares_table_migrations_dont(self):
        orm = {"erp.tool_call_audits": {"id"}}
        findings = _compare_orm_vs_migrations(orm, {})
        assert len(findings) == 1
        assert findings[0]["kind"] == "orm_migration_drift"

    def test_orm_and_migrations_agree_has_no_findings(self):
        orm = {"erp.tool_call_audits": {"id"}}
        migrations = {"erp.tool_call_audits": {"id", "tool_name"}}
        assert _compare_orm_vs_migrations(orm, migrations) == []


# ---------------------------------------------------------------------------
# _dynamic_blind_spot_detail
# ---------------------------------------------------------------------------


class TestDynamicBlindSpotDetail:
    def test_rename_column_names_old_and_new(self):
        detail = _dynamic_blind_spot_detail({
            "class": "rename_column", "old_column": "client_id", "new_column": "marca_id",
            "file": "046_clients_to_marcas.sql",
        })
        assert "046_clients_to_marcas.sql" in detail
        assert "client_id" in detail and "marca_id" in detail
        assert "%I" in detail

    def test_unknown_class_still_produces_a_string(self):
        detail = _dynamic_blind_spot_detail({"class": "something_new", "file": "x.sql"})
        assert "x.sql" in detail
        assert "verify manually" in detail


# ---------------------------------------------------------------------------
# _downgrade_dynamic_ddl_false_positives — the social-wiring 046 shape
# ---------------------------------------------------------------------------


class TestDowngradeDynamicDdlFalsePositives:
    def test_rename_column_downgrades_when_live_has_the_new_name(self):
        """The real bug: migrations declare client_id (never saw the
        dynamic rename), live has marca_id instead — corroborated, so the
        missing_column finding is downgraded, not dropped silently and not
        kept as a blocking finding."""
        findings = [{
            "kind": "missing_column", "table": "social_wiring.integration_accounts",
            "column": "client_id", "source": "migrations", "severity": "high",
            "detail": "x",
        }]
        live = {"social_wiring.integration_accounts": {"id", "marca_id"}}
        dynamic = [{
            "class": "rename_column", "old_column": "client_id", "new_column": "marca_id",
            "column": None, "file": "046_clients_to_marcas.sql",
        }]
        kept, downgraded = _downgrade_dynamic_ddl_false_positives(findings, live, dynamic)
        assert kept == []
        assert len(downgraded) == 1
        assert "client_id" in downgraded[0] and "marca_id" in downgraded[0]
        assert "verify manually" in downgraded[0]

    def test_rename_column_NOT_downgraded_without_live_corroboration(self):
        """Same dynamic blind spot exists, but THIS table's live schema has
        neither client_id nor marca_id — no evidence this table went
        through the dynamic rename at all, so a genuinely unrelated
        missing_column finding on the same column name must still block."""
        findings = [{
            "kind": "missing_column", "table": "social_wiring.unrelated_table",
            "column": "client_id", "source": "migrations", "severity": "high",
            "detail": "x",
        }]
        live = {"social_wiring.unrelated_table": {"id"}}  # no marca_id either
        dynamic = [{
            "class": "rename_column", "old_column": "client_id", "new_column": "marca_id",
            "column": None, "file": "046_clients_to_marcas.sql",
        }]
        kept, downgraded = _downgrade_dynamic_ddl_false_positives(findings, live, dynamic)
        assert kept == findings
        assert downgraded == []

    def test_drop_column_downgrades_on_name_match_alone(self):
        findings = [{
            "kind": "missing_column", "table": "erp.legacy",
            "column": "old_flag", "source": "migrations", "severity": "high",
            "detail": "x",
        }]
        live = {"erp.legacy": {"id"}}
        dynamic = [{
            "class": "drop_column", "old_column": None, "new_column": None,
            "column": "old_flag", "file": "099_dynamic_drop.sql",
        }]
        kept, downgraded = _downgrade_dynamic_ddl_false_positives(findings, live, dynamic)
        assert kept == []
        assert len(downgraded) == 1
        assert "old_flag" in downgraded[0]

    def test_missing_table_findings_pass_through_untouched(self):
        findings = [{
            "kind": "missing_table", "table": "erp.ghost", "column": None,
            "source": "migrations", "severity": "high", "detail": "x",
        }]
        kept, downgraded = _downgrade_dynamic_ddl_false_positives(findings, {}, [])
        assert kept == findings
        assert downgraded == []

    def test_negative_control_unrelated_missing_column_still_a_finding(self):
        """No dynamic blind spots at all — a real missing_column must never
        be swallowed."""
        findings = [{
            "kind": "missing_column", "table": "erp.assinaturas",
            "column": "external_id", "source": "migrations", "severity": "high",
            "detail": "x",
        }]
        kept, downgraded = _downgrade_dynamic_ddl_false_positives(findings, {}, [])
        assert kept == findings
        assert downgraded == []


# ---------------------------------------------------------------------------
# check_schema_drift — end-to-end, using the three real bugs as fixtures
# ---------------------------------------------------------------------------


class TestCheckSchemaDrift:
    def test_bug_2_missing_table_tool_call_audits(self, tmp_path):
        """Migration declares erp.tool_call_audits; live schema (Fake
        executor with zero rows) has nothing — the pre-repair state where
        migration 030 was authored but never applied."""
        products_dir = tmp_path / "products"
        _make_main_py(products_dir, "erp-imobiliario", "erp")
        _make_migrations(products_dir, "erp-imobiliario", [
            ("030_tool_call_audits.sql", (
                "SET search_path = erp, public;\n"
                "CREATE TABLE IF NOT EXISTS erp.tool_call_audits (\n"
                "    id BIGSERIAL PRIMARY KEY,\n"
                "    tool_name VARCHAR(80) NOT NULL\n"
                ");\n"
            )),
        ])
        result = check_schema_drift(
            "erp-imobiliario", executor=_live_executor([]), products_dir=products_dir,
        )
        assert result["status"] == "drift_detected"
        kinds = {f["kind"] for f in result["findings"]}
        assert "missing_table" in kinds
        table_findings = [f for f in result["findings"] if f["table"] == "erp.tool_call_audits"]
        assert len(table_findings) == 1
        assert table_findings[0]["kind"] == "missing_table"

    def test_bug_1_missing_column_external_id(self, tmp_path):
        """Migration declares erp.assinaturas.external_id; live schema has
        the table but not that column — the pre-047 state."""
        products_dir = tmp_path / "products"
        _make_main_py(products_dir, "erp-imobiliario", "erp")
        _make_migrations(products_dir, "erp-imobiliario", [
            ("001_assinaturas.sql", "CREATE TABLE erp.assinaturas (id UUID PRIMARY KEY);\n"),
            ("047_assinaturas_external_id.sql", (
                "SET search_path = erp, public;\n"
                "ALTER TABLE erp.assinaturas ADD COLUMN IF NOT EXISTS external_id text;\n"
            )),
        ])
        live_rows = [{"table_name": "assinaturas", "column_name": "id"}]  # no external_id
        result = check_schema_drift(
            "erp-imobiliario", executor=_live_executor(live_rows), products_dir=products_dir,
        )
        assert result["status"] == "drift_detected"
        col_findings = [f for f in result["findings"] if f["kind"] == "missing_column"]
        assert len(col_findings) == 1
        assert col_findings[0]["table"] == "erp.assinaturas"
        assert col_findings[0]["column"] == "external_id"

    def test_fully_matching_schema_is_in_sync(self, tmp_path):
        products_dir = tmp_path / "products"
        _make_main_py(products_dir, "erp-imobiliario", "erp")
        _make_migrations(products_dir, "erp-imobiliario", [
            ("017_llm_preferences.sql", (
                "CREATE TABLE erp.llm_preferences (org_id UUID PRIMARY KEY, provider TEXT);\n"
            )),
        ])
        live_rows = [
            {"table_name": "llm_preferences", "column_name": "org_id"},
            {"table_name": "llm_preferences", "column_name": "provider"},
        ]
        result = check_schema_drift(
            "erp-imobiliario", executor=_live_executor(live_rows), products_dir=products_dir,
        )
        assert result["status"] == "in_sync"
        assert result["findings"] == []
        assert result["ok"] is True
        assert result["checked_tables"] == 1

    def test_no_migrations_and_no_orm_is_undeterminable_not_a_pass(self, tmp_path):
        """Fail-closed: nothing to compare against must be a finding, never
        a silent in_sync."""
        products_dir = tmp_path / "products"
        _make_main_py(products_dir, "ghost-product", "ghost")
        result = check_schema_drift(
            "ghost-product", executor=_live_executor([]), products_dir=products_dir,
        )
        assert result["status"] == "undeterminable"
        assert result["ok"] is False
        assert len(result["findings"]) == 1
        assert result["findings"][0]["kind"] == "undeterminable"
        assert result["error"] is not None

    def test_no_executor_and_no_credentials_is_not_configured(self, tmp_path, monkeypatch):
        """Mirrors schema_exposure's not_configured contract — never a
        silent skip. Neutralizes the DB-first credential resolution the
        same way test_migrate_product.py's own carve-out does (an external
        seed-library credential seam, not our own guard)."""
        products_dir = tmp_path / "products"
        _make_main_py(products_dir, "erp-imobiliario", "erp")
        _make_migrations(products_dir, "erp-imobiliario", [
            ("001.sql", "CREATE TABLE erp.x (id UUID PRIMARY KEY);\n"),
        ])
        monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
        # Neutralize the DB-first tier so this stays hermetic (no real DB
        # read) — the same carve-out test_migrate_product.py uses (an
        # external seed-library credential seam, not our own guard).
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda *a, **k: None,
        )
        result = check_schema_drift("erp-imobiliario", products_dir=products_dir)
        assert result["status"] == "not_configured"
        assert result["ok"] is False
        assert "NOC-REMEDIATE" in result["error"]

    def test_live_executor_error_is_status_error(self, tmp_path):
        products_dir = tmp_path / "products"
        _make_main_py(products_dir, "erp-imobiliario", "erp")
        _make_migrations(products_dir, "erp-imobiliario", [
            ("001.sql", "CREATE TABLE erp.x (id UUID PRIMARY KEY);\n"),
        ])
        failing = FakeSqlExecutor(fail_on={_LIVE_COLS_KEY})
        result = check_schema_drift(
            "erp-imobiliario", executor=failing, products_dir=products_dir,
        )
        assert result["status"] == "error"
        assert result["ok"] is False

    def test_orm_migration_drift_reported_even_without_live_db_access(self, tmp_path):
        """The offline ORM-vs-migrations leg runs before the live-DB leg,
        so it still surfaces when the executor later reports not_configured
        — findings from an offline leg are never dropped just because a
        later leg couldn't run."""
        products_dir = tmp_path / "products"
        _make_main_py(products_dir, "core", "public")
        _make_model(products_dir, "core", "tool_call_audit.py", (
            "from sqlalchemy import Column, Integer, String\n"
            "from app.models import Base\n\n"
            "class ToolCallAudit(Base):\n"
            "    __tablename__ = \"tool_call_audits\"\n"
            "    __table_args__ = {\"schema\": \"public\"}\n\n"
            "    id = Column(Integer, primary_key=True)\n"
            "    extra_field = Column(String(10))\n"
        ))
        _make_migrations(products_dir, "core", [
            ("001.sql", "CREATE TABLE public.tool_call_audits (id INTEGER PRIMARY KEY);\n"),
        ])
        result = check_schema_drift(
            "core", executor=_live_executor([{"table_name": "tool_call_audits", "column_name": "id"}]),
            products_dir=products_dir,
        )
        drift = [f for f in result["findings"] if f["kind"] == "orm_migration_drift"]
        assert len(drift) == 1
        assert drift[0]["column"] == "extra_field"

    def test_dynamic_rename_column_is_in_sync_not_drift_detected(self, tmp_path):
        """End-to-end recreation of social-wiring's 046_clients_to_marcas.sql
        shape: a migration set that declares `client_id` (never sees the
        dynamic per-table rename), a live schema that actually has
        `marca_id` (the rename DID apply, just not visible to this
        parser). Before this slice: 1 confident missing_column finding,
        status='drift_detected', blocking every deploy. After: 0 findings,
        1 corroborated blind spot, status='in_sync'."""
        products_dir = tmp_path / "products"
        _make_main_py(products_dir, "social-wiring", "social_wiring")
        _make_migrations(products_dir, "social-wiring", [
            ("001_social-wiring.sql", (
                "CREATE TABLE social_wiring.integration_accounts ("
                "id UUID PRIMARY KEY, client_id UUID);\n"
            )),
            ("046_clients_to_marcas.sql", (
                "DO $$\n"
                "DECLARE t TEXT;\n"
                "BEGIN\n"
                "  FOREACH t IN ARRAY ARRAY['integration_accounts']\n"
                "  LOOP\n"
                "    EXECUTE format("
                "'ALTER TABLE social_wiring.%I RENAME COLUMN client_id TO marca_id', t"
                ");\n"
                "  END LOOP;\n"
                "END\n"
                "$$;\n"
            )),
        ])
        live_rows = [
            {"table_name": "integration_accounts", "column_name": "id"},
            {"table_name": "integration_accounts", "column_name": "marca_id"},
        ]
        result = check_schema_drift(
            "social-wiring", executor=_live_executor(live_rows), products_dir=products_dir,
        )
        assert result["status"] == "in_sync"
        assert result["ok"] is True
        assert result["findings"] == []
        assert any("client_id" in b and "marca_id" in b for b in result["blind_spots"])

    def test_dynamic_ddl_elsewhere_does_not_mask_an_unrelated_real_bug(self, tmp_path):
        """Negative control: the SAME product carries the dynamic-rename
        blind spot AND a genuinely missing, unrelated column on a
        different table — that second one must still block. Downgrading
        must never become a product-wide amnesty."""
        products_dir = tmp_path / "products"
        _make_main_py(products_dir, "social-wiring", "social_wiring")
        _make_migrations(products_dir, "social-wiring", [
            ("001_social-wiring.sql", (
                "CREATE TABLE social_wiring.integration_accounts ("
                "id UUID PRIMARY KEY, client_id UUID);\n"
                "CREATE TABLE social_wiring.contacts (id UUID PRIMARY KEY);\n"
            )),
            ("046_clients_to_marcas.sql", (
                "DO $$\n"
                "DECLARE t TEXT;\n"
                "BEGIN\n"
                "  FOREACH t IN ARRAY ARRAY['integration_accounts']\n"
                "  LOOP\n"
                "    EXECUTE format("
                "'ALTER TABLE social_wiring.%I RENAME COLUMN client_id TO marca_id', t"
                ");\n"
                "  END LOOP;\n"
                "END\n"
                "$$;\n"
            )),
            ("047_bug.sql", (
                "ALTER TABLE social_wiring.contacts "
                "ADD COLUMN IF NOT EXISTS whatsapp_id TEXT;\n"
            )),
        ])
        live_rows = [
            {"table_name": "integration_accounts", "column_name": "id"},
            {"table_name": "integration_accounts", "column_name": "marca_id"},
            {"table_name": "contacts", "column_name": "id"},  # whatsapp_id never applied live
        ]
        result = check_schema_drift(
            "social-wiring", executor=_live_executor(live_rows), products_dir=products_dir,
        )
        assert result["status"] == "drift_detected"
        real = [f for f in result["findings"] if f["kind"] == "missing_column"]
        assert len(real) == 1
        assert real[0]["table"] == "social_wiring.contacts"
        assert real[0]["column"] == "whatsapp_id"


class TestRegistration:
    def test_register_wires_the_tool(self):
        from tools.noctus.dev import schema_drift as sd

        calls: list[dict] = []

        class FakeServer:
            def tool(self, **kwargs):
                def _decorator(fn):
                    calls.append(kwargs)
                    return fn
                return _decorator

        sd.register(FakeServer())
        assert calls
        assert calls[0]["name"] == "noctus.dev.schema_drift"
