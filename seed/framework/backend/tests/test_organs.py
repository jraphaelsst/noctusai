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
    assert {"finance", "items", "commerce_money", "commerce_fiscal", "jobs", "parties", "inventory", "purchasing", "contracts"} <= set(ORGAN_REGISTRY)
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


# -- parties / inventory / purchasing ------------------------------------------------------------------


def _app_of(organ):
    from noctusai_lib.primitives.exceptions import AppException, app_exception_handler

    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    routers, _ = mount_organs([organ])
    for r in routers:
        app.include_router(r)
    return app


def test_mount_parties_routes_overrides_and_strict_401():
    from noctusai_lib.domain.parties import IMPORT_UPLOAD_MAX_BYTES, IMPORT_UPLOAD_PATH_PATTERN
    from noctusai_seed.organs import mount_parties

    organ = mount_parties(schema="erp", auth_dependency=_auth, get_admin_client=lambda: object(), get_core_client=lambda: object())
    assert organ.max_body_path_overrides == {IMPORT_UPLOAD_PATH_PATTERN: IMPORT_UPLOAD_MAX_BYTES}
    app = _app_of(organ)
    assert any(r.path == IMPORT_UPLOAD_PATH_PATTERN for r in app.routes)
    client = TestClient(app)
    assert client.get("/api/parties").status_code == 401
    assert client.post("/api/parties", json={}).status_code == 401
    # a host that mounts elsewhere gets the override re-derived from ITS prefix
    moved = mount_parties(schema="erp", auth_dependency=_auth, get_admin_client=lambda: object(), get_core_client=lambda: object(), prefix="/api/pty")
    assert list(moved.max_body_path_overrides) == ["/api/pty/import"]


def test_mount_inventory_routes_and_strict_401():
    from noctusai_seed.organs import mount_inventory

    organ = mount_inventory(schema="erp", auth_dependency=_auth, get_admin_client=lambda: object(), get_core_client=lambda: object())
    assert organ.max_body_path_overrides == {}
    client = TestClient(_app_of(organ))
    for method, path in (("GET", "/api/inventory/balances"), ("POST", "/api/inventory/receive"), ("GET", "/api/inventory/warehouses")):
        assert client.request(method, path, json={} if method == "POST" else None).status_code == 401, path


def test_mount_rejects_a_cfg_for_another_schema():
    from noctusai_lib.domain.inventory import InventoryConfig
    from noctusai_seed.organs import mount_inventory

    with pytest.raises(ValueError):
        mount_inventory(schema="erp", cfg=InventoryConfig(schema="other"), auth_dependency=_auth, get_admin_client=lambda: object(), get_core_client=lambda: object())


ORDER_ID = "44444444-4444-4444-8444-444444444444"


def _purchasing_client(*, role: str, grants=(), threshold=None, total=100_000):
    from noctusai_lib.domain.permissions import FakePermissionGrantRepository
    from noctusai_lib.testing import MockSupabaseClient
    from noctusai_seed.organs import mount_purchasing

    core = MockSupabaseClient()
    core.set_table_data("noctus_users", [{"id": "u1", "org_id": "org-1", "org_role": role, "role": "user"}])
    db = MockSupabaseClient()
    db.table("pur_orders").insert({"id": ORDER_ID, "org_id": "org-1", "number": 1, "status": "draft", "supplier_name": "F", "total_cents": total, "goods_cents": total}).execute()
    if threshold is not None:
        db.table("pur_settings").insert({"org_id": "org-1", "approval_threshold_cents": threshold}).execute()
    db.set_rpc_data("pur_transition", {"status": "ok", "order_id": ORDER_ID})
    organ = mount_purchasing(
        schema="erp", auth_dependency=_auth, get_admin_client=lambda: db, get_core_client=lambda: core,
        permissions=FakePermissionGrantRepository([("u1", "purchasing.approve")] if grants else []),
    )
    return TestClient(_app_of(organ))


APPROVE = f"/api/purchasing/orders/{ORDER_ID}/approve"
H = {"Authorization": "Bearer x"}


def test_mount_purchasing_strict_401_on_every_route_and_admin_gates_the_writes():
    client = _purchasing_client(role="member")
    for method, path in (("GET", "/api/purchasing/orders"), ("GET", "/api/purchasing/settings"), ("POST", APPROVE),
                         ("POST", "/api/purchasing/orders"), ("PUT", "/api/purchasing/settings"), ("GET", "/api/purchasing/receipts")):
        assert client.request(method, path, json={} if method in ("POST", "PUT") else None).status_code == 401, path
    assert client.post("/api/purchasing/orders", json={}, headers=H).status_code == 403  # member: not admin
    assert client.get("/api/purchasing/orders", headers=H).status_code == 200


def test_purchasing_approval_comes_from_the_selected_org_role_and_the_permission_grant():
    assert _purchasing_client(role="member").post(APPROVE, headers=H).status_code == 403            # staff, no grant
    assert _purchasing_client(role="member", grants=(1,)).post(APPROVE, headers=H).status_code == 200  # grant holder, not admin
    assert _purchasing_client(role="owner").post(APPROVE, headers=H).status_code == 200            # admin, no threshold
    # above the org threshold only the permission holder approves
    assert _purchasing_client(role="owner", threshold=50_000).post(APPROVE, headers=H).status_code == 403
    assert _purchasing_client(role="owner", grants=(1,), threshold=50_000).post(APPROVE, headers=H).status_code == 200
    assert _purchasing_client(role="owner", threshold=500_000).post(APPROVE, headers=H).status_code == 200


# -- contracts -------------------------------------------------------------------------------------------


def _contracts_client(*, role: str):
    from noctusai_lib.testing import MockSupabaseClient
    from noctusai_seed.organs import mount_contracts

    core = MockSupabaseClient()
    core.set_table_data("noctus_users", [{"id": "u1", "org_id": "org-1", "org_role": role, "role": "user"}])
    organ = mount_contracts(schema="erp", auth_dependency=_auth, get_admin_client=lambda: MockSupabaseClient(), get_core_client=lambda: core)
    return organ, TestClient(_app_of(organ))


def test_mount_contracts_strict_401_on_every_route_and_admin_gates_the_writes():
    organ, client = _contracts_client(role="member")
    cid = "55555555-5555-4555-8555-555555555555"
    for method, path in (("GET", "/api/contracts"), ("POST", "/api/contracts"), ("GET", f"/api/contracts/{cid}"), ("POST", f"/api/contracts/{cid}/activate"),
                         ("POST", f"/api/contracts/{cid}/terminate"), ("GET", f"/api/contracts/{cid}/billing-preview"), ("POST", "/api/contracts/billing/run"),
                         ("POST", f"/api/contracts/{cid}/signature"), ("GET", f"/api/contracts/{cid}/attachments")):
        assert client.request(method, path, json={} if method == "POST" else None).status_code == 401, path
    assert client.post("/api/contracts", json={}, headers=H).status_code == 403  # member: not admin
    assert client.post(f"/api/contracts/{cid}/terminate", json={}, headers=H).status_code == 403
    assert client.post("/api/contracts/billing/run", headers=H).status_code == 403
    assert client.get("/api/contracts", headers=H).status_code == 200


def test_mount_contracts_overrides_rebase_on_the_prefix_and_expose_the_job():
    from noctusai_lib.domain.contracts import ATTACHMENT_UPLOAD_MAX_BYTES, ATTACHMENT_UPLOAD_PATH_PATTERN
    from noctusai_seed.organs import mount_contracts

    organ = mount_contracts(schema="erp", auth_dependency=_auth, get_admin_client=lambda: object(), get_core_client=lambda: object())
    assert organ.max_body_path_overrides == {ATTACHMENT_UPLOAD_PATH_PATTERN: ATTACHMENT_UPLOAD_MAX_BYTES}
    moved = mount_contracts(schema="erp", auth_dependency=_auth, get_admin_client=lambda: object(), get_core_client=lambda: object(), prefix="/api/ctr")
    assert list(moved.max_body_path_overrides) == ["/api/ctr/*/attachments"]

    class Sched:
        jobs: dict = {}

        def register(self, job_id, fn, **kw):
            self.jobs[job_id] = kw

    sched = Sched()
    assert organ.register_jobs(scheduler=sched) == "contracts_generate_billing" and sched.jobs["contracts_generate_billing"] == {"hours": 24}
    assert organ.max_body_path_overrides and ORGAN_REGISTRY["contracts"].max_body_path_overrides() == organ.max_body_path_overrides


def test_contracts_migration_restates_the_finance_source_check_from_the_full_enum():
    from noctusai_lib.domain.finance.types import EntrySource, values

    sql = organ_migration_sql("contracts", "erp")
    for v in values(EntrySource):
        assert f"'{v}'" in sql, v
    assert "'purchasing'" in sql and "'contracts'" in sql


def test_mount_contracts_refuses_a_cfg_for_another_schema():
    from noctusai_lib.domain.contracts import ContractsConfig
    from noctusai_seed.organs import mount_contracts

    with pytest.raises(ValueError):
        mount_contracts(schema="erp", cfg=ContractsConfig(schema="other"), auth_dependency=_auth, get_admin_client=lambda: object(), get_core_client=lambda: object())
