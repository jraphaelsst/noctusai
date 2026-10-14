"""Tests for `noctus.dev.render_organ_migration` (hermetic: tmp products dir, injected catalog)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
REPO_ROOT = Path(__file__).resolve().parents[3]
for sub in ("seed/lib/backend", "seed/framework/backend"):
    sys.path.insert(0, str(REPO_ROOT / sub))

from noctusai_seed.organs import organ_migration_sql  # noqa: E402
from tools.noctus.dev import _catalog_scope_guard  # noqa: E402
from tools.noctus.dev.render_organ_migration import render_organ_migration as render  # noqa: E402


def _product(tmp_path, slug="demo"):
    products = tmp_path / "products"
    mig = products / slug / "backend" / "migrations"
    mig.mkdir(parents=True)
    (mig / "001_seed.sql").write_text("-- seed\n")
    return products, mig


def _live(*slugs):
    return lambda: list(slugs)


def _call(products, **kw):
    kw.setdefault("live_products_fn", _live("demo"))
    return render("demo", "finance", products_dir=products, schema="erp", skip_fetch=True, **kw)


def test_dry_run_plans_without_writing(tmp_path):
    products, mig = _product(tmp_path)
    r = _call(products)
    assert r["status"] == "planned" and r["number"] == 2
    assert [p.name for p in mig.glob("*.sql")] == ["001_seed.sql"]


def test_confirm_writes_generator_output_then_is_idempotent(tmp_path):
    products, mig = _product(tmp_path)
    r = _call(products, confirm=True)
    assert r["status"] == "created"
    f = mig / "002_finance.sql"
    assert f.read_text() == organ_migration_sql("finance", "erp")
    assert _call(products, confirm=True)["status"] == "up_to_date"
    assert len(list(mig.glob("*finance*.sql"))) == 1


def test_drifted_file_is_refreshed_in_place_only_on_confirm(tmp_path):
    products, mig = _product(tmp_path)
    _call(products, confirm=True)
    f = mig / "002_finance.sql"
    f.write_text(f.read_text() + "-- edit\n")
    assert _call(products)["status"] == "would_refresh"
    assert f.read_text().endswith("-- edit\n")
    assert _call(products, confirm=True)["status"] == "refreshed"
    assert f.read_text() == organ_migration_sql("finance", "erp")


def test_asleep_product_is_refused(tmp_path):
    products, mig = _product(tmp_path)
    r = _call(products, confirm=True, live_products_fn=_live("other"))
    assert r["status"] == _catalog_scope_guard.REFUSED_STATUS
    assert [p.name for p in mig.glob("*.sql")] == ["001_seed.sql"]


def test_unknown_organ_errors(tmp_path):
    products, _ = _product(tmp_path)
    r = render("demo", "nope", products_dir=products, live_products_fn=_live("demo"), skip_fetch=True)
    assert r["status"] == "error" and "unknown organ" in r["error"]


def test_hostile_slug_is_refused_before_any_filesystem_access(tmp_path):
    products, _ = _product(tmp_path)
    for bad in ("../demo", "demo/../../x", "Demo", "-x", "a b"):
        r = render(bad, "finance", products_dir=products, schema="erp", skip_fetch=True, live_products_fn=_live(bad))
        assert r["status"] == "error" and "Invalid product slug" in r["error"], bad


def test_invalid_schema_identifier_is_refused(tmp_path):
    products, _ = _product(tmp_path)
    for bad in ("erp; DROP SCHEMA x", "Erp", "1erp", 'e"rp', ""):
        r = render("demo", "finance", products_dir=products, schema=bad, skip_fetch=True, live_products_fn=_live("demo"))
        assert r["status"] == "error", bad


def test_slug_fallback_schema_is_refused(tmp_path):
    products, mig = _product(tmp_path)  # no app/main.py declaration -> slug_fallback
    r = render("demo", "finance", products_dir=products, skip_fetch=True, live_products_fn=_live("demo"), confirm=True)
    assert r["status"] == "error" and "schema=" in r["error"]
    assert [p.name for p in mig.glob("*.sql")] == ["001_seed.sql"]
