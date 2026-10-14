"""`mount_finance` / `mount_organs` / pin helper / `create_product_app(organs=...)` seam."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.domain.finance import (
    ATTACHMENT_UPLOAD_PATH_PATTERN,
    STATEMENT_UPLOAD_PATH_PATTERN,
)
from noctusai_lib.testing.organs import assert_organ_migration_current
from noctusai_seed.organs import ORGAN_REGISTRY, mount_finance, mount_organs, organ_migration_sql


async def _auth(authorization: str | None = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="no auth")
    return (SimpleNamespace(id="u1"), "tok", "org-1")


def _mount():
    return mount_finance(
        schema="erp", auth_dependency=_auth,
        get_admin_client=lambda: object(), get_core_client=lambda: object(),
    )


def test_mount_finance_yields_both_routers_with_expected_paths():
    organ = _mount()
    assert len(list(organ)) == 2
    paths = {r.path for router in organ for r in router.routes}
    assert "/api/finance/statements" in paths
    assert any(p.startswith("/api/finance/entries") for p in paths)
    assert organ.max_body_path_overrides.keys() == {ATTACHMENT_UPLOAD_PATH_PATTERN, STATEMENT_UPLOAD_PATH_PATTERN}


def test_reconciliation_can_be_skipped():
    organ = mount_finance(
        schema="erp", auth_dependency=_auth, get_admin_client=lambda: object(),
        get_core_client=lambda: object(), reconciliation=False,
    )
    assert len(organ.routers) == 1


def test_routes_are_strictly_401_without_auth():
    app = FastAPI()
    routers, _ = mount_organs([_mount()])
    for r in routers:
        app.include_router(r)
    client = TestClient(app)
    for method, path in (("get", "/api/finance/entries"), ("post", "/api/finance/statements")):
        assert getattr(client, method)(path).status_code == 401, path


def test_schema_mismatch_with_cfg_is_refused():
    from noctusai_lib.domain.finance import FinanceConfig

    with pytest.raises(ValueError):
        mount_finance(schema="erp", cfg=FinanceConfig(schema="other"), auth_dependency=_auth,
                      get_admin_client=lambda: object(), get_core_client=lambda: object())


def test_mount_organs_merges_overrides():
    routers, overrides = mount_organs([_mount()])
    assert len(routers) == 2 and STATEMENT_UPLOAD_PATH_PATTERN in overrides


def test_pin_helper_passes_then_detects_drift(tmp_path):
    spec = ORGAN_REGISTRY["finance"]
    mig = tmp_path / "backend" / "migrations"
    mig.mkdir(parents=True)
    f = mig / "007_finance.sql"
    f.write_text(organ_migration_sql("finance", "erp"), encoding="utf-8")
    assert assert_organ_migration_current(tmp_path, "finance", schema="erp") == f
    f.write_text(f.read_text() + "\n-- hand edit\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="drifted"):
        assert_organ_migration_current(tmp_path, "finance", schema="erp")
    f.unlink()
    with pytest.raises(AssertionError, match="exactly one"):
        assert_organ_migration_current(tmp_path, "finance", schema="erp")
    assert spec.migration_header in organ_migration_sql("finance", "erp")


def test_create_product_app_organs_seam_mounts_routers_and_covers_upload_routes(fake_settings):
    """Without the seam the finance upload routes would refuse to boot (no override); with it they boot."""
    from noctusai_seed import create_product_app

    app = create_product_app(
        name="Test", schema="test", settings=fake_settings,
        standard_routers=["health"], organs=[_mount()],
    )
    paths = {r.path for r in app.routes}
    assert "/api/finance/statements" in paths
    assert any(p.startswith("/api/finance/entries") for p in paths)
    with TestClient(app) as client:
        assert client.get("/api/finance/entries").status_code == 401


# -- items + the commerce money/fiscal/jobs registry entries + the finance tax-regime seam ------------------


def test_every_registered_organ_header_prefixes_its_generated_migration():
    assert {"finance", "items", "commerce_money", "commerce_fiscal", "jobs"} <= set(ORGAN_REGISTRY)
    for name, spec in ORGAN_REGISTRY.items():
        assert organ_migration_sql(name, "erp").startswith(spec.migration_header), name


def test_registered_migration_headers_are_unique_prefixes():
    headers = [s.migration_header for s in ORGAN_REGISTRY.values()]
    for h in headers:
        assert sum(o.startswith(h) for o in headers) == 1, h  # a pin helper finds a file by header


def test_mount_items_routes_overrides_and_strict_401():
    from noctusai_lib.domain.items import ITEMS_IMPORT_MAX_BYTES, ITEMS_IMPORT_PATH_PATTERN
    from noctusai_seed.organs import mount_items

    organ = mount_items(
        schema="erp", auth_dependency=_auth, get_admin_client=lambda: object(), get_core_client=lambda: object(),
    )
    assert organ.max_body_path_overrides == {ITEMS_IMPORT_PATH_PATTERN: ITEMS_IMPORT_MAX_BYTES}
    app = FastAPI()
    routers, _ = mount_organs([organ])
    for r in routers:
        app.include_router(r)
    assert any(r.path == ITEMS_IMPORT_PATH_PATTERN for r in app.routes)
    client = TestClient(app)
    assert client.get("/api/items").status_code == 401
    assert client.post("/api/items", json={}).status_code == 401


def test_mount_finance_passes_default_tax_regime_to_the_router():
    organ = mount_finance(
        schema="erp", auth_dependency=_auth, get_admin_client=lambda: object(), get_core_client=lambda: object(),
        default_tax_regime=lambda ctx: "mei",
    )
    assert len(organ.routers) == 2
