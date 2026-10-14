"""ERP W3-W4 on the commerce host: purchasing, quotes (+ the public accept link), contracts, and the stock link.

Pins: (a) every rendered organ migration equals its generator output and the organs are numbered in `requires` order
(`assert_organ_migration_order`); (b) every route is mounted and the staff surface is strictly 401; (c) the customer's
quote link is public but fails closed (bad token -> 404, no secret -> 503); (d) physical fulfillment holds stock through the
inventory `StockPort`, digital stays a Noop, and the storefront checkout is wired to the registry; (e) the accepted-quote
handler routes goods -> order, services -> contract; (f) parties are protected from deletion while any ERP row points at them;
(g) the contracts billing job is on the scheduler; (h) the pages' `status_pagina` rows ship in 029. Collaborators swap through
`dependency_overrides` -- nothing is patched.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migrations_dir
from noctusai_lib.testing.organs import assert_organ_migration_current, find_organ_migration

PRODUCT_DIR = Path(__file__).resolve().parents[1]
UUID0 = "00000000-0000-0000-0000-000000000000"
NEW_ORGANS = ("purchasing", "quotes", "contracts", "commerce_erp")
MOUNTED_ORGANS = (
    "commerce_money", "commerce_fiscal", "jobs", "finance", "items", "parties", "inventory", *NEW_ORGANS,
)


@pytest.mark.parametrize("organ", NEW_ORGANS)
def test_rendered_organ_migration_is_the_generators_output(organ):
    assert_organ_migration_current(PRODUCT_DIR, organ, schema="commerce")


def test_organ_migrations_are_numbered_in_requires_order():
    from noctusai_seed.organs import assert_organ_migration_order

    # finance -> parties is satisfied by the separate `finance_party_link` delta (pinned in test_commerce_p4_wiring.py)
    numbers = assert_organ_migration_order(PRODUCT_DIR, MOUNTED_ORGANS, waived=(("finance", "parties"),))
    for organ in NEW_ORGANS:
        assert numbers[organ] > max(numbers[dep] for dep in ("finance", "items", "parties", "inventory"))
    assert numbers["commerce_erp"] > numbers["commerce_money"]


def test_applied_migrations_were_not_rewritten():
    """014-018 are APPLIED in prod (`migrations-applied.json`): the ERP link ships as NEW files only."""
    import hashlib
    import json

    applied = json.loads((PRODUCT_DIR / "migrations-applied.json").read_text(encoding="utf-8"))["applied"]
    for name, digest in applied.items():
        assert hashlib.sha256((migrations_dir(PRODUCT_DIR) / name).read_bytes()).hexdigest() == digest, name
    numbers = [int(p.name.split("_", 1)[0]) for p in migrations_dir(PRODUCT_DIR).glob("*.sql")]
    assert len(numbers) == len(set(numbers))


def test_status_pagina_rows_for_the_new_pages_are_production():
    (path,) = [p for p in migrations_dir(PRODUCT_DIR).glob("*.sql") if "erp_pages_status_pagina" in p.name]
    body = path.read_text(encoding="utf-8")
    for page in ("compras", "orcamentos", "contratos"):
        assert f"('{page}', 'producao')" in body
    assert "ON CONFLICT (nome_pagina) DO NOTHING" in body  # never overwrite an operator's flip


def _routes(app) -> set[tuple[str, str]]:
    return {(m, r.path) for r in app.routes if hasattr(r, "methods") for m in r.methods}


ROUTES = [
    ("GET", "/api/purchasing/orders"), ("POST", "/api/purchasing/orders"), ("POST", "/api/purchasing/orders/{order_id}/approve"),
    ("POST", "/api/purchasing/orders/{order_id}/receipts"), ("GET", "/api/purchasing/approvers"),
    ("POST", "/api/purchasing/approvers"), ("DELETE", "/api/purchasing/approvers/{user_id}"),
    ("GET", "/api/quotes"), ("POST", "/api/quotes"), ("POST", "/api/quotes/{quote_id}/send"),
    ("POST", "/api/quotes/{quote_id}/convert"),
    ("GET", "/api/public/quotes/{token}"), ("POST", "/api/public/quotes/{token}/accept"), ("POST", "/api/public/quotes/{token}/reject"),
    ("GET", "/api/contracts"), ("POST", "/api/contracts"), ("GET", "/api/contracts/{contract_id}/billing-preview"),
    ("POST", "/api/contracts/billing/run"),
]


@pytest.mark.parametrize("method,path", ROUTES)
def test_route_is_mounted(client, method, path):
    from app.main import app

    assert (method, path) in _routes(app), f"{method} {path} is not mounted"


STAFF_ROUTES = [
    ("GET", "/api/purchasing/orders"), ("POST", "/api/purchasing/orders"), ("GET", "/api/purchasing/approvers"),
    ("GET", "/api/purchasing/settings"), ("GET", "/api/purchasing/receipts"),
    ("GET", "/api/quotes"), ("POST", "/api/quotes"), ("POST", f"/api/quotes/{UUID0}/send"), ("POST", f"/api/quotes/{UUID0}/convert"),
    ("GET", "/api/contracts"), ("POST", "/api/contracts"), ("GET", f"/api/contracts/{UUID0}"),
    ("POST", "/api/contracts/billing/run"),
]


@pytest.mark.parametrize("method,path", STAFF_ROUTES)
def test_staff_routes_are_strictly_401_without_auth(client, method, path):
    assert client.raw().request(method, path).status_code == 401


class TestPublicQuoteLink:
    """The customer's accept link carries NO login: the signed token is the credential and every failure is a closed door."""

    def test_a_bad_token_is_the_same_404_for_every_route(self, client):
        from app import commerce_deps as deps
        from app.main import app

        app.dependency_overrides[deps.get_link_secret] = lambda: "test-link-secret-0123456789"
        try:
            raw = client.raw()
            codes = {
                raw.get("/api/public/quotes/not-a-token").status_code,
                raw.get("/api/public/quotes/not-a-token/pdf").status_code,
                raw.post("/api/public/quotes/not-a-token/accept", json={"name": "Ana Souza", "agree": True}).status_code,
                raw.post("/api/public/quotes/not-a-token/reject", json={"reason": "caro"}).status_code,
            }
        finally:
            app.dependency_overrides.pop(deps.get_link_secret, None)
        assert codes == {404}

    def test_without_the_link_secret_it_fails_closed_never_open(self, client):
        resp = client.raw().get("/api/public/quotes/not-a-token")
        assert resp.status_code == 503 and resp.status_code != 200

    def test_the_link_points_at_the_spas_public_accept_page(self):
        from app import commerce_deps as deps

        url = deps.quote_accept_url("tok123")
        assert url.endswith("/orcamento/tok123") and url.startswith("http")


class TestStockWiring:
    def test_physical_fulfillment_holds_stock_and_digital_stays_noop(self):
        from app import commerce_deps as deps
        from noctusai_lib.domain.commerce import FulfillmentType, NoopFulfillment
        from noctusai_lib.domain.commerce.stock_fulfillment import StockFulfillment

        registry = deps.get_fulfillment()
        for physical in (FulfillmentType.SHIPPING, FulfillmentType.PICKUP, FulfillmentType.LOCAL_DELIVERY):
            assert isinstance(registry.handler_for(physical), StockFulfillment)
        for other in (FulfillmentType.DIGITAL_DELIVERY, FulfillmentType.NONE):
            assert type(registry.handler_for(other)) is NoopFulfillment

    def test_the_stock_port_is_the_real_one_over_this_schema(self):
        from app import commerce_deps as deps
        from app.commerce import INVENTORY_CFG, SCHEMA
        from noctusai_lib.domain.inventory import SupabaseStockPort

        port = deps.get_stock_port()
        assert isinstance(port, SupabaseStockPort) and INVENTORY_CFG.schema == SCHEMA

    def test_the_storefront_checkout_and_the_staff_cancel_reach_the_registry(self):
        from app import commerce_deps as deps
        from app.routers.commerce_routers import public_router, staff_router

        def depends_on_registry(router, name):
            (route,) = [r for r in router.routes if getattr(r, "name", "") == name]
            return any(d.call is deps.get_fulfillment for d in route.dependant.dependencies)

        assert depends_on_registry(public_router, "storefront_checkout") or any(
            d.call is deps.get_fulfillment for r in public_router.routes for d in getattr(getattr(r, "dependant", None), "dependencies", [])
        )
        # the staff cancel builds MoneyDeps (which carries the registry) from this dependency
        assert any(
            d.call is not None and d.call.__name__ == "money_deps"
            for r in staff_router.routes if getattr(r, "name", "") == "commerce_cancel_order" for d in r.dependant.dependencies
        )


class TestQuoteAcceptHandlerWiring:
    def test_goods_become_a_commerce_order_and_services_a_contract(self):
        from app import commerce_deps as deps
        from noctusai_lib.domain.commerce.quote_handlers import CommerceQuoteAcceptHandler
        from noctusai_lib.domain.contracts.quote_handler import ContractQuoteAcceptHandler
        from noctusai_lib.domain.quotes import QuoteAcceptContext, RoutingQuoteAcceptHandler

        handler = deps.get_quote_accept_handler()
        assert isinstance(handler, RoutingQuoteAcceptHandler)
        assert set(handler._handlers) == {"order", "contract"}  # noqa: SLF001 -- the routing table IS the contract
        assert isinstance(handler._handlers["order"], CommerceQuoteAcceptHandler)  # noqa: SLF001
        assert isinstance(handler._handlers["contract"], ContractQuoteAcceptHandler)  # noqa: SLF001
        # a kind nobody converts is "skipped", never an error
        none_ctx = QuoteAcceptContext(org_id="o", quote={"id": "q"}, lines=(), acceptance={}, convert_to="none")
        assert handler.handle(none_ctx) is None

    def test_the_quotes_organ_is_given_that_handler(self):
        src = (PRODUCT_DIR / "app" / "routers" / "commerce_routers.py").read_text(encoding="utf-8")
        assert "get_accept_handler=deps.get_quote_accept_handler" in src and "get_link_secret=deps.get_link_secret" in src


def test_parties_are_protected_while_any_erp_row_points_at_them():
    src = (PRODUCT_DIR / "app" / "routers" / "commerce_routers.py").read_text(encoding="utf-8")
    for pair in ('("fin_entries", "party_id")', '("pur_orders", "party_id")', '("quo_quotes", "party_id")', '("ctr_contracts", "party_id")'):
        assert pair in src, pair


def test_contracts_billing_rides_on_the_scheduler():
    from noctusai_lib.api import scheduler as seed_scheduler

    from app.scheduler import configure

    names = configure()
    assert "contracts_generate_billing" in names
    assert "contracts_generate_billing" in {j.id for j in seed_scheduler.scheduler.get_jobs()}


def test_the_new_upload_surface_is_covered_by_a_body_override():
    from app.main import app  # noqa: F401  (boot refuses an UploadFile route without a covering override)
    from noctusai_lib.domain.contracts import ATTACHMENT_UPLOAD_PATH_PATTERN
    from noctusai_seed.organs import ORGAN_REGISTRY

    assert ATTACHMENT_UPLOAD_PATH_PATTERN in ORGAN_REGISTRY["contracts"].max_body_path_overrides()


def test_find_organ_migration_finds_each_new_file_exactly_once():
    from noctusai_seed.organs import ORGAN_REGISTRY

    for organ in NEW_ORGANS:
        assert len(find_organ_migration(PRODUCT_DIR, ORGAN_REGISTRY[organ].migration_header)) == 1, organ
