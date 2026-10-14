"""P4 HTTP surface: refund authz, Idempotency-Key, quote `installment_options`, checkout `installments`, the public payment route."""
from __future__ import annotations

from datetime import timedelta

import pytest

from noctusai_lib.domain.commerce._common import now

from .conftest import CFG, ORG_A, ORG_B, checkout_body, pay, seed_product, seed_profile

UUID0 = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def shop(h):
    h.seed_host()
    seed_profile(h.db)
    _, offer = seed_product(h.db, price_cents=30000)
    return h, offer


def _place(h, offer, **over):
    r = h.client.post("/api/storefront/checkout", json=checkout_body(offer["id"], **over), headers=h.shop())
    assert r.status_code == 201, r.text
    order = h.db.table("commerce_orders").select("*").execute().data[-1]
    h.gateway.sync_charges()
    return order


def _paid_order(h, offer):
    order = _place(h, offer)
    pay(h.gateway, order)
    # settle through the real webhook route
    r = h.client.post(
        f"/api/webhooks/payments/asaas/{ORG_A}",
        json={"id": "evt_p", "event": "PAYMENT_RECEIVED", "payment": {"id": order["gateway_charge_id"], "status": "RECEIVED", "externalReference": order["id"]}},
        headers={"asaas-access-token": "hook-token"},
    )
    assert r.json()["outcome"] == "processed"
    return order


class TestRefundRoute:
    def test_unauthenticated_is_strictly_401(self, h):
        assert h.client.post(f"/api/commerce/orders/{UUID0}/refunds", json={"reason": "teste"}).status_code == 401

    def test_plain_staff_is_403_and_nothing_moves(self, shop):
        h, offer = shop
        order = _paid_order(h, offer)
        r = h.client.post(f"/api/commerce/orders/{order['id']}/refunds", json={"reason": "teste", "amount_cents": 100}, headers=h.staff())
        assert r.status_code == 403
        assert not [c for c in h.gateway.charges.calls if c[0] == "refund_charge"]

    def test_org_admin_refunds_partially_with_idempotency(self, shop):
        h, offer = shop
        order = _paid_order(h, offer)
        url = f"/api/commerce/orders/{order['id']}/refunds"
        hdr = {**h.staff("orgadmin"), "Idempotency-Key": "abc"}
        r = h.client.post(url, json={"reason": "cliente pediu", "amount_cents": 5000}, headers=hdr)
        assert r.status_code == 201 and r.json()["data"]["status"] == "done"
        again = h.client.post(url, json={"reason": "cliente pediu", "amount_cents": 5000}, headers=hdr)
        assert again.json()["data"]["id"] == r.json()["data"]["id"]
        assert len([c for c in h.gateway.charges.calls if c[0] == "refund_charge"]) == 1
        detail = h.client.get(f"/api/commerce/orders/{order['id']}", headers=h.staff()).json()["data"]
        assert detail["status"] == "partially_refunded"
        assert [x["status"] for x in detail["refunds"]] == ["done"] and detail["charges"][0]["status"] == "paid"
        assert detail["reminders"] == []

    def test_error_codes(self, shop):
        h, offer = shop
        order = _paid_order(h, offer)
        url = f"/api/commerce/orders/{order['id']}/refunds"
        r = h.client.post(url, json={"reason": "teste", "amount_cents": 999999}, headers=h.staff("orgadmin"))
        assert r.status_code == 422 and r.json()["error"]["code"] == "valor_excede_saldo"
        assert h.client.post(url, json={"reason": "x"}, headers=h.staff("orgadmin")).status_code == 422  # reason too short
        assert h.client.post(url, json={"reason": "teste", "nope": 1}, headers=h.staff("orgadmin")).status_code == 422
        other = h.client.post(url, json={"reason": "teste"}, headers=h.staff("org-b"))
        assert other.status_code == 403
        assert h.client.post(f"/api/commerce/orders/{UUID0}/refunds", json={"reason": "teste"}, headers=h.staff("orgadmin")).status_code == 404

    def test_another_orgs_order_is_a_404_for_the_service(self, shop):
        import asyncio

        from noctusai_lib.domain.commerce import refunds
        from noctusai_lib.primitives.exceptions import NotFoundError

        from .conftest import money_deps

        h, offer = shop
        order = _paid_order(h, offer)
        with pytest.raises(NotFoundError):
            asyncio.run(refunds.create_refund(h.db, ORG_B, money_deps(h.gateway), order["id"], amount_cents=1, reason="x", requested_by=None))


class TestQuoteAndCheckoutInstallments:
    def test_quote_lists_the_options(self, shop):
        h, offer = shop
        r = h.client.post("/api/storefront/checkout/quote", json={"items": [{"offer_id": offer["id"], "qty": 1}]}, headers=h.shop())
        opts = r.json()["data"]["installment_options"]
        assert [o["count"] for o in opts] == list(range(1, 13))
        assert opts[0] == {"count": 1, "installment_cents": 30000, "total_cents": 30000, "interest_free": True}
        assert opts[2]["interest_free"] and opts[2]["total_cents"] == 30000  # 3x free by default
        assert not opts[3]["interest_free"] and opts[3]["total_cents"] > 30000
        assert sum([opts[3]["installment_cents"]] * 3) < opts[3]["total_cents"]  # last parcela absorbs the remainder

    def test_card_checkout_charges_the_quoted_total(self, shop):
        h, offer = shop
        quoted = h.client.post("/api/storefront/checkout/quote", json={"items": [{"offer_id": offer["id"], "qty": 1}]}, headers=h.shop()).json()["data"]["installment_options"][5]
        r = h.client.post("/api/storefront/checkout", json=checkout_body(offer["id"], payment_method="credit_card", installments=6), headers=h.shop())
        assert r.status_code == 201 and r.json()["data"]["installment_count"] == 6
        req = h.gateway.checkout.calls[-1][1]
        assert req.installment_count == 6 and req.price.amount_cents == quoted["total_cents"] and req.customer_reference
        order = h.db.table("commerce_orders").select("*").execute().data[0]
        assert order["total_cents"] == 30000  # the order total is the cart; the CHARGE carries the interest
        view = h.client.get(f"/api/storefront/orders/{order['token']}", headers=h.shop()).json()["data"]
        assert view["installment_count"] == 6 and view["charged_cents"] == quoted["total_cents"]

    @pytest.mark.parametrize("method,count", [("pix", 3), ("credit_card", 13), ("credit_card", 0), ("credit_card", -1)])
    def test_invalid_installments_are_422(self, shop, method, count):
        h, offer = shop
        r = h.client.post("/api/storefront/checkout", json=checkout_body(offer["id"], payment_method=method, installments=count), headers=h.shop())
        assert r.status_code == 422 and r.json()["error"]["code"] == "parcelamento_invalido"
        assert h.db.table("commerce_orders").select("*").execute().data == []

    def test_store_settings_change_the_offer(self, shop):
        h, offer = shop
        from noctusai_lib.domain.commerce import profile

        cur = profile.get_profile(h.db, ORG_A)
        profile.put_profile(h.db, ORG_A, "u", {**{k: cur[k] for k in profile.PROFILE_FIELDS}, "installments_max": 4, "installments_interest_free": 2,
                                                "installment_interest_monthly_bps": 0}, expected_version=cur["version"], is_platform_admin=False)
        opts = h.client.post("/api/storefront/checkout/quote", json={"items": [{"offer_id": offer["id"], "qty": 1}]}, headers=h.shop()).json()["data"]["installment_options"]
        assert [o["count"] for o in opts] == [1, 2, 3, 4] and all(o["total_cents"] == 30000 for o in opts)  # 0 bps: no interest


class TestPaymentRoute:
    def test_regenerate_over_http(self, shop):
        h, offer = shop
        order = _place(h, offer)
        url = f"/api/storefront/orders/{order['token']}/payment"
        same = h.client.post(url, json={"payment_method": "pix"}, headers=h.shop())
        assert same.status_code == 200 and same.json()["data"]["checkout_url"] == order["checkout_url"]
        too_soon = h.client.post(url, json={"payment_method": "boleto"}, headers=h.shop())
        assert too_soon.status_code == 429 and too_soon.json()["error"]["code"] == "muitas_tentativas"
        h.db.table("commerce_orders").update({"last_charge_attempt_at": (now() - timedelta(minutes=5)).isoformat()}).eq("id", order["id"]).execute()
        r = h.client.post(url, json={"payment_method": "boleto"}, headers=h.shop())
        assert r.status_code == 200 and r.json()["data"]["status"] == "pending_payment"

    def test_unknown_token_and_foreign_host_are_404(self, shop):
        h, offer = shop
        assert h.client.post("/api/storefront/orders/nope/payment", json={"payment_method": "pix"}, headers=h.shop()).status_code == 404
        order = _place(h, offer)
        h.seed_host(ORG_B, "loja-b.test")
        assert h.client.post(f"/api/storefront/orders/{order['token']}/payment", json={"payment_method": "pix"}, headers=h.shop("loja-b.test")).status_code == 404

    def test_paid_order_is_409_not_payable(self, shop):
        h, offer = shop
        order = _paid_order(h, offer)
        r = h.client.post(f"/api/storefront/orders/{order['token']}/payment", json={"payment_method": "pix"}, headers=h.shop())
        assert r.status_code == 409 and r.json()["error"]["code"] == "pedido_nao_pagavel"

    def test_the_route_is_rate_limited_with_the_portal_policy(self, h):
        from noctusai_lib.api.rate_limit_policies import DEFAULT_PORTAL_RL

        assert CFG.payment_rate_limit == DEFAULT_PORTAL_RL and DEFAULT_PORTAL_RL in h.limited

    def test_cancel_voids_the_gateway_charge(self, shop):
        h, offer = shop
        order = _place(h, offer)
        r = h.client.post(f"/api/commerce/orders/{order['id']}/cancel", headers=h.staff())
        assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled"
        assert h.gateway.charges.charges[order["gateway_charge_id"]].status == "cancelled"


class TestSignedOrderLink:
    """S4: the reminder link is order-scoped and expiring; it opens that order's page + regenerate, nothing else."""

    def _link(self, order, ttl=60, org=ORG_A):
        from noctusai_lib.domain.commerce import access_links

        from .conftest import SECRET

        return access_links.sign_token(SECRET, purpose=access_links.PURPOSE_ORDER, org_id=org, subject=order["id"], ttl_minutes=ttl)

    def test_the_signed_link_opens_the_order_without_leaking_its_permanent_token(self, shop):
        h, offer = shop
        order = _place(h, offer)
        link = self._link(order)
        r = h.client.get(f"/api/storefront/orders/{link}", headers=h.shop())
        assert r.status_code == 200 and r.json()["data"]["token"] == link != order["token"]

    def test_the_signed_link_can_regenerate_the_payment(self, shop):
        h, offer = shop
        order = _place(h, offer)
        h.db.table("commerce_orders").update({"last_charge_attempt_at": (now() - timedelta(minutes=5)).isoformat()}).eq("id", order["id"]).execute()
        r = h.client.post(f"/api/storefront/orders/{self._link(order)}/payment", json={"payment_method": "boleto"}, headers=h.shop())
        assert r.status_code == 200

    def test_expired_forged_and_wrong_purpose_links_are_400(self, shop):
        from noctusai_lib.domain.commerce import access_links

        from .conftest import SECRET

        h, offer = shop
        order = _place(h, offer)
        for bad in (
            self._link(order, ttl=-5),
            self._link(order) + "x",
            access_links.sign_token(SECRET, purpose=access_links.PURPOSE_MY_ORDERS, org_id=ORG_A, subject=order["customer_id"], ttl_minutes=5),
        ):
            r = h.client.get(f"/api/storefront/orders/{bad}", headers=h.shop())
            assert r.status_code == 400 and r.json()["error"]["code"] == "link_invalido"

    def test_a_link_minted_for_another_store_is_useless_here(self, shop):
        h, offer = shop
        order = _place(h, offer)
        r = h.client.get(f"/api/storefront/orders/{self._link(order, org=ORG_B)}", headers=h.shop())
        assert r.status_code == 400
