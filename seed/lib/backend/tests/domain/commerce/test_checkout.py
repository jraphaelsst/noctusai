"""Quote math, checkout consent rules, split, immediate-delivery waiver, gateway failure."""
from __future__ import annotations

import logging

import pytest

from noctusai_lib.domain.commerce import CommerceError, FakeCheckoutGateway, checkout, coupons, orders, profile
from noctusai_lib.domain.commerce.checkout import build_quote, create_checkout

from .conftest import CFG, ORG_A, ORG_B, USER_ID, VALID_CNPJ, checkout_body, seed_product, seed_profile


def go(db, gateway, body, **kw):
    return create_checkout(db, ORG_A, CFG, gateway, body, order_url_for=lambda t: f"https://x.test/pedido/{t}", **kw)


class TestQuote:
    def test_price_comes_from_the_offer_never_the_request(self, db):
        _, o = seed_product(db, price_cents=4700)
        q = build_quote(db, ORG_A, [{"offer_id": o["id"], "qty": 3}])
        assert (q.subtotal_cents, q.discount_cents, q.total_cents) == (14100, 0, 14100)
        assert q.lines[0]["unit_price_cents"] == 4700

    def test_percent_and_fixed_coupons(self, db):
        _, o = seed_product(db, price_cents=10000)
        coupons.create_coupon(db, ORG_A, {"code": "P10", "kind": "percent", "value": 10})
        coupons.create_coupon(db, ORG_A, {"code": "F2500", "kind": "fixed", "value": 2500})
        assert build_quote(db, ORG_A, [{"offer_id": o["id"], "qty": 1}], "p10").total_cents == 9000
        assert build_quote(db, ORG_A, [{"offer_id": o["id"], "qty": 1}], "F2500").total_cents == 7500

    def test_bad_coupon_reports_error_and_charges_full_price(self, db):
        _, o = seed_product(db, price_cents=1000)
        q = build_quote(db, ORG_A, [{"offer_id": o["id"], "qty": 1}], "NOPE")
        assert q.coupon_error == "nao_encontrado" and q.total_cents == 1000
        assert q.public()["coupon_error"] == "nao_encontrado"

    def test_duplicate_lines_merge(self, db):
        _, o = seed_product(db, price_cents=100)
        q = build_quote(db, ORG_A, [{"offer_id": o["id"], "qty": 2}, {"offer_id": o["id"], "qty": 3}])
        assert len(q.lines) == 1 and q.lines[0]["qty"] == 5

    def test_unsellable_offers_are_refused(self, db):
        _, o = seed_product(db, publish=False)
        with pytest.raises(CommerceError) as exc:
            build_quote(db, ORG_A, [{"offer_id": o["id"], "qty": 1}])
        assert exc.value.code == "oferta_indisponivel"
        _, foreign = seed_product(db, ORG_B)
        with pytest.raises(CommerceError):
            build_quote(db, ORG_A, [{"offer_id": foreign["id"], "qty": 1}])

    def test_waiver_flag_only_for_digital_lines(self, db):
        _, d = seed_product(db, title="D", product_type="digital")
        _, p = seed_product(db, title="P", product_type="physical")
        assert build_quote(db, ORG_A, [{"offer_id": d["id"], "qty": 1}]).requires_immediate_delivery_waiver
        assert not build_quote(db, ORG_A, [{"offer_id": p["id"], "qty": 1}]).requires_immediate_delivery_waiver


class TestConsents:
    def setup_method(self):
        self.gw = FakeCheckoutGateway()

    def test_missing_consents_block_is_aceite_obrigatorio(self, db):
        seed_profile(db)
        _, o = seed_product(db)
        with pytest.raises(CommerceError) as exc:
            go(db, self.gw, checkout_body(o["id"], consents=None))
        assert exc.value.code == "aceite_obrigatorio" and exc.value.status_code == 422
        assert db.table("commerce_orders").select("*").execute().data == []

    def test_stale_terms_version_is_refused(self, db):
        seed_profile(db)
        _, o = seed_product(db)
        body = checkout_body(o["id"])
        body["consents"]["terms_version"] = "0.1"
        with pytest.raises(CommerceError) as exc:
            go(db, self.gw, body)
        assert exc.value.code == "aceite_obrigatorio" and "terms" in exc.value.details["missing"]

    def test_digital_line_needs_the_waiver(self, db):
        seed_profile(db)
        _, o = seed_product(db, product_type="digital")
        body = checkout_body(o["id"])
        body["consents"]["immediate_delivery_waiver"] = False
        with pytest.raises(CommerceError) as exc:
            go(db, self.gw, body)
        assert exc.value.details["missing"] == ["immediate_delivery_waiver"]

    def test_physical_line_does_not_need_the_waiver(self, db):
        seed_profile(db)
        _, o = seed_product(db, product_type="physical")
        body = checkout_body(o["id"])
        body["consents"]["immediate_delivery_waiver"] = False
        assert go(db, self.gw, body)["status"] == "pending_payment"


class TestCreate:
    def test_happy_path_writes_everything(self, db):
        seed_profile(db)
        _, o = seed_product(db, price_cents=4700)
        gw = FakeCheckoutGateway()
        out = go(db, gw, checkout_body(o["id"]))
        assert out["status"] == "pending_payment" and out["order_token"] and out["pix_qr"]["payload"]
        order = db.table("commerce_orders").select("*").execute().data[0]
        assert order["total_cents"] == 4700 and order["gateway_charge_id"] and order["platform_fee_cents"] == 0
        assert len(db.table("commerce_order_items").select("*").execute().data) == 1
        events = orders.list_events(db, ORG_A, order["id"])
        assert [(e["from_status"], e["to_status"]) for e in events] == [(None, "created"), ("created", "pending_payment")]
        kinds = {c["kind"] for c in db.table("commerce_consents").select("*").execute().data}
        assert kinds == {"terms", "privacy", "marketing", "immediate_delivery_waiver"}
        cust = db.table("commerce_customers").select("*").execute().data[0]
        assert cust["email"] == "ana@example.com" and cust["field_sources"]["name"]["source"] == "form"

    def test_client_cannot_influence_the_price(self, db):
        seed_profile(db)
        _, o = seed_product(db, price_cents=4700)
        gw = FakeCheckoutGateway()
        body = checkout_body(o["id"])
        body["items"][0]["price_cents"] = 1  # not a schema field; the service ignores it regardless
        go(db, gw, body)
        req = gw.checkout.calls[-1][1]
        assert req.price.amount_cents == 4700

    def test_no_profile_is_409(self, db):
        _, o = seed_product(db)
        with pytest.raises(CommerceError) as exc:
            go(db, FakeCheckoutGateway(), checkout_body(o["id"]))
        assert exc.value.code == "loja_nao_configurada"

    def test_invalid_coupon_refuses_instead_of_silently_charging_full_price(self, db):
        seed_profile(db)
        _, o = seed_product(db)
        with pytest.raises(CommerceError) as exc:
            go(db, FakeCheckoutGateway(), checkout_body(o["id"], coupon="NOPE"))
        assert exc.value.code == "cupom_invalido"

    def test_coupon_use_is_counted_and_released_on_gateway_failure(self, db):
        from noctusai_lib.integrations.payments.errors import PaymentGatewayError

        seed_profile(db)
        _, o = seed_product(db, price_cents=10000)
        coupons.create_coupon(db, ORG_A, {"code": "ONE", "kind": "percent", "value": 10, "max_uses": 1})

        class Boom(FakeCheckoutGateway):
            def hosted_checkout(self, org_id):
                class H:
                    def create_checkout(self, req):
                        raise PaymentGatewayError("asaas", "refused", status=400, retryable=False)
                return H()

        with pytest.raises(CommerceError) as exc:
            go(db, Boom(), checkout_body(o["id"], coupon="ONE"))
        assert exc.value.code == "pagamento_falhou" and exc.value.status_code == 502
        assert db.table("commerce_coupons").select("*").execute().data[0]["uses_count"] == 0
        order = db.table("commerce_orders").select("*").execute().data[0]
        assert order["status"] == "failed"
        go(db, FakeCheckoutGateway(), checkout_body(o["id"], coupon="ONE"))
        assert db.table("commerce_coupons").select("*").execute().data[0]["uses_count"] == 1
        with pytest.raises(CommerceError):  # cap reached
            go(db, FakeCheckoutGateway(), checkout_body(o["id"], coupon="ONE"))

    def test_unconfigured_gateway_is_503_and_leaves_no_order(self, db):
        seed_profile(db)
        _, o = seed_product(db)
        with pytest.raises(CommerceError) as exc:
            go(db, FakeCheckoutGateway(configured=False), checkout_body(o["id"]))
        assert exc.value.status_code == 503
        assert db.table("commerce_orders").select("*").execute().data == []

    @pytest.mark.parametrize("doc", ["123", "11111111111", "52998224726"])
    def test_buyer_document_must_be_valid(self, db, doc):
        seed_profile(db)
        _, o = seed_product(db)
        body = checkout_body(o["id"])
        body["buyer"]["doc"] = doc
        with pytest.raises(CommerceError) as exc:
            go(db, FakeCheckoutGateway(), body)
        assert exc.value.code == "documento_invalido"

    def test_cnpj_buyer_is_accepted(self, db):
        seed_profile(db)
        _, o = seed_product(db)
        body = checkout_body(o["id"])
        body["buyer"]["doc"] = VALID_CNPJ
        assert go(db, FakeCheckoutGateway(), body)["status"] == "pending_payment"


class TestPlatformSplit:
    def _setup(self, db, bps):
        seed_profile(db)
        if bps:
            profile.put_profile(db, ORG_A, USER_ID, {
                "legal_name": "L", "trade_name": "L", "cnpj": VALID_CNPJ, "tax_regime": "mei",
                "platform_fee_bps": bps}, expected_version=1, is_platform_admin=True)
        return seed_product(db, price_cents=10000)[1]

    def test_split_only_with_bps_and_wallet(self, db):
        o = self._setup(db, 300)
        gw = FakeCheckoutGateway(wallet_id="wal-noc")
        go(db, gw, checkout_body(o["id"]))
        req = gw.checkout.calls[-1][1]
        assert (req.split_wallet_id, req.split_percent) == ("wal-noc", 3.0)
        assert db.table("commerce_orders").select("*").execute().data[0]["platform_fee_cents"] == 300

    def test_no_bps_no_split(self, db):
        o = self._setup(db, 0)
        gw = FakeCheckoutGateway(wallet_id="wal-noc")
        go(db, gw, checkout_body(o["id"]))
        assert gw.checkout.calls[-1][1].split_wallet_id is None

    def test_no_wallet_no_split_logged_once(self, db, caplog):
        checkout._NO_WALLET_LOGGED.discard(ORG_A)
        o = self._setup(db, 300)
        gw = FakeCheckoutGateway(wallet_id=None)
        with caplog.at_level(logging.INFO, logger=checkout.logger.name):
            go(db, gw, checkout_body(o["id"]))
            go(db, gw, checkout_body(o["id"]))
        assert gw.checkout.calls[-1][1].split_wallet_id is None
        assert db.table("commerce_orders").select("*").execute().data[0]["platform_fee_cents"] == 0
        assert sum("no platform wallet" in r.message for r in caplog.records) == 1
