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


# --- frozen-after-apply (security review B2) -------------------------------------------------------
import json  # noqa: E402

import pytest  # noqa: E402

from noctusai_lib.testing.migrations_applied import record_applied, sha256_text  # noqa: E402
from noctusai_lib.testing.organs import assert_organ_migration_current, expected_organ_migration  # noqa: E402


def _applied(mig, *names):
    record_applied(mig.parent, {n: sha256_text((mig / n).read_text()) for n in names})


def _drift_generator(mig_file):
    """Simulate the generator moving on: the committed file no longer equals its output."""
    mig_file.write_text(mig_file.read_text() + "-- older generator\n")


def test_applied_latest_with_moved_generator_ships_new_revision_and_freezes_the_old(tmp_path):
    products, mig = _product(tmp_path)
    _call(products, confirm=True)
    f = mig / "002_finance.sql"
    _drift_generator(f)
    _applied(mig, "002_finance.sql")
    frozen = f.read_text()
    assert _call(products)["status"] == "would_new_revision"
    r = _call(products, confirm=True)
    assert r["status"] == "new_revision" and r["revision"] == 2
    assert f.read_text() == frozen  # applied file untouched
    new = mig / "003_finance_rev2.sql"
    assert new.read_text() == expected_organ_migration("finance", "erp", 2)
    assert new.read_text().endswith("-- organ-revision: 2\n")
    assert _call(products, confirm=True)["status"] == "up_to_date"  # latest matches generator
    assert assert_organ_migration_current(mig.parent.parent, "finance", schema="erp") == new


def test_applied_and_current_is_up_to_date_not_a_new_revision(tmp_path):
    products, mig = _product(tmp_path)
    _call(products, confirm=True)
    _applied(mig, "002_finance.sql")
    assert _call(products, confirm=True)["status"] == "up_to_date"
    assert len(list(mig.glob("*finance*.sql"))) == 1


def test_unapplied_stale_latest_is_refreshed_in_place_even_with_a_record_present(tmp_path):
    products, mig = _product(tmp_path)
    record_applied(mig.parent, {"001_seed.sql": sha256_text("-- seed\n")})
    _call(products, confirm=True)
    _drift_generator(mig / "002_finance.sql")
    assert _call(products, confirm=True)["status"] == "refreshed"
    assert len(list(mig.glob("*finance*.sql"))) == 1


def test_pin_checks_only_the_latest_against_the_generator_and_older_against_the_record(tmp_path):
    products, mig = _product(tmp_path)
    _call(products, confirm=True)
    old = mig / "002_finance.sql"
    _drift_generator(old)
    _applied(mig, "002_finance.sql")
    _call(products, confirm=True)
    pdir = mig.parent.parent
    assert_organ_migration_current(pdir, "finance", schema="erp")  # old differs from generator: fine
    old.write_text(old.read_text() + "-- tamper\n")  # frozen file edited
    with pytest.raises(AssertionError, match="frozen"):
        assert_organ_migration_current(pdir, "finance", schema="erp")


def test_pin_rejects_stacked_unapplied_revisions_and_a_stale_latest(tmp_path):
    products, mig = _product(tmp_path)
    _call(products, confirm=True)
    pdir = mig.parent.parent
    (mig / "003_finance_rev2.sql").write_text(expected_organ_migration("finance", "erp", 2))
    with pytest.raises(AssertionError, match="not recorded as applied"):
        assert_organ_migration_current(pdir, "finance", schema="erp")
    _applied(mig, "002_finance.sql")
    assert_organ_migration_current(pdir, "finance", schema="erp")
    (mig / "003_finance_rev2.sql").write_text(expected_organ_migration("finance", "erp", 2) + "-- stale\n")
    with pytest.raises(AssertionError, match="drifted"):
        assert_organ_migration_current(pdir, "finance", schema="erp")


def test_pin_fails_when_no_file_exists(tmp_path):
    _products, mig = _product(tmp_path)
    with pytest.raises(AssertionError, match="no rendered"):
        assert_organ_migration_current(mig.parent.parent, "finance", schema="erp")


def test_applied_record_roundtrip_and_malformed(tmp_path):
    from noctusai_lib.testing.migrations_applied import load_applied

    b = tmp_path / "backend"
    (b / "migrations").mkdir(parents=True)
    assert load_applied(b) == {}
    record_applied(b, {"b.sql": "2"})
    record_applied(b / "migrations", {"a.sql": "1"})
    assert load_applied(b) == {"a.sql": "1", "b.sql": "2"}
    (b / "migrations-applied.json").write_text(json.dumps({"applied": []}))
    with pytest.raises(ValueError):
        load_applied(b)
