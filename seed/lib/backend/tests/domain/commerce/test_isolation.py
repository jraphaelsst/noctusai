"""Per-table org isolation: org B can neither read nor write org A's rows via the service layer."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.commerce import (
    COMMERCE_TABLES, CommerceError, FakeCheckoutGateway, catalog, coupons, customers, hosts, orders, profile,
)
from noctusai_lib.domain.commerce.checkout import create_checkout
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import CFG, ORG_A, ORG_B, USER_ID, checkout_body, seed_product, seed_profile


@pytest.fixture
def world(db):
    """Org A with one row in EVERY commerce table."""
    seed_profile(db)
    cat = catalog.create_category(db, ORG_A, {"name": "Cat"})
    p, o = seed_product(db, category_id=cat["id"])
    db.table("commerce_media").insert({
        "id": "m1", "org_id": ORG_A, "product_id": p["id"], "storage_path": f"{ORG_A}/x", "kind": "image",
        "alt": "", "position": 0, "created_at": "2026-01-01T00:00:00+00:00"}).execute()
    coupons.create_coupon(db, ORG_A, {"code": "A10", "kind": "percent", "value": 10})
    hosts.add_host(db, ORG_A, "loja-a.test")
    create_checkout(db, ORG_A, CFG, FakeCheckoutGateway(), checkout_body(o["id"]), order_url_for=lambda t: t)
    cust = db.table("commerce_customers").select("*").execute().data[0]
    customers.create_privacy_request(db, ORG_A, cust["id"], __import__("noctusai_lib.domain.commerce", fromlist=["x"]).PrivacyRequestKind.ACCESS, None)
    return {"product": p, "offer": o, "category": cat, "customer": cust,
            "order": db.table("commerce_orders").select("*").execute().data[0],
            "coupon": db.table("commerce_coupons").select("*").execute().data[0]}


def test_world_populates_every_table(db, world):
    for table in COMMERCE_TABLES:
        assert db.table(table).select("*").execute().data, f"fixture left {table} empty"


def test_every_row_written_by_the_services_carries_its_org(db, world):
    for table in COMMERCE_TABLES:
        for row in db.table(table).select("*").execute().data:
            assert row["org_id"] == ORG_A, (table, row)


def test_org_b_reads_see_nothing(db, world):
    assert profile.get_profile(db, ORG_B) is None
    assert catalog.list_categories(db, ORG_B) == []
    assert catalog.list_products(db, ORG_B)[0] == [] and catalog.list_products(db, ORG_B)[1] == 0
    assert coupons.list_coupons(db, ORG_B) == []
    assert customers.list_customers(db, ORG_B)[0] == [] and orders.list_orders(db, ORG_B)[0] == []
    assert hosts.list_hosts(db, ORG_B) == []
    assert orders.get_order_by_token(db, ORG_B, world["order"]["token"]) is None


def test_org_b_by_id_access_is_a_404_everywhere(db, world):
    p, o, cat, cust, order, coupon = (world[k] for k in ("product", "offer", "category", "customer", "order", "coupon"))
    calls = [
        lambda: catalog.get_product(db, ORG_B, p["id"]),
        lambda: catalog.list_offers(db, ORG_B, p["id"]),
        lambda: catalog.update_product(db, ORG_B, p["id"], {"title": "pwn"}),
        lambda: catalog.set_product_status(db, ORG_B, p["id"], "retired"),
        lambda: catalog.delete_product_rows(db, ORG_B, p["id"]),
        lambda: catalog.update_offer(db, ORG_B, p["id"], o["id"], {"price_cents": 1}),
        lambda: catalog.delete_offer(db, ORG_B, p["id"], o["id"]),
        lambda: catalog.update_category(db, ORG_B, cat["id"], {"name": "pwn"}),
        lambda: catalog.delete_category(db, ORG_B, cat["id"]),
        lambda: coupons.update_coupon(db, ORG_B, coupon["id"], {"active": False}),
        lambda: coupons.delete_coupon(db, ORG_B, coupon["id"]),
        lambda: customers.get_customer(db, ORG_B, cust["id"]),
        lambda: customers.anonymize_customer(db, ORG_B, cust["id"]),
        lambda: customers.enrich_from_payment(db, ORG_B, cust["id"], {"name": "pwn"}),
        lambda: orders.get_order(db, ORG_B, order["id"]),
        lambda: orders.cancel_order(db, ORG_B, order["id"]),
        lambda: hosts.delete_host(db, ORG_B, "loja-a.test"),
    ]
    for call in calls:
        with pytest.raises(NotFoundError):
            call()


def test_org_b_writes_never_touch_org_a_rows(db, world):
    snapshot = {t: [dict(r) for r in db.table(t).select("*").execute().data] for t in COMMERCE_TABLES}
    with pytest.raises(NotFoundError):
        catalog.update_product(db, ORG_B, world["product"]["id"], {"title": "pwn"})
    with pytest.raises(CommerceError):  # checkout on B with A's offer id: unsellable
        create_checkout(db, ORG_B, CFG, FakeCheckoutGateway(), checkout_body(world["offer"]["id"]), order_url_for=lambda t: t)
    after = {t: [dict(r) for r in db.table(t).select("*").execute().data] for t in COMMERCE_TABLES}
    assert after["commerce_products"] == snapshot["commerce_products"]
    assert after["commerce_orders"] == snapshot["commerce_orders"]
    assert all(r["org_id"] == ORG_A for t in after for r in after[t])


def test_same_slug_and_email_are_independent_per_org(db, world):
    seed_profile(db, ORG_B)
    seed_product(db, ORG_B, title="Ebook")  # slug "ebook" exists in A
    b = customers.upsert_buyer(db, ORG_B, {"name": "Outra", "email": "ana@example.com"})
    assert b["org_id"] == ORG_B and b["id"] != world["customer"]["id"]
