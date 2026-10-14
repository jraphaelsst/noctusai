"""The ERP link: stock holds through the fulfillment handler (E6), the quote -> order handler (E7), the link delta.

Fakes only: `FakeStockPort` (the inventory port's own in-memory twin, same rules as the RPCs), the fake gateway, the mock
PostgREST client validated against the generators' schema. The RPCs themselves are proven on a real Postgres in
`inventory/test_inventory_on_real_postgres.py`; the delta's DDL in `test_erp_link_on_real_postgres.py`.
"""
from __future__ import annotations

import logging
from typing import Any

import pytest

from noctusai_lib.domain.commerce import (
    CommerceError,
    FakeCheckoutGateway,
    FulfillmentType,
    OrderChannel,
    catalog,
    make_fulfillment_registry,
    orders,
)
from noctusai_lib.domain.commerce.checkout import create_checkout
from noctusai_lib.domain.commerce.erp_sql import commerce_erp_migration
from noctusai_lib.domain.commerce.quote_handlers import (
    CLIENTE_SEM_EMAIL,
    LINHA_INVALIDA_PARA_PEDIDO,
    CommerceQuoteAcceptHandler,
)
from noctusai_lib.domain.commerce.stock_fulfillment import LATE_REF_SUFFIX, StockFulfillment
from noctusai_lib.domain.inventory import FakeStockPort
from noctusai_lib.domain.quotes import QuoteAcceptContext

from .conftest import CFG, ORG_A, ORG_B, SCHEMA, checkout_body, seed_product, seed_profile

ITEM = "11111111-1111-4111-8111-111111111111"
ITEM_B = "22222222-2222-4222-8222-222222222222"
PARTY = "33333333-3333-4333-8333-333333333333"
QUOTE = "44444444-4444-4444-8444-444444444444"
PHYSICAL = FulfillmentType.SHIPPING


class SpyStock(FakeStockPort):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def reserve(self, *a, **kw):
        self.calls.append("reserve")
        return super().reserve(*a, **kw)

    def commit(self, *a, **kw):
        self.calls.append("commit")
        return super().commit(*a, **kw)

    def release(self, *a, **kw):
        self.calls.append("release")
        return super().release(*a, **kw)


def registry(db: Any, stock: FakeStockPort):
    handler = StockFulfillment(get_stock=lambda: stock, get_db=lambda: db)
    return make_fulfillment_registry(
        {FulfillmentType.SHIPPING: handler, FulfillmentType.PICKUP: handler, FulfillmentType.LOCAL_DELIVERY: handler}
    )


def physical(db: Any, *, org: str = ORG_A, item: str | None = ITEM, price_cents: int = 5000, title: str = "Camiseta"):
    over = {"item_id": item} if item else {}
    return seed_product(db, org, title=title, product_type="physical", price_cents=price_cents, fulfillment_type="shipping", **over)


def go(db, gateway, body, fulfillment=None):
    return create_checkout(
        db, ORG_A, CFG, gateway, body, order_url_for=lambda t: f"https://x.test/pedido/{t}", fulfillment=fulfillment
    )


def order_rows(db):
    return db.table("commerce_orders").select("*").execute().data or []


# ── the delta ────────────────────────────────────────────────────────────────────────────────────────────────────


class TestLinkDelta:
    def test_the_generator_emits_the_link_and_is_rerunnable(self):
        sql = commerce_erp_migration(CFG, SCHEMA)
        assert sql == commerce_erp_migration(CFG, SCHEMA)
        # tenancy by construction: the composite FK, not a plain item_id reference
        assert "FOREIGN KEY (org_id, item_id) REFERENCES commerce.itm_items (org_id, id)" in sql
        assert "uq_commerce_orders_source_ref ON commerce.commerce_orders (org_id, source_ref) WHERE source_ref IS NOT NULL" in sql
        assert sql.count("IF NOT EXISTS") >= 4 and "DROP CONSTRAINT IF EXISTS commerce_orders_channel_check" in sql

    def test_product_api_carries_the_item_link(self, db):
        product, _ = physical(db)
        assert product["item_id"] == ITEM
        patched = catalog.update_product(db, ORG_A, product["id"], {"item_id": None})
        assert patched["item_id"] is None

    def test_a_product_without_a_link_writes_no_item_column(self, db):
        product, _ = seed_product(db, title="Ebook")
        assert "item_id" not in product  # a host that never applied the delta has no such column


# ── stock through the fulfillment handler (E6) ───────────────────────────────────────────────────────────────────


class TestStockHolds:
    def setup_method(self):
        self.stock = SpyStock()
        self.stock.receive(ORG_A, ITEM, 3, 1000)

    def test_checkout_reserves_the_linked_lines_and_nothing_else(self, db):
        seed_profile(db)
        _, offer = physical(db)
        _, digital = seed_product(db, title="Ebook")
        go(db, FakeCheckoutGateway(), checkout_body(offer["id"], items=[{"offer_id": offer["id"], "qty": 2}, {"offer_id": digital["id"], "qty": 1}]),
           registry(db, self.stock))
        (order,) = order_rows(db)
        assert self.stock.balance(ORG_A, ITEM).reserved == 2 and self.stock.available(ORG_A, ITEM) == 1
        assert list(self.stock.orders) == [(ORG_A, order["id"])]  # held under the ORDER id

    def test_oversell_refuses_the_sale_in_pt_br_and_writes_nothing(self, db):
        seed_profile(db)
        _, offer = physical(db)
        with pytest.raises(CommerceError) as exc:
            go(db, FakeCheckoutGateway(), checkout_body(offer["id"], items=[{"offer_id": offer["id"], "qty": 4}]), registry(db, self.stock))
        assert exc.value.code == "estoque_insuficiente" and exc.value.status_code == 409
        assert "Estoque insuficiente" in exc.value.message
        assert order_rows(db) == [] and self.stock.available(ORG_A, ITEM) == 3

    def test_the_last_unit_cannot_be_sold_twice(self, db):
        seed_profile(db)
        _, offer = physical(db)
        reg = registry(db, self.stock)
        go(db, FakeCheckoutGateway(), checkout_body(offer["id"], items=[{"offer_id": offer["id"], "qty": 3}]), reg)
        with pytest.raises(CommerceError) as exc:
            go(db, FakeCheckoutGateway(), checkout_body(offer["id"]), reg)
        assert exc.value.code == "estoque_insuficiente"
        assert len(order_rows(db)) == 1

    def test_a_coupon_is_given_back_when_the_stock_refuses(self, db):
        from noctusai_lib.domain.commerce import coupons

        seed_profile(db)
        _, offer = physical(db)
        coupons.create_coupon(db, ORG_A, {"code": "ONE", "kind": "percent", "value": 10, "max_uses": 1})
        with pytest.raises(CommerceError):
            go(db, FakeCheckoutGateway(), checkout_body(offer["id"], coupon="ONE", items=[{"offer_id": offer["id"], "qty": 9}]), registry(db, self.stock))
        assert db.table("commerce_coupons").select("*").execute().data[0]["uses_count"] == 0

    def test_a_gateway_failure_gives_the_hold_back(self, db):
        from noctusai_lib.integrations.payments.errors import PaymentGatewayError

        seed_profile(db)
        _, offer = physical(db)

        class Boom(FakeCheckoutGateway):
            def hosted_checkout(self, org_id):
                class H:
                    def create_checkout(self, req):
                        raise PaymentGatewayError("asaas", "refused", status=400, retryable=False)

                return H()

        with pytest.raises(CommerceError) as exc:
            go(db, Boom(), checkout_body(offer["id"], items=[{"offer_id": offer["id"], "qty": 2}]), registry(db, self.stock))
        assert exc.value.code == "pagamento_falhou"
        assert self.stock.balance(ORG_A, ITEM).reserved == 0 and self.stock.available(ORG_A, ITEM) == 3

    def test_paid_commits_and_a_redelivery_is_idempotent(self, db):
        seed_profile(db)
        _, offer = physical(db)
        reg = registry(db, self.stock)
        go(db, FakeCheckoutGateway(), checkout_body(offer["id"], items=[{"offer_id": offer["id"], "qty": 2}]), reg)
        (order,) = order_rows(db)
        items = orders.list_items(db, ORG_A, order["id"])
        reg.dispatch_paid(order, items)
        reg.dispatch_paid(order, items)  # Asaas sends confirmed AND received
        bal = self.stock.balance(ORG_A, ITEM)
        assert (bal.on_hand, bal.reserved) == (1, 0)

    def test_expired_and_cancelled_orders_release_the_hold(self, db):
        seed_profile(db)
        _, offer = physical(db)
        reg = registry(db, self.stock)
        go(db, FakeCheckoutGateway(), checkout_body(offer["id"], items=[{"offer_id": offer["id"], "qty": 2}]), reg)
        (order,) = order_rows(db)
        reg.dispatch_expired(order, orders.list_items(db, ORG_A, order["id"]))
        assert self.stock.available(ORG_A, ITEM) == 3
        # a second order, cancelled by staff through the service
        go(db, FakeCheckoutGateway(), checkout_body(offer["id"]), reg)
        second = [o for o in order_rows(db) if o["id"] != order["id"]][0]
        assert self.stock.available(ORG_A, ITEM) == 2
        orders.cancel_order(db, ORG_A, second["id"], fulfillment=reg)
        assert self.stock.available(ORG_A, ITEM) == 3

    def test_revoking_a_paid_order_does_not_pretend_to_restock(self, db, caplog):
        seed_profile(db)
        _, offer = physical(db)
        reg = registry(db, self.stock)
        go(db, FakeCheckoutGateway(), checkout_body(offer["id"]), reg)
        (order,) = order_rows(db)
        items = orders.list_items(db, ORG_A, order["id"])
        reg.dispatch_paid(order, items)
        with caplog.at_level(logging.INFO):
            reg.dispatch_revoked(order, items)  # must not raise: the goods already left
        assert self.stock.balance(ORG_A, ITEM).on_hand == 2

    def test_paying_after_the_hold_expired_rehold_and_commits(self, db):
        seed_profile(db)
        _, offer = physical(db)
        reg = registry(db, self.stock)
        go(db, FakeCheckoutGateway(), checkout_body(offer["id"]), reg)
        (order,) = order_rows(db)
        items = orders.list_items(db, ORG_A, order["id"])
        reg.dispatch_expired(order, items)
        reg.dispatch_paid(order, items)  # late payment (EXPIRED -> PAID)
        assert (self.stock.balance(ORG_A, ITEM).on_hand, self.stock.balance(ORG_A, ITEM).reserved) == (2, 0)
        assert (ORG_A, order["id"] + LATE_REF_SUFFIX) in self.stock.orders

    def test_paying_with_no_stock_left_never_raises_over_real_money(self, db, caplog):
        seed_profile(db)
        _, offer = physical(db)
        reg = registry(db, self.stock)
        go(db, FakeCheckoutGateway(), checkout_body(offer["id"]), reg)
        (order,) = order_rows(db)
        items = orders.list_items(db, ORG_A, order["id"])
        reg.dispatch_expired(order, items)
        self.stock.balances[(ORG_A, ITEM, "default")].on_hand = 0  # sold elsewhere meanwhile
        with caplog.at_level(logging.ERROR):
            reg.dispatch_paid(order, items)
        assert "PAID but its stock could not be committed" in caplog.text

    def test_unlinked_and_digital_lines_never_touch_the_port(self, db):
        spy = SpyStock()
        seed_profile(db)
        _, unlinked = physical(db, item=None, title="Sem item")
        _, digital = seed_product(db, title="Ebook")
        go(db, FakeCheckoutGateway(), checkout_body(unlinked["id"], items=[{"offer_id": unlinked["id"], "qty": 5}, {"offer_id": digital["id"], "qty": 1}]), registry(db, spy))
        assert spy.calls == []

    def test_stock_is_per_org(self, db):
        seed_profile(db)
        _, offer = physical(db)
        self.stock.receive(ORG_B, ITEM, 100, 1000)  # another org's stock of the same id does not count
        with pytest.raises(CommerceError):
            go(db, FakeCheckoutGateway(), checkout_body(offer["id"], items=[{"offer_id": offer["id"], "qty": 4}]), registry(db, self.stock))


# ── quote -> order (E7) ──────────────────────────────────────────────────────────────────────────────────────────


def seed_party(db, *, email: str | None = "ana@example.com", org: str = ORG_A) -> None:
    db.table("pty_parties").insert({
        "id": PARTY, "org_id": org, "kind": "PF", "doc": "52998224725", "legal_name": "Ana Souza", "trade_name": None,
        "email": email, "phones": ["11988887777"], "address": {"city": "Santos"}, "is_active": True,
    }).execute()


def line(desc="Camiseta", qty=2, unit=5000, discount=0, item_id=ITEM, kind="goods") -> dict:
    gross = round(qty * unit)
    return {"id": "l", "position": 0, "item_id": item_id, "description": desc, "unit": "UN", "kind": kind, "qty": qty,
            "unit_price_cents": unit, "discount_cents": discount, "total_cents": gross - discount}


def accept_ctx(lines: list[dict], *, discount=0, convert_to="order", quote_id=QUOTE, org=ORG_A) -> QuoteAcceptContext:
    subtotal = sum(ln["total_cents"] for ln in lines)
    quote = {"id": quote_id, "number": "ORC-00001", "party_id": PARTY, "title": None, "currency": "BRL",
             "subtotal_cents": subtotal, "discount_cents": discount, "total_cents": subtotal - discount,
             "party": {"id": PARTY, "legal_name": "Ana Souza", "trade_name": None, "email": "ana@example.com"}}
    return QuoteAcceptContext(org_id=org, quote=quote, lines=tuple(lines), acceptance={}, convert_to=convert_to)


class TestQuoteToOrder:
    def setup_method(self):
        self.stock = SpyStock()
        self.stock.receive(ORG_A, ITEM, 5, 1000)

    def handler(self, db, with_stock=True):
        return CommerceQuoteAcceptHandler(get_db=lambda: db, get_fulfillment=(lambda: registry(db, self.stock)) if with_stock else None)

    def test_creates_a_manual_draft_order_with_its_lines_event_and_customer(self, db):
        seed_party(db)
        product, _ = physical(db)
        result = self.handler(db).handle(accept_ctx([line(qty=2, unit=5000, discount=500)], discount=250))
        assert result.kind == "order"
        (order,) = order_rows(db)
        assert order["id"] == result.ref
        assert (order["status"], order["channel"], order["source_ref"]) == ("created", OrderChannel.MANUAL.value, QUOTE)
        assert (order["subtotal_cents"], order["discount_cents"], order["total_cents"]) == (9500, 250, 9250)
        assert order["payment_method"] is None and order["gateway"] is None
        (item,) = orders.list_items(db, ORG_A, order["id"])
        assert (item["product_id"], item["qty"], item["total_cents"], item["fulfillment_type"]) == (product["id"], 2, 9500, "shipping")
        (event,) = orders.list_events(db, ORG_A, order["id"])
        assert event["to_status"] == "created" and "ORC-00001" in event["reason"]
        (customer,) = db.table("commerce_customers").select("*").execute().data
        assert customer["email"] == "ana@example.com" and customer["id"] == order["customer_id"]
        assert self.stock.balance(ORG_A, ITEM).reserved == 2  # held under the order id

    def test_is_idempotent_on_the_quote_id(self, db):
        seed_party(db)
        physical(db)
        h = self.handler(db)
        first = h.handle(accept_ctx([line()]))
        again = h.handle(accept_ctx([line()]))
        assert again.ref == first.ref and again.detail["created"] is False
        assert len(order_rows(db)) == 1 and self.stock.balance(ORG_A, ITEM).reserved == 2  # one order, one hold

    def test_oversell_fails_the_conversion_and_writes_nothing(self, db):
        seed_party(db)
        physical(db)
        with pytest.raises(CommerceError) as exc:
            self.handler(db).handle(accept_ctx([line(qty=9)]))
        assert exc.value.code == "estoque_insuficiente"
        assert order_rows(db) == [] and self.stock.available(ORG_A, ITEM) == 5

    def test_a_line_without_a_catalog_product_is_a_plain_line_without_stock(self, db):
        seed_party(db)
        self.handler(db).handle(accept_ctx([line(item_id=ITEM_B, desc="Frete avulso")]))
        (item,) = orders.list_items(db, ORG_A, order_rows(db)[0]["id"])
        assert (item["product_id"], item["fulfillment_type"]) == (None, "none") and self.stock.orders == {}

    def test_a_party_without_email_cannot_be_an_orders_customer(self, db):
        seed_party(db, email=None)
        with pytest.raises(CommerceError) as exc:
            self.handler(db).handle(accept_ctx([line()]))
        assert exc.value.code == CLIENTE_SEM_EMAIL and order_rows(db) == []

    @pytest.mark.parametrize("bad", [line(qty=2.5), line(unit=0)])
    def test_lines_an_order_cannot_hold_fail_loudly_in_pt_br(self, db, bad):
        seed_party(db)
        with pytest.raises(CommerceError) as exc:
            self.handler(db).handle(accept_ctx([bad]))
        assert exc.value.code == LINHA_INVALIDA_PARA_PEDIDO and order_rows(db) == []

    def test_another_orgs_party_is_not_found(self, db):
        seed_party(db, org=ORG_B)
        with pytest.raises(CommerceError) as exc:
            self.handler(db).handle(accept_ctx([line()]))
        assert exc.value.code == "cliente_nao_encontrado"

    def test_a_failure_after_the_hold_gives_the_hold_back(self, db):
        class Boom(Exception):
            pass

        class FailingItemsDb(type(db)):  # a DB double whose items insert fails (a subclass, not a patch of our code)
            def table(self, name):
                if name == "commerce_order_items":
                    raise Boom("db down")
                return super().table(name)

        flaky = FailingItemsDb(validate_schema=True, schema=SCHEMA)
        seed_party(flaky)
        physical(flaky)
        with pytest.raises(Boom):
            self.handler(flaky).handle(accept_ctx([line()]))
        assert order_rows(flaky) == [] and self.stock.balance(ORG_A, ITEM).reserved == 0
