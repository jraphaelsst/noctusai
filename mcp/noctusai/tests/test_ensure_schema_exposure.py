"""Tests for ``noctus.dev.ensure_schema_exposure``.

All tests are fully hermetic — they use ``migrate_product.FakeSqlExecutor``
and an injected ``products=[...]`` roster (bypassing the live catalog round-
trip), so zero real Supabase calls are made. Per the dispatch brief: "Do not
touch the VPS or the database" — every test here stays in-process.

Test seam design mirrors ``test_migrate_product.py``:
  - ``executor=FakeSqlExecutor(...)`` injection avoids network.
  - ``products_dir=tmp_path/"products"`` injection avoids PRODUCTS_DIR.
  - ``products=[...]`` injection avoids the catalog roster round-trip.
  - No monkey-patching of our own code (per KB § PATTERNS/compliance/testing.md);
    the one carve-out (neutralizing the DB-first credential tier, an external
    seed-library seam) mirrors ``test_migrate_product.py``'s own carve-out.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

from tools.noctus.dev.ensure_schema_exposure import (  # noqa: E402
    _alter_role_sql,
    _exposed_schemas_sql,
    _parse_exposed_schemas,
    check_schema_exposure,
)
from tools.noctus.dev.migrate_product import FakeSqlExecutor  # noqa: E402


def _make_products_dir(tmp_path: Path) -> Path:
    p = tmp_path / "products"
    p.mkdir()
    return p


def _make_main_py(products_dir: Path, product_slug: str, schema: str) -> None:
    app_dir = products_dir / product_slug / "backend" / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "main.py").write_text(
        f'app = create_product_app(name="X", schema="{schema}")\n',
        encoding="utf-8",
    )


_EXPOSED_ROWS_KEY = "pg_db_role_setting"  # FakeSqlExecutor preset-key fragment


def _fake_with_exposed(schemas: list[str]) -> FakeSqlExecutor:
    csv = ",".join(schemas)
    return FakeSqlExecutor(
        preset_rows={
            _EXPOSED_ROWS_KEY: [{"setconfig": [f"pgrst.db_schemas={csv}"]}],
        }
    )


class TestParseExposedSchemas:
    def test_parses_csv_setting(self):
        rows = [{"setconfig": ["some.other=1", "pgrst.db_schemas=core,erp,orbity"]}]
        assert _parse_exposed_schemas(rows) == ["core", "erp", "orbity"]

    def test_missing_setting_returns_none(self):
        rows = [{"setconfig": ["some.other=1"]}]
        assert _parse_exposed_schemas(rows) is None

    def test_no_rows_returns_none(self):
        assert _parse_exposed_schemas([]) is None
        assert _parse_exposed_schemas(None) is None

    def test_strips_whitespace_entries(self):
        rows = [{"setconfig": ["pgrst.db_schemas= core , erp ,orbity "]}]
        assert _parse_exposed_schemas(rows) == ["core", "erp", "orbity"]


class TestAlterRoleSql:
    def test_builds_csv(self):
        sql = _alter_role_sql(["core", "erp", "orbity"])
        assert "ALTER ROLE authenticator SET pgrst.db_schemas='core,erp,orbity';" == sql

    def test_escapes_single_quotes(self):
        sql = _alter_role_sql(["weird'schema"])
        assert "weird''schema" in sql


class TestExposedSchemasSql:
    def test_targets_authenticator_role(self):
        sql = _exposed_schemas_sql()
        assert "pg_db_role_setting" in sql
        assert "authenticator" in sql


class TestCheckAction:
    def test_in_sync_when_all_schemas_exposed(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "orbity", "orbity")
        _make_main_py(products, "erp-imobiliario", "erp")
        fake = _fake_with_exposed(["orbity", "erp", "core"])

        result = check_schema_exposure(
            action="check",
            products=["orbity", "erp-imobiliario"],
            executor=fake,
            products_dir=products,
        )

        assert result["status"] == "in_sync"
        assert result["missing"] == []
        assert result["ok"] is True

    def test_drift_detected_when_schema_unexposed(self, tmp_path):
        # The 2026-09-16 shape: a new product's schema was never added.
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "agents", "agents")
        fake = _fake_with_exposed(["core", "erp", "orbity"])

        result = check_schema_exposure(
            action="check",
            products=["agents"],
            executor=fake,
            products_dir=products,
        )

        assert result["status"] == "drift_detected"
        assert result["missing"] == ["agents"]
        assert result["checked"][0]["schema"] == "agents"

    def test_never_mutates_on_check(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "agents", "agents")
        fake = _fake_with_exposed(["core"])

        check_schema_exposure(
            action="check", products=["agents"], executor=fake, products_dir=products
        )

        assert not any("ALTER ROLE" in sql for sql in fake.executed)
        assert not any("NOTIFY" in sql for sql in fake.executed)

    def test_no_exposed_setting_at_all_treats_as_empty(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "orbity", "orbity")
        fake = FakeSqlExecutor(preset_rows={_EXPOSED_ROWS_KEY: [{"setconfig": []}]})

        result = check_schema_exposure(
            action="check", products=["orbity"], executor=fake, products_dir=products
        )

        assert result["exposed_schemas"] == []
        assert result["missing"] == ["orbity"]


class TestApplyAction:
    def test_dry_run_by_default_plans_but_does_not_write(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "agents", "agents")
        fake = _fake_with_exposed(["core"])

        result = check_schema_exposure(
            action="apply", products=["agents"], executor=fake, products_dir=products
        )

        assert result["status"] == "planned"
        assert result["new_exposed_schemas"] == ["agents", "core"]
        assert not any("ALTER ROLE" in sql for sql in fake.executed)

    def test_confirm_true_appends_and_never_removes(self, tmp_path):
        # APPEND-ONLY: an existing exposed schema outside the checked roster
        # (e.g. 'legacy_schema', not derived from any product here) must
        # survive the union untouched — this tool never removes.
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "agents", "agents")
        fake = _fake_with_exposed(["core", "legacy_schema"])

        result = check_schema_exposure(
            action="apply",
            confirm=True,
            products=["agents"],
            executor=fake,
            products_dir=products,
        )

        assert result["status"] == "applied"
        assert result["applied"] is True
        assert result["new_exposed_schemas"] == ["agents", "core", "legacy_schema"]
        alter_calls = [sql for sql in fake.executed if "ALTER ROLE" in sql]
        assert len(alter_calls) == 1
        assert "agents" in alter_calls[0] and "core" in alter_calls[0] and "legacy_schema" in alter_calls[0]
        assert any("NOTIFY" in sql for sql in fake.executed)

    def test_up_to_date_when_nothing_missing(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "orbity", "orbity")
        fake = _fake_with_exposed(["orbity"])

        result = check_schema_exposure(
            action="apply",
            confirm=True,
            products=["orbity"],
            executor=fake,
            products_dir=products,
        )

        assert result["status"] == "up_to_date"
        assert not any("ALTER ROLE" in sql for sql in fake.executed)

    def test_alter_role_failure_surfaces_error(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "agents", "agents")
        fake = FakeSqlExecutor(
            preset_rows={_EXPOSED_ROWS_KEY: [{"setconfig": ["pgrst.db_schemas=core"]}]},
            fail_on={"ALTER ROLE"},
        )

        result = check_schema_exposure(
            action="apply",
            confirm=True,
            products=["agents"],
            executor=fake,
            products_dir=products,
        )

        assert result["status"] == "error"
        assert "ALTER ROLE failed" in result["error"]


class TestNotConfigured:
    def test_not_configured_when_no_token(self, tmp_path, monkeypatch):
        """When SUPABASE_ACCESS_TOKEN is absent and no executor injected,
        returns not_configured — NEVER a silent skip (predeploy_check's
        schema_exposure leg depends on this distinction to fail loud)."""
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "orbity", "orbity")
        monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
        # Neutralize the DB-first tier so this stays hermetic (no real DB
        # read) — same external-seam carve-out test_migrate_product.py uses.
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda *a, **k: None,
        )

        result = check_schema_exposure(products=["orbity"], products_dir=products)

        assert result["status"] == "not_configured"
        assert result["ok"] is False
        assert "SUPABASE_ACCESS_TOKEN" in result["error"]
        assert "NOC-REMEDIATE" in result["error"]


class TestInvalidAction:
    def test_unknown_action_errors(self, tmp_path):
        fake = _fake_with_exposed(["core"])
        result = check_schema_exposure(action="bogus", executor=fake, products=["core"])
        assert result["status"] == "error"
        assert result["ok"] is False


class TestRosterResolution:
    def test_live_products_fn_injection_drives_the_roster(self, tmp_path):
        """`products=` omitted -> resolves via the injected `live_products_fn`
        seam (the same one `deploy_verify._resolve_live_products` exposes) —
        never a second, independently-drifting roster definition."""
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "orbity", "orbity")
        # _resolve_live_products unions with build_scope.ALWAYS_BUILD ("core"),
        # so "core" is checked too — its schema falls back to the naive slug
        # transform ("core") since it has no main.py in this fixture.
        fake = _fake_with_exposed(["orbity", "core"])

        result = check_schema_exposure(
            executor=fake,
            products=None,
            live_products_fn=lambda: ["orbity"],
            products_dir=products,
        )

        assert result["status"] == "in_sync"
        assert result["roster_source"] == "live_catalog"
        assert [c["product"] for c in result["checked"]] == ["core", "orbity"]

    def test_explicit_products_bypasses_catalog_roster(self, tmp_path):
        """The per-product predeploy_check leg passes products=[product] —
        this must never fall through to the catalog round-trip."""
        products = _make_products_dir(tmp_path)
        _make_main_py(products, "agents", "agents")
        fake = _fake_with_exposed(["agents"])

        def _boom():
            raise AssertionError("catalog roster must not be consulted when products= is set")

        result = check_schema_exposure(
            executor=fake,
            products=["agents"],
            live_products_fn=_boom,
            products_dir=products,
        )

        assert result["status"] == "in_sync"
        assert result["roster_source"] == "explicit"


# ---------------------------------------------------------------------------
# action='prune' — removal of asleep products' schemas (AT-847e83bb)
# ---------------------------------------------------------------------------


class _StatefulFake(FakeSqlExecutor):
    """FakeSqlExecutor whose ALTER ROLE really changes what the next read
    returns (a test double, so the post-apply verify re-read is exercised)."""

    def execute(self, sql: str):
        if sql.startswith("ALTER ROLE authenticator SET pgrst.db_schemas='"):
            csv = sql.split("='", 1)[1].rsplit("';", 1)[0]
            self.preset_rows[_EXPOSED_ROWS_KEY] = [{"setconfig": [f"pgrst.db_schemas={csv}"]}]
        return super().execute(sql)


def _prune_fixture(tmp_path):
    products = _make_products_dir(tmp_path)
    _make_main_py(products, "agents", "agents")
    _make_main_py(products, "erp-imobiliario", "erp")  # asleep
    _make_main_py(products, "orbity", "orbity")  # asleep
    (products / "core").mkdir()  # schema 'core' is protected infra
    return products


def _exposed_fake(cls, exposed):
    return cls(preset_rows={_EXPOSED_ROWS_KEY: [{"setconfig": [f"pgrst.db_schemas={','.join(exposed)}"]}]})


def _prune(tmp_path, exposed, *, confirm=False, active=None, fake=None):
    products = _prune_fixture(tmp_path)
    fake = fake or _exposed_fake(_StatefulFake, exposed)
    result = check_schema_exposure(
        action="prune",
        confirm=confirm,
        executor=fake,
        products_dir=products,
        live_products_fn=lambda: ["agents"],
        active_products=active if active is not None else {"agents", "core"},
    )
    return result, fake


def _writes(fake):
    return [s for s in fake.executed if s.startswith(("ALTER", "NOTIFY"))]


class TestPruneAction:
    def test_dry_run_plans_only_asleep_schemas_and_writes_nothing(self, tmp_path):
        result, fake = _prune(tmp_path, ["public", "graphql_public", "core", "agents", "erp", "orbity"])
        assert result["status"] == "planned"
        assert result["to_drop"] == [
            {"schema": "erp", "products": ["erp-imobiliario"]},
            {"schema": "orbity", "products": ["orbity"]},
        ]
        assert result["new_exposed_schemas"] == ["public", "graphql_public", "core", "agents"]
        assert result["sql"] == [
            "ALTER ROLE authenticator SET pgrst.db_schemas='public,graphql_public,core,agents';",
            "NOTIFY pgrst,'reload config';",
        ]
        assert _writes(fake) == []

    def test_excludes_active_and_protected_schemas(self, tmp_path):
        # orbity woken up -> kept; public/core/seed protected even though seed has no declaration.
        result, _ = _prune(
            tmp_path, ["public", "core", "seed", "agents", "erp", "orbity"], active={"agents", "orbity"}
        )
        assert {d["schema"] for d in result["to_drop"]} == {"erp"}
        assert {"public", "core", "seed", "agents", "orbity"} <= set(result["new_exposed_schemas"])

    def test_unattributable_schema_is_refused_not_dropped(self, tmp_path):
        result, _ = _prune(tmp_path, ["public", "agents", "erp", "mystery"])
        assert [r["schema"] for r in result["refused"]] == ["mystery"]
        assert "mystery" in result["new_exposed_schemas"]
        assert "erp" not in result["new_exposed_schemas"]

    def test_slug_fallback_attribution_is_refused(self, tmp_path):
        products = _prune_fixture(tmp_path)
        (products / "daily-life").mkdir()  # no main.py -> slug-guess schema
        result = check_schema_exposure(
            action="prune",
            executor=_exposed_fake(_StatefulFake, ["agents", "daily_life"]),
            products_dir=products,
            live_products_fn=lambda: ["agents"],
            active_products={"agents"},
        )
        assert result["status"] == "up_to_date"
        assert [r["schema"] for r in result["refused"]] == ["daily_life"]

    def test_shared_schema_with_one_active_owner_is_kept(self, tmp_path):
        products = _prune_fixture(tmp_path)
        _make_main_py(products, "twin", "erp")  # active product also declares erp
        result = check_schema_exposure(
            action="prune",
            executor=_exposed_fake(_StatefulFake, ["agents", "erp"]),
            products_dir=products,
            live_products_fn=lambda: ["agents"],
            active_products={"agents", "twin"},
        )
        assert result["status"] == "up_to_date"
        assert "erp" in result["kept"]

    def test_confirm_applies_notifies_and_verifies(self, tmp_path):
        result, fake = _prune(tmp_path, ["public", "agents", "erp"], confirm=True)
        assert result["status"] == "pruned" and result["applied"] is True
        assert _writes(fake) == [
            "ALTER ROLE authenticator SET pgrst.db_schemas='public,agents';",
            "NOTIFY pgrst,'reload config';",
        ]

    def test_verify_failure_is_loud(self, tmp_path):
        # Plain FakeSqlExecutor: ALTER "succeeds" but the re-read is unchanged.
        fake = _exposed_fake(FakeSqlExecutor, ["public", "agents", "erp"])
        result, _ = _prune(tmp_path, [], confirm=True, fake=fake)
        assert result["status"] == "error" and "verify FAILED" in result["error"]

    def test_idempotent_when_nothing_to_prune(self, tmp_path):
        result, fake = _prune(tmp_path, ["public", "core", "agents"], confirm=True)
        assert result["status"] == "up_to_date"
        assert _writes(fake) == []

    def test_missing_active_scope_refuses(self, tmp_path):
        from tools.noctus.dev import ensure_schema_exposure as mod

        assert mod._read_active_scope(tmp_path / "absent.txt") is None
