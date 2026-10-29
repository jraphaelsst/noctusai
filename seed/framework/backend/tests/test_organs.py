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
    with pytest.raises(AssertionError, match="no rendered finance migration found"):
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


# -- finance reminders -----------------------------------------------------------------------------------


def _reminders_client(*, role: str):
    from noctusai_lib.domain.finance.reminders import FakeReminderChannel, ReminderContact, ReminderPorts
    from noctusai_lib.testing import MockSupabaseClient
    from noctusai_seed.organs import mount_finance_reminders

    core = MockSupabaseClient()
    core.set_table_data("noctus_users", [{"id": "u1", "org_id": "org-1", "org_role": role, "role": "user"}])
    ports = ReminderPorts(channels={"whatsapp": FakeReminderChannel()}, resolve_contact=lambda s, e: ReminderContact(nome="x", phone="11999998888"))
    organ = mount_finance_reminders(schema="erp", auth_dependency=_auth, get_admin_client=lambda: MockSupabaseClient(),
                                    get_core_client=lambda: core, get_ports=lambda: ports)
    return organ, TestClient(_app_of(organ))


def test_mount_finance_reminders_strict_401_and_admin_gates_the_writes():
    organ, client = _reminders_client(role="member")
    P = "/api/finance/reminders"
    rid = "55555555-5555-4555-8555-555555555555"
    for method, path in (("GET", f"{P}/settings"), ("PUT", f"{P}/settings"), ("GET", f"{P}/rules"), ("POST", f"{P}/rules"),
                         ("PATCH", f"{P}/rules/{rid}"), ("DELETE", f"{P}/rules/{rid}"), ("PUT", f"{P}/receivables/{rid}/opt-out"),
                         ("GET", f"{P}/log"), ("GET", f"{P}/preview")):
        assert client.request(method, path, json={} if method in ("POST", "PUT", "PATCH") else None).status_code == 401, path
    assert client.put(f"{P}/settings", json={"enabled": True}, headers=H).status_code == 403  # member: not admin
    assert client.post(f"{P}/rules", json={"offset_days": 1, "template": "x"}, headers=H).status_code == 403
    assert client.get(f"{P}/rules", headers=H).status_code == 200


def test_mount_finance_reminders_exposes_the_daily_job_and_refuses_a_foreign_cfg():
    from noctusai_lib.domain.finance import FinanceConfig
    from noctusai_seed.organs import mount_finance_reminders

    organ, _ = _reminders_client(role="owner")

    class Sched:
        jobs: dict = {}

        def register(self, job_id, fn, **kw):
            self.jobs[job_id] = kw

    sched = Sched()
    assert organ.register_jobs(scheduler=sched) == "finance_billing_reminders"
    assert sched.jobs["finance_billing_reminders"]["cron"] == "0 12 * * *"
    with pytest.raises(ValueError):
        mount_finance_reminders(schema="erp", cfg=FinanceConfig(schema="other"), auth_dependency=_auth, get_admin_client=lambda: object(),
                                get_core_client=lambda: object(), get_ports=lambda: None)


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


def test_leads_organ_is_registered_and_mounts_with_strict_401():
    from noctusai_lib.domain.leads import LeadsConfig, leads_migration
    from noctusai_seed.organs import mount_leads

    spec = ORGAN_REGISTRY["leads"]
    assert spec.migration("erp") == leads_migration("erp") and spec.guard_probes is not None
    cfg = LeadsConfig(stages=["lead", "fechado"], origins=["whatsapp", "outro"])
    organ = mount_leads(auth_dependency=_auth, get_admin_client=lambda: object(), config=cfg)
    client = TestClient(_app_of(organ))
    assert client.get("/api/leads").status_code == 401
    assert client.get("/api/leads/board").status_code == 401
    assert client.post("/api/leads/x/move", json={}).status_code == 401
    assert {r.path for router in organ for r in router.routes} >= {"/api/leads", "/api/leads/board", "/api/leads/config", "/api/leads/{lead_id}/move"}


def test_clients_organ_is_registered_and_mounts_with_strict_401():
    from noctusai_lib.domain.clients import ClientsConfig, clients_migration
    from noctusai_lib.domain.finance import FinanceConfig
    from noctusai_seed.organs import mount_clients

    spec = ORGAN_REGISTRY["clients"]
    assert spec.migration("erp") == clients_migration("erp") and spec.guard_probes is not None
    assert [p.guard_name for p in spec.guard_probes("erp")] == ["uq_clients_lead", "uq_client_sessions_slot"]
    organ = mount_clients(schema="erp", auth_dependency=_auth, get_admin_client=lambda: object(),
                          get_core_client=lambda: object(), config=ClientsConfig())
    assert organ.max_body_path_overrides == {}
    client = TestClient(_app_of(organ))
    for method, path in (("GET", "/api/clients"), ("GET", "/api/clients/config"), ("POST", "/api/clients/x/payments"),
                         ("DELETE", "/api/clients/x"), ("GET", "/api/clients/sessions")):
        assert client.request(method, path, json={} if method == "POST" else None).status_code == 401, path
    assert {r.path for router in organ for r in router.routes} >= {"/api/clients", "/api/clients/{client_id}/payments", "/api/clients/sessions"}
    with pytest.raises(ValueError):
        mount_clients(schema="erp", auth_dependency=_auth, get_admin_client=lambda: object(), get_core_client=lambda: object(),
                      config=ClientsConfig(), finance_cfg=FinanceConfig(schema="other"))


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


def _purchasing_client(*, role: str, grants=(), other_org_grants=(), threshold=None, total=100_000):
    from noctusai_lib.testing import MockSupabaseClient
    from noctusai_seed.organs import mount_purchasing

    core = MockSupabaseClient()
    core.set_table_data("noctus_users", [{"id": "u1", "org_id": "org-1", "org_role": role, "role": "user"}])
    db = MockSupabaseClient()
    db.table("pur_orders").insert({"id": ORDER_ID, "org_id": "org-1", "number": 1, "status": "draft", "supplier_name": "F", "total_cents": total, "goods_cents": total}).execute()
    if threshold is not None:
        db.table("pur_settings").insert({"org_id": "org-1", "approval_threshold_cents": threshold}).execute()
    if grants:
        db.table("pur_approvers").insert({"org_id": "org-1", "user_id": "u1"}).execute()
    if other_org_grants:  # approver of ANOTHER org only: must not approve here
        db.table("pur_approvers").insert({"org_id": "org-2", "user_id": "u1"}).execute()
    db.set_rpc_data("pur_transition", {"status": "ok", "order_id": ORDER_ID})
    organ = mount_purchasing(schema="erp", auth_dependency=_auth, get_admin_client=lambda: db, get_core_client=lambda: core)
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


def test_purchasing_approval_comes_from_the_selected_org_role_and_the_org_scoped_approver_list():
    assert _purchasing_client(role="member").post(APPROVE, headers=H).status_code == 403            # staff, no grant
    assert _purchasing_client(role="member", grants=(1,)).post(APPROVE, headers=H).status_code == 200  # grant holder, not admin
    assert _purchasing_client(role="owner").post(APPROVE, headers=H).status_code == 200            # admin, no threshold
    # above the org threshold only the permission holder approves
    assert _purchasing_client(role="owner", threshold=50_000).post(APPROVE, headers=H).status_code == 403
    assert _purchasing_client(role="owner", grants=(1,), threshold=50_000).post(APPROVE, headers=H).status_code == 200
    assert _purchasing_client(role="owner", threshold=500_000).post(APPROVE, headers=H).status_code == 200
    # an approver grant in ANOTHER org never approves here (org-scoped list, no global permission)
    assert _purchasing_client(role="member", other_org_grants=(1,)).post(APPROVE, headers=H).status_code == 403
    assert _purchasing_client(role="owner", other_org_grants=(1,), threshold=50_000).post(APPROVE, headers=H).status_code == 403


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


# -- quotes ----------------------------------------------------------------------------------------------------

QUOTE_ID = "55555555-5555-4555-8555-555555555555"
SECRET = "quotes-test-secret-0123456789"


def _quotes_organ(**over):
    from noctusai_lib.testing import MockSupabaseClient
    from noctusai_seed.organs import mount_quotes

    core = MockSupabaseClient()
    core.set_table_data("noctus_users", [{"id": "u1", "org_id": "org-1", "org_role": over.pop("role", "member"), "role": "user"}])
    db = over.pop("db", None) or MockSupabaseClient()
    return mount_quotes(schema="erp", auth_dependency=_auth, get_admin_client=lambda: db, get_core_client=lambda: core, **over)


def test_quotes_is_registered_and_its_header_prefixes_the_migration():
    assert organ_migration_sql("quotes", "erp").startswith(ORGAN_REGISTRY["quotes"].migration_header)
    assert "erp.quo_quotes" in organ_migration_sql("quotes", "erp")


def test_mount_quotes_staff_routes_are_strict_401_and_admin_gates_the_writes():
    client = TestClient(_app_of(_quotes_organ()))
    for method, path in (("GET", "/api/quotes"), ("POST", "/api/quotes"), ("GET", f"/api/quotes/{QUOTE_ID}"),
                         ("POST", f"/api/quotes/{QUOTE_ID}/send"), ("POST", f"/api/quotes/{QUOTE_ID}/accept"), ("GET", f"/api/quotes/{QUOTE_ID}/pdf")):
        assert client.request(method, path, json={} if method == "POST" else None).status_code == 401, path
    assert client.post("/api/quotes", json={}, headers=H).status_code == 403          # member: not admin
    assert client.get("/api/quotes", headers=H).status_code == 200                      # member may read


def test_mount_quotes_public_routes_exist_only_with_a_link_secret_and_need_no_auth():
    without = _app_of(_quotes_organ())
    assert not any(r.path.startswith("/api/public/quotes") for r in without.routes)
    limited: list[str] = []

    def rate_limit(limit):
        def deco(fn):
            limited.append(limit)
            return fn
        return deco

    organ = _quotes_organ(get_link_secret=lambda: SECRET, rate_limit=rate_limit)
    app = _app_of(organ)
    assert {r.path for r in app.routes if r.path.startswith("/api/public/quotes")} == {
        "/api/public/quotes/{token}", "/api/public/quotes/{token}/pdf", "/api/public/quotes/{token}/accept", "/api/public/quotes/{token}/reject"}
    assert len(limited) == 4                                                              # every public route is throttled
    client = TestClient(app)
    r = client.get("/api/public/quotes/not-a-token")                                       # no Authorization header: the TOKEN is the gate
    assert (r.status_code, r.json()["error"]["code"]) == (404, "link_invalido")
    assert client.post("/api/public/quotes/not-a-token/accept", json={"name": "Ana Souza", "agree": True}).status_code == 404


def test_mount_quotes_optional_seams_mount_their_routes_only_when_supplied():
    plain = {r.path for r in _app_of(_quotes_organ()).routes}
    assert f"/api/quotes/{{quote_id}}/pdf" in plain
    assert not any(p.endswith("/docx") or p.endswith("/signature") for p in plain)
    full = {r.path for r in _app_of(_quotes_organ(get_signature=lambda: object(), docx_template=lambda ctx: b"x")).routes}
    assert "/api/quotes/{quote_id}/docx" in full and "/api/quotes/{quote_id}/signature" in full


def test_mount_quotes_send_without_a_link_secret_is_a_typed_503_for_an_admin():
    client = TestClient(_app_of(_quotes_organ(role="owner")))
    r = client.post(f"/api/quotes/{QUOTE_ID}/send", json={"channel": "link"}, headers=H)
    assert (r.status_code, r.json()["error"]["code"]) == (503, "link_indisponivel")


def test_mount_quotes_rejects_a_cfg_for_another_schema():
    from noctusai_lib.domain.quotes import QuotesConfig

    with pytest.raises(ValueError):
        _quotes_organ(cfg=QuotesConfig(schema="other"))

# -- organ dependency order (`OrganSpec.requires` + `assert_organ_migration_order`) ---------------------------


def test_every_requires_names_a_registered_organ_and_nothing_requires_itself_or_cycles():
    for name, spec in ORGAN_REGISTRY.items():
        for dep in (*spec.requires, *spec.optional_requires):
            assert dep in ORGAN_REGISTRY and dep != name, (name, dep)

    def depth(n: str, seen: tuple[str, ...] = ()) -> int:
        assert n not in seen, f"requires cycle: {seen + (n,)}"
        spec = ORGAN_REGISTRY[n]
        return 1 + max((depth(d, seen + (n,)) for d in (*spec.requires, *spec.optional_requires)), default=0)

    for n in ORGAN_REGISTRY:
        depth(n)


def test_requires_declares_the_documented_graph():
    spec = ORGAN_REGISTRY
    assert spec["inventory"].requires == ("items",)
    assert set(spec["purchasing"].requires) == {"parties", "items", "inventory", "finance"}
    assert set(spec["contracts"].requires) == {"parties", "items", "finance"}
    assert spec["finance"].requires == () and spec["finance"].optional_requires == ("parties",)
    assert set(spec["commerce_erp"].requires) == {"items", "commerce_money"}


def _render(tmp_path, numbering: dict[str, int], schema: str = "erp"):
    mig = tmp_path / "backend" / "migrations"
    mig.mkdir(parents=True, exist_ok=True)
    for organ, n in numbering.items():
        (mig / f"{n:03d}_{organ}.sql").write_text(organ_migration_sql(organ, schema), encoding="utf-8")
    return tmp_path


def test_assert_organ_migration_order_accepts_dependencies_first(tmp_path):
    from noctusai_seed.organs import assert_organ_migration_order

    organs = {"parties": 10, "items": 11, "finance": 12, "inventory": 13, "contracts": 14, "purchasing": 15}
    assert assert_organ_migration_order(_render(tmp_path, organs), list(organs)) == organs


def test_assert_organ_migration_order_refuses_a_dependent_numbered_before_its_dependency(tmp_path):
    from noctusai_seed.organs import assert_organ_migration_order

    organs = {"contracts": 10, "parties": 11, "items": 12, "finance": 13}
    with pytest.raises(AssertionError, match="contracts.*AFTER"):
        assert_organ_migration_order(_render(tmp_path, organs), list(organs))


def test_assert_organ_migration_order_refuses_a_missing_requirement_but_allows_a_missing_optional_one(tmp_path):
    from noctusai_seed.organs import assert_organ_migration_order

    with pytest.raises(AssertionError, match="inventory requires items"):
        assert_organ_migration_order(_render(tmp_path / "a", {"inventory": 10}), ["inventory"])
    # finance without parties is legal (the party link is optional); with parties mounted it must come after it
    assert assert_organ_migration_order(_render(tmp_path / "b", {"finance": 10}), ["finance"]) == {"finance": 10}
    with pytest.raises(AssertionError, match="finance.*AFTER parties"):
        assert_organ_migration_order(_render(tmp_path / "c", {"finance": 10, "parties": 11}), ["finance", "parties"])


def test_a_waiver_excuses_exactly_the_edge_a_separate_delta_satisfies(tmp_path):
    """commerce renders finance BEFORE parties and links them in a later delta file: that one edge is waived, nothing else."""
    from noctusai_seed.organs import assert_organ_migration_order

    organs = {"finance": 10, "parties": 11}
    root = _render(tmp_path, organs)
    assert assert_organ_migration_order(root, list(organs), waived=(("finance", "parties"),)) == organs
    # the other edges of a waived organ still bind
    both = {"parties": 10, "items": 11, "finance": 12, "inventory": 13, "contracts": 9}
    with pytest.raises(AssertionError, match="contracts.*AFTER"):
        assert_organ_migration_order(_render(tmp_path / "x", both), list(both), waived=(("finance", "parties"),))


def test_a_stale_waiver_fails_loudly(tmp_path):
    from noctusai_seed.organs import assert_organ_migration_order

    organs = {"parties": 10, "items": 11}
    with pytest.raises(AssertionError, match="waiver"):
        assert_organ_migration_order(_render(tmp_path, organs), list(organs), waived=(("items", "parties"),))


def test_mount_contracts_get_billing_seam_replaces_the_booking_for_the_job():
    """A host that decorates the booking (gateway charge per receivable) passes `get_billing`: the daily job uses it."""
    import asyncio

    from noctusai_lib.domain.contracts import FakeContractsBilling
    from noctusai_lib.testing import MockSupabaseClient
    from noctusai_seed.organs import mount_contracts

    db = MockSupabaseClient()
    seen: list = []
    billing = FakeContractsBilling()

    def get_billing(client):
        seen.append(client)
        return billing

    organ = mount_contracts(schema="erp", auth_dependency=_auth, get_admin_client=lambda: db, get_core_client=lambda: object(), get_billing=get_billing)

    class Sched:
        fns: dict = {}

        def register(self, job_id, fn, **kw):
            self.fns[job_id] = fn

    sched = Sched()
    organ.register_jobs(scheduler=sched)
    asyncio.run(sched.fns["contracts_generate_billing"]())
    assert seen == [db], "the job must book through the host's billing, resolved per run"
