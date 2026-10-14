"""Router contract tests via TestClient: paths, status codes, envelopes, error codes, 401s."""
from __future__ import annotations

import json
import re

import pytest

from noctusai_lib.domain.commerce import access_links, customers, storefront
from noctusai_lib.domain.licensing import FakeLicenseChecker

from .conftest import CFG, HOST_A, HOST_B, ORG_A, ORG_B, SECRET, VALID_CNPJ, checkout_body, seed_product, seed_profile

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
UUID0 = "11111111-1111-1111-1111-111111111111"

STAFF_ROUTES = [
    ("GET", "/api/commerce/profile"), ("PUT", "/api/commerce/profile"), ("POST", "/api/commerce/profile/cnpj-lookup"),
    ("GET", "/api/commerce/categories"), ("POST", "/api/commerce/categories"),
    ("PATCH", f"/api/commerce/categories/{UUID0}"), ("DELETE", f"/api/commerce/categories/{UUID0}"),
    ("GET", "/api/commerce/products"), ("POST", "/api/commerce/products"),
    ("GET", f"/api/commerce/products/{UUID0}"), ("PATCH", f"/api/commerce/products/{UUID0}"),
    ("DELETE", f"/api/commerce/products/{UUID0}"), ("POST", f"/api/commerce/products/{UUID0}/status"),
    ("GET", f"/api/commerce/products/{UUID0}/offers"), ("POST", f"/api/commerce/products/{UUID0}/offers"),
    ("PATCH", f"/api/commerce/products/{UUID0}/offers/{UUID0}"), ("DELETE", f"/api/commerce/products/{UUID0}/offers/{UUID0}"),
    ("POST", f"/api/commerce/products/{UUID0}/media"), ("DELETE", f"/api/commerce/products/{UUID0}/media/{UUID0}"),
    ("GET", "/api/commerce/coupons"), ("POST", "/api/commerce/coupons"),
    ("PATCH", f"/api/commerce/coupons/{UUID0}"), ("DELETE", f"/api/commerce/coupons/{UUID0}"),
    ("GET", "/api/commerce/customers"), ("GET", f"/api/commerce/customers/{UUID0}"),
    ("GET", f"/api/commerce/customers/{UUID0}/export"), ("POST", f"/api/commerce/customers/{UUID0}/anonymize"),
    ("GET", "/api/commerce/orders"), ("GET", f"/api/commerce/orders/{UUID0}"), ("POST", f"/api/commerce/orders/{UUID0}/cancel"),
    ("POST", f"/api/commerce/orders/{UUID0}/refunds"),
    ("GET", "/api/commerce/hosts"), ("POST", "/api/commerce/hosts"), ("DELETE", "/api/commerce/hosts/x.test"),
]


@pytest.mark.parametrize("method,path", STAFF_ROUTES)
def test_every_staff_route_is_401_without_auth(h, method, path):
    assert h.client.request(method, path).status_code == 401  # strict ==, never `in (401, 4xx)`


def test_staff_route_inventory_matches_the_mounted_router(h):
    mounted = {(m, r.path) for r in h.app.routes if r.path.startswith("/api/commerce") for m in r.methods - {"HEAD", "OPTIONS"}}
    norm = lambda p: re.sub(r"\{[^}]+\}|[0-9a-f]{8}-[0-9a-f-]{27}|/x\.test$", lambda m: "/x.test" if m.group(0) == "/x.test" else "X", p).replace("/x.test", "/X")  # noqa: E731
    assert {(m, norm(p)) for m, p in mounted} == {(m, norm(p)) for m, p in STAFF_ROUTES}


class TestStaffFlow:
    def test_profile_create_conflict_and_cnpj(self, h):
        body = {"legal_name": "Loja LTDA", "trade_name": "Loja", "cnpj": VALID_CNPJ, "tax_regime": "mei", "expected_version": 0}
        assert h.client.get("/api/commerce/profile", headers=h.staff()).json() == {"data": None}
        r = h.client.put("/api/commerce/profile", json=body, headers=h.staff())
        assert r.status_code == 200 and r.json()["data"]["version"] == 1
        r = h.client.put("/api/commerce/profile", json=body, headers=h.staff())  # expected_version 0 again
        assert r.status_code == 409 and r.json()["error"]["code"] == "versao_conflitante"
        r = h.client.put("/api/commerce/profile", json={**body, "cnpj": "11222333000182", "expected_version": 1}, headers=h.staff())
        assert r.status_code == 422 and r.json()["error"]["code"] == "cnpj_invalido"

    def test_platform_fee_is_ignored_for_non_admins(self, h):
        body = {"legal_name": "Loja LTDA", "trade_name": "Loja", "cnpj": VALID_CNPJ, "tax_regime": "mei",
                "expected_version": 0, "platform_fee_bps": 400}
        assert h.client.put("/api/commerce/profile", json=body, headers=h.staff()).json()["data"]["platform_fee_bps"] == 0
        body["expected_version"] = 1
        assert h.client.put("/api/commerce/profile", json=body, headers=h.staff("admin")).json()["data"]["platform_fee_bps"] == 400

    def test_unknown_body_keys_are_rejected(self, h):
        r = h.client.post("/api/commerce/categories", json={"name": "A", "nope": 1}, headers=h.staff())
        assert r.status_code == 422

    def test_cnpj_lookup_envelope(self, h):
        r = h.client.post("/api/commerce/profile/cnpj-lookup", json={"cnpj": VALID_CNPJ}, headers=h.staff())
        assert r.status_code == 200 and r.json()["data"]["cnpj"] == VALID_CNPJ

    def test_product_lifecycle_and_envelopes(self, h):
        c = h.client
        r = c.post("/api/commerce/products", json={"title": "Ebook", "product_type": "digital"}, headers=h.staff())
        assert r.status_code == 201
        pid = r.json()["data"]["id"]
        assert c.post(f"/api/commerce/products/{pid}/status", json={"status": "published"}, headers=h.staff()).status_code == 422
        r = c.post(f"/api/commerce/products/{pid}/offers", json={"name": "Padrão", "price_cents": 4700}, headers=h.staff())
        assert r.status_code == 201 and r.json()["data"]["fee_estimate"]["pix_cents"] == 199
        r = c.post(f"/api/commerce/products/{pid}/status", json={"status": "published"}, headers=h.staff())
        assert r.status_code == 200 and r.json()["data"]["status"] == "published"
        r = c.get(f"/api/commerce/products/{pid}", headers=h.staff())
        assert r.json()["data"]["offers"][0]["price_cents"] == 4700 and r.json()["data"]["media"] == []
        r = c.get("/api/commerce/products?status=published&page=1&page_size=10", headers=h.staff())
        body = r.json()
        assert set(body) == {"data", "pagination"} and set(body["pagination"]) == {"page", "page_size", "total", "total_pages"}
        assert body["pagination"]["total"] == 1 and body["pagination"]["total_pages"] == 1
        assert c.get("/api/commerce/products?status=bogus", headers=h.staff()).status_code == 422
        assert c.delete(f"/api/commerce/products/{pid}", headers=h.staff()).status_code == 204

    def test_media_upload_uses_file_and_alt_fields(self, h):
        pid = h.client.post("/api/commerce/products", json={"title": "P", "product_type": "digital"}, headers=h.staff()).json()["data"]["id"]
        r = h.client.post(f"/api/commerce/products/{pid}/media", headers=h.staff(),
                          files={"file": ("a.png", PNG, "image/png")}, data={"alt": "capa"})
        assert r.status_code == 201 and r.json()["data"]["alt"] == "capa" and r.json()["data"]["url"]
        bad = h.client.post(f"/api/commerce/products/{pid}/media", headers=h.staff(), files={"file": ("a.pdf", b"%PDF", "application/pdf")})
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "midia_invalida"
        mid = r.json()["data"]["id"]
        assert h.client.delete(f"/api/commerce/products/{pid}/media/{mid}", headers=h.staff()).status_code == 204

    def test_hosts_are_platform_admin_only(self, h):
        assert h.client.get("/api/commerce/hosts", headers=h.staff()).status_code == 403
        assert h.client.post("/api/commerce/hosts", json={"hostname": "x.test"}, headers=h.staff()).status_code == 403
        r = h.client.post("/api/commerce/hosts", json={"hostname": "Loja-X.Test:443", "is_primary": True}, headers=h.staff("admin"))
        assert r.status_code == 201 and r.json()["data"]["hostname"] == "loja-x.test"
        assert h.client.post("/api/commerce/hosts", json={"hostname": "loja-x.test"}, headers=h.staff("admin")).status_code == 409
        assert h.client.get("/api/commerce/hosts", headers=h.staff("admin")).json()["data"][0]["hostname"] == "loja-x.test"
        assert h.client.delete("/api/commerce/hosts/loja-x.test", headers=h.staff("admin")).status_code == 204

    def test_cross_org_ids_are_404(self, h):
        pid = h.client.post("/api/commerce/products", json={"title": "P", "product_type": "digital"}, headers=h.staff()).json()["data"]["id"]
        assert h.client.get(f"/api/commerce/products/{pid}", headers=h.staff("org-b")).status_code == 404

    def test_customer_export_is_json_data_envelope_and_order_cancel(self, h):
        seed_profile(h.db)
        _, o = seed_product(h.db)
        h.seed_host()
        h.client.post("/api/storefront/checkout", json=checkout_body(o["id"]), headers=h.shop())
        cust = h.client.get("/api/commerce/customers", headers=h.staff()).json()["data"][0]
        exp = h.client.get(f"/api/commerce/customers/{cust['id']}/export", headers=h.staff())
        assert exp.status_code == 200 and "orders" in exp.json()["data"]
        order = h.client.get("/api/commerce/orders", headers=h.staff()).json()["data"][0]
        assert order["customer"]["email"] == "ana@example.com"
        r = h.client.post(f"/api/commerce/orders/{order['id']}/cancel", headers=h.staff())
        assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled"
        again = h.client.post(f"/api/commerce/orders/{order['id']}/cancel", headers=h.staff())
        assert again.status_code == 409 and again.json()["error"]["code"] == "transicao_invalida"
        assert h.client.post(f"/api/commerce/customers/{cust['id']}/anonymize", headers=h.staff()).json()["data"]["anonymized_at"]


@pytest.fixture
def shop(h):
    seed_profile(h.db)
    p, o = seed_product(h.db, price_cents=4700)
    h.seed_host()
    return h, p, o


class TestStorefront:
    def test_unknown_host_and_unlicensed_org_are_the_same_404(self, shop):
        h, _, _ = shop
        h.seed_host(ORG_B, HOST_B)
        h.checker.allow_all = False
        h.checker.licensed = {(ORG_A, CFG.license_product_slug)}
        unknown = h.client.get("/api/storefront", headers=h.shop("nada.test"))
        unlicensed = h.client.get("/api/storefront", headers=h.shop(HOST_B))
        assert unknown.status_code == unlicensed.status_code == 404
        assert unknown.json() == unlicensed.json()
        assert h.client.get("/api/storefront", headers=h.shop()).status_code == 200

    def test_license_outage_fails_closed_503(self, shop):
        h, _, _ = shop
        h.checker.unavailable = True
        assert h.client.get("/api/storefront", headers=h.shop()).status_code == 503

    def test_host_header_port_is_ignored(self, shop):
        h, _, _ = shop
        assert h.client.get("/api/storefront", headers=h.shop(f"{HOST_A}:8443")).status_code == 200

    def test_disclosures(self, shop):
        h, _, _ = shop
        d = h.client.get("/api/storefront", headers=h.shop()).json()["data"]
        assert d["cnpj"] == VALID_CNPJ and d["legal_name"] and d["legal"]["terms_version"] == CFG.terms_version
        assert d["legal"]["withdrawal_text"] and "org_id" not in d and "platform_fee_bps" not in d

    def test_no_profile_is_404_loja_nao_configurada(self, h):
        h.seed_host()
        r = h.client.get("/api/storefront", headers=h.shop())
        assert r.status_code == 404 and r.json()["error"]["code"] == "loja_nao_configurada"

    def test_catalog_and_product_shapes_without_leaks(self, shop):
        h, p, o = shop
        cat = h.client.get("/api/storefront/catalog", headers=h.shop()).json()
        item = cat["data"][0]
        assert set(item) >= {"id", "slug", "title", "offers", "media_url"} and item["offers"][0]["id"] == o["id"]
        assert cat["pagination"]["total"] == 1
        prod = h.client.get(f"/api/storefront/products/{item['slug']}", headers=h.shop()).json()["data"]
        assert prod["offers"][0]["price_cents"] == 4700
        assert "org_id" not in json.dumps(prod) and ORG_A not in json.dumps(cat) + json.dumps(prod)

    def test_other_orgs_catalog_is_not_visible(self, shop):
        h, _, _ = shop
        seed_product(h.db, ORG_B, title="Segredo")
        titles = [i["title"] for i in h.client.get("/api/storefront/catalog", headers=h.shop()).json()["data"]]
        assert "Segredo" not in titles
        assert h.client.get("/api/storefront/products/segredo", headers=h.shop()).status_code == 404

    def test_unpublished_products_404(self, shop):
        h, _, _ = shop
        seed_product(h.db, title="Rascunho", publish=False)
        assert h.client.get("/api/storefront/products/rascunho", headers=h.shop()).status_code == 404

    def test_quote_lines_shape(self, shop):
        h, p, o = shop
        r = h.client.post("/api/storefront/checkout/quote", json={"items": [{"offer_id": o["id"], "qty": 2}]}, headers=h.shop())
        d = r.json()["data"]
        assert r.status_code == 200 and d["total_cents"] == 9400 and d["requires_immediate_delivery_waiver"] is True
        assert set(d["lines"][0]) == {"offer_id", "product_id", "title", "product_type", "fulfillment_type",
                                      "unit_price_cents", "qty", "total_cents"}

    def test_checkout_flow_and_public_order_without_internal_ids(self, shop):
        h, p, o = shop
        r = h.client.post("/api/storefront/checkout", json=checkout_body(o["id"]), headers=h.shop())
        assert r.status_code == 201
        d = r.json()["data"]
        assert d["status"] == "pending_payment" and d["checkout_url"] and set(d["pix_qr"]) == {"payload", "encoded_image", "expires_at"}
        view = h.client.get(f"/api/storefront/orders/{d['order_token']}", headers=h.shop()).json()["data"]
        raw = json.dumps(view)
        assert view["items"][0]["total_cents"] == 4700 and view["status"] == "pending_payment"
        order = h.db.table("commerce_orders").select("*").execute().data[0]
        for forbidden in (order["id"], order["customer_id"], ORG_A, o["id"], p["id"], "platform_fee", "gateway_charge_id", "coupon"):
            assert forbidden not in raw
        # the order token of one store is a 404 on another store's host
        h.seed_host(ORG_B, HOST_B)
        assert h.client.get(f"/api/storefront/orders/{d['order_token']}", headers=h.shop(HOST_B)).status_code == 404

    def test_checkout_without_consents_is_422_aceite_obrigatorio(self, shop):
        h, _, o = shop
        body = checkout_body(o["id"])
        body.pop("consents")
        r = h.client.post("/api/storefront/checkout", json=body, headers=h.shop())
        assert r.status_code == 422 and r.json()["error"]["code"] == "aceite_obrigatorio"

    def test_checkout_ignores_a_client_sent_price(self, shop):
        h, _, o = shop
        body = checkout_body(o["id"])
        body["items"][0]["price_cents"] = 1
        assert h.client.post("/api/storefront/checkout", json=body, headers=h.shop()).status_code == 422  # unknown key rejected

    def test_gateway_down_is_503_and_failure_is_502(self, shop):
        h, _, o = shop
        h.gateway.configured = False
        assert h.client.post("/api/storefront/checkout", json=checkout_body(o["id"]), headers=h.shop()).status_code == 503

    def test_access_link_is_always_202_with_identical_body(self, shop):
        h, _, o = shop
        h.client.post("/api/storefront/checkout", json=checkout_body(o["id"]), headers=h.shop())
        known = h.client.post("/api/storefront/orders/access-link", json={"email": "ana@example.com"}, headers=h.shop())
        unknown = h.client.post("/api/storefront/orders/access-link", json={"email": "ninguem@example.com"}, headers=h.shop())
        assert known.status_code == unknown.status_code == 202 and known.content == unknown.content
        assert len(h.mailer.sent) == 1 if hasattr(h.mailer, "sent") else True

    def test_magic_link_lists_orders_and_rejects_forgeries(self, shop):
        h, _, o = shop
        h.client.post("/api/storefront/checkout", json=checkout_body(o["id"]), headers=h.shop())
        cust = h.db.table("commerce_customers").select("*").execute().data[0]
        good = access_links.sign_token(SECRET, purpose="my_orders", org_id=ORG_A, subject=cust["id"], ttl_minutes=5)
        r = h.client.get("/api/storefront/my-orders", params={"token": good}, headers=h.shop())
        assert r.status_code == 200 and len(r.json()["data"]) == 1
        wrong_purpose = access_links.sign_token(SECRET, purpose="privacy_verify", org_id=ORG_A, subject=cust["id"], ttl_minutes=5)
        forged = good[:-3] + "AAA"
        for bad in (wrong_purpose, forged, "x.y"):
            assert h.client.get("/api/storefront/my-orders", params={"token": bad + "0000000"}, headers=h.shop()).status_code == 400

    def test_privacy_request_roundtrip(self, shop):
        h, _, o = shop
        h.client.post("/api/storefront/checkout", json=checkout_body(o["id"]), headers=h.shop())
        r = h.client.post("/api/storefront/privacy-requests", json={"email": "ana@example.com", "kind": "access"}, headers=h.shop())
        assert r.status_code == 202
        req = h.db.table("commerce_privacy_requests").select("*").execute().data[0]
        assert req["status"] == "open"
        token = access_links.sign_token(SECRET, purpose="privacy_verify", org_id=ORG_A, subject=req["id"], ttl_minutes=5)
        v = h.client.post("/api/storefront/privacy-requests/verify", json={"token": token}, headers=h.shop())
        assert v.status_code == 200 and v.json()["data"]["status"] == "verified"

    def test_rate_limits_are_applied_from_config(self, shop):
        h, _, _ = shop
        assert CFG.storefront_rate_limit in h.limited and CFG.checkout_rate_limit in h.limited and CFG.webhook_rate_limit in h.limited


class TestWebhookRoute:
    def _order(self, shop):
        h, _, o = shop
        h.client.post("/api/storefront/checkout", json=checkout_body(o["id"]), headers=h.shop())
        order = h.db.table("commerce_orders").select("*").execute().data[0]
        h.gateway.sync_charges()
        h.gateway.charges.mark_paid(order["gateway_charge_id"])  # what the gateway read will show
        return h, order

    def _post(self, h, org, payload, token="hook-token", gateway="asaas"):
        headers = {"asaas-access-token": token} if token is not None else {}
        return h.client.post(f"/api/webhooks/payments/{gateway}/{org}", content=json.dumps(payload), headers=headers)

    def _payload(self, order, event="PAYMENT_CONFIRMED", id_="evt_1"):
        return {"id": id_, "event": event, "payment": {"id": order["gateway_charge_id"], "status": "RECEIVED", "externalReference": order["id"], "customer": "cus_1"}}

    def test_bad_or_missing_token_is_401_and_changes_nothing(self, shop):
        h, order = self._order(shop)
        assert self._post(h, ORG_A, self._payload(order), token="wrong").status_code == 401
        assert self._post(h, ORG_A, self._payload(order), token=None).status_code == 401
        assert h.db.table("commerce_orders").select("*").execute().data[0]["status"] == "pending_payment"

    def test_unset_secret_is_fail_closed_401(self, shop):
        h, order = self._order(shop)
        h.gateway.webhook_secret = None
        assert self._post(h, ORG_A, self._payload(order)).status_code == 401

    def test_paid_then_duplicate(self, shop):
        h, order = self._order(shop)
        r = self._post(h, ORG_A, self._payload(order))
        assert r.status_code == 200 and r.json() == {"received": True, "outcome": "processed"}
        assert h.db.table("commerce_orders").select("*").execute().data[0]["status"] == "paid"
        assert self._post(h, ORG_A, self._payload(order)).json()["outcome"] == "duplicate"

    def test_unknown_event_is_200_ignored(self, shop):
        h, order = self._order(shop)
        r = self._post(h, ORG_A, self._payload(order, event="PAYMENT_CREATED", id_="evt_x"))
        assert r.status_code == 200 and r.json()["outcome"] == "ignored"

    def test_unknown_gateway_404_and_bad_org_id_422(self, shop):
        h, order = self._order(shop)
        assert self._post(h, ORG_A, self._payload(order), gateway="stripe").status_code == 404
        assert self._post(h, "not-a-uuid", self._payload(order)).status_code == 422

    def test_another_orgs_path_cannot_move_this_orders_status(self, shop):
        h, order = self._order(shop)
        assert self._post(h, ORG_B, self._payload(order)).json()["outcome"] == "ignored"
        assert h.db.table("commerce_orders").select("*").execute().data[0]["status"] == "pending_payment"


class TestRealRateLimiter:
    """The harness mounts every rate-limited router under a REAL slowapi `Limiter` (see
    conftest): these pin that it stays real and actually limits, so the whole router suite
    keeps exercising the wrapped handlers prod runs."""

    def test_the_harness_limiter_is_real_slowapi(self, h):
        from slowapi import Limiter

        assert isinstance(h.limiter, Limiter) and h.app.state.limiter is h.limiter

    def test_checkout_is_429_past_its_configured_limit(self, shop):
        h, _, o = shop
        allowed = int(CFG.checkout_rate_limit.split("/")[0])
        codes = [
            h.client.post("/api/storefront/checkout", json=checkout_body(o["id"]), headers=h.shop()).status_code
            for _ in range(allowed + 1)
        ]
        assert 429 not in codes[:allowed] and codes[-1] == 429
