"""Customer enrichment (D26), privacy, and the idempotent payment webhook."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.commerce import FakeCheckoutGateway, FulfillmentType, customers, make_fulfillment_registry, orders
from noctusai_lib.domain.commerce.checkout import create_checkout
from noctusai_lib.domain.commerce.webhook import DUPLICATE, IGNORED, PROCESSED, handle_event
from noctusai_lib.domain.payments import FakeEventInbox
from noctusai_lib.integrations.payments.webhook_events import make_fake_gateway_event
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import CFG, ORG_A, ORG_B, checkout_body, seed_product, seed_profile


class TestEnrichment:
    def test_payment_overwrites_form_and_is_verified(self, db):
        c = customers.upsert_buyer(db, ORG_A, {"name": "ana s", "email": "a@x.io", "doc": "52998224725"})
        out = customers.enrich_from_payment(db, ORG_A, c["id"], {"name": "Ana Souza", "phone": "(11) 98888-7777"})
        assert out["name"] == "Ana Souza" and out["phone"] == "11988887777"
        assert out["field_sources"]["name"]["source"] == "payment" and out["field_sources"]["name"]["verified"] is True

    def test_later_form_value_never_downgrades_a_payment_field(self, db):
        c = customers.upsert_buyer(db, ORG_A, {"name": "x", "email": "a@x.io"})
        customers.enrich_from_payment(db, ORG_A, c["id"], {"name": "Nome Do Pagamento"})
        again = customers.upsert_buyer(db, ORG_A, {"name": "Digitado Depois", "email": "A@x.io", "phone": "11977776666"})
        assert again["name"] == "Nome Do Pagamento"
        assert again["phone"] == "11977776666" and again["field_sources"]["phone"]["source"] == "form"

    def test_staff_beats_form_but_payment_beats_staff(self):
        row = {"name": "A", "field_sources": {}}
        staff = customers.merge_customer_fields(row, {"name": "Staff"}, "staff", at="t")
        row = {**row, **staff}
        assert customers.merge_customer_fields(row, {"name": "Form"}, "form", at="t") == {}
        pay = customers.merge_customer_fields(row, {"name": "Pay"}, "payment", at="t")
        assert pay["name"] == "Pay"

    def test_gateway_email_owned_by_another_customer_is_not_merged(self, db):
        a = customers.upsert_buyer(db, ORG_A, {"name": "A", "email": "a@x.io"})
        customers.upsert_buyer(db, ORG_A, {"name": "B", "email": "b@x.io"})
        out = customers.enrich_from_payment(db, ORG_A, a["id"], {"email": "b@x.io", "name": "A Real"})
        assert out["email"] == "a@x.io" and out["name"] == "A Real"


class TestPrivacy:
    def test_export_and_anonymize(self, db):
        seed_profile(db)
        _, o = seed_product(db)
        create_checkout(db, ORG_A, CFG, FakeCheckoutGateway(), checkout_body(o["id"]), order_url_for=lambda t: t,
                        ip="1.2.3.4", user_agent="UA")
        cust = db.table("commerce_customers").select("*").execute().data[0]
        exp = customers.export_customer(db, ORG_A, cust["id"])
        assert exp["customer"]["email"] == "ana@example.com" and len(exp["orders"]) == 1
        assert exp["orders"][0]["items"] and exp["orders"][0]["events"] and exp["consents"]
        customers.create_privacy_request(db, ORG_A, cust["id"], __import__("noctusai_lib.domain.commerce", fromlist=["x"]).PrivacyRequestKind.DELETION, None)
        out = customers.anonymize_customer(db, ORG_A, cust["id"])
        assert out["doc"] is None and out["anonymized_at"] and "anonymized.invalid" in out["email"]
        assert all(c["ip"] is None for c in customers.list_consents(db, ORG_A, cust["id"]))
        assert db.table("commerce_orders").select("*").execute().data  # orders survive
        assert customers.list_privacy_requests(db, ORG_A, cust["id"])[0]["status"] == "done"
        assert customers.anonymize_customer(db, ORG_A, cust["id"])["anonymized_at"] == out["anonymized_at"]

    def test_other_org_cannot_touch_the_customer(self, db):
        c = customers.upsert_buyer(db, ORG_A, {"name": "A", "email": "a@x.io"})
        for fn in (customers.anonymize_customer, customers.export_customer, customers.get_customer):
            with pytest.raises(NotFoundError):
                fn(db, ORG_B, c["id"])

    def test_revoke_consent_request_withdraws_marketing_when_verified(self, db):
        from noctusai_lib.domain.commerce import PrivacyRequestKind

        c = customers.upsert_buyer(db, ORG_A, {"name": "A", "email": "a@x.io"})
        r = customers.create_privacy_request(db, ORG_A, c["id"], PrivacyRequestKind.REVOKE_CONSENT, None)
        done = customers.verify_privacy_request(db, ORG_A, r["id"])
        assert done["status"] == "done"
        assert customers.list_consents(db, ORG_A, c["id"])[0]["granted"] is False


def paid_event(order_id, *, event_id="evt1", customer="cus_1", name="PAYMENT_CONFIRMED"):
    return make_fake_gateway_event(
        gateway="asaas", kind="charge_paid", event_id=event_id, external_reference=order_id,
        charge_id_at_gateway="pay_1", raw={"event": name, "payment": {"customer": customer}},
    )


class Rec:
    def __init__(self):
        self.calls = []

    def on_paid(self, order, items):
        self.calls.append(order["id"])


@pytest.fixture
def placed(db):
    seed_profile(db)
    _, o = seed_product(db)
    gw = FakeCheckoutGateway(customers={"cus_1": {"name": "Ana Souza Real", "doc": "52998224725", "email": "ana@example.com"}})
    create_checkout(db, ORG_A, CFG, gw, checkout_body(o["id"]), order_url_for=lambda t: t)
    order = db.table("commerce_orders").select("*").execute().data[0]
    rec = Rec()
    reg = make_fulfillment_registry({FulfillmentType.DIGITAL_DELIVERY: rec})
    return db, order, gw, FakeEventInbox(), reg, rec


class TestWebhook:
    def test_paid_transitions_enriches_and_fulfils(self, placed):
        db, order, gw, inbox, reg, rec = placed
        assert handle_event(db, ORG_A, paid_event(order["id"]), inbox=inbox, gateway=gw, fulfillment=reg) == PROCESSED
        o = orders.get_order(db, ORG_A, order["id"])
        assert o["status"] == "paid" and o["paid_at"]
        cust = db.table("commerce_customers").select("*").execute().data[0]
        assert cust["name"] == "Ana Souza Real" and cust["field_sources"]["name"]["source"] == "payment"
        assert rec.calls == [order["id"]]
        assert [e["to_status"] for e in orders.list_events(db, ORG_A, order["id"])][-1] == "paid"

    def test_duplicate_delivery_never_double_transitions(self, placed):
        db, order, gw, inbox, reg, rec = placed
        ev = paid_event(order["id"])
        assert handle_event(db, ORG_A, ev, inbox=inbox, gateway=gw, fulfillment=reg) == PROCESSED
        assert handle_event(db, ORG_A, ev, inbox=inbox, gateway=gw, fulfillment=reg) == DUPLICATE
        assert len(orders.list_events(db, ORG_A, order["id"])) == 3  # created, pending, paid
        assert rec.calls == [order["id"]]

    def test_second_confirmation_event_is_a_state_noop(self, placed):
        db, order, gw, inbox, reg, rec = placed
        handle_event(db, ORG_A, paid_event(order["id"]), inbox=inbox, gateway=gw, fulfillment=reg)
        handle_event(db, ORG_A, paid_event(order["id"], event_id="evt2", name="PAYMENT_RECEIVED"), inbox=inbox, gateway=gw, fulfillment=reg)
        assert len(orders.list_events(db, ORG_A, order["id"])) == 3

    def test_failure_releases_the_claim_so_the_retry_lands(self, placed):
        db, order, gw, inbox, reg, rec = placed

        class Bad:
            def on_paid(self, o, i):
                raise RuntimeError("down")

        bad_reg = make_fulfillment_registry({FulfillmentType.DIGITAL_DELIVERY: Bad()})
        ev = paid_event(order["id"])
        with pytest.raises(RuntimeError):
            handle_event(db, ORG_A, ev, inbox=inbox, gateway=gw, fulfillment=bad_reg)
        assert inbox.releases
        assert handle_event(db, ORG_A, ev, inbox=inbox, gateway=gw, fulfillment=reg) == PROCESSED

    def test_overdue_expires_then_late_payment_recovers(self, placed):
        db, order, gw, inbox, reg, _ = placed
        over = make_fake_gateway_event(gateway="asaas", kind="charge_failed", event_id="o1", external_reference=order["id"])
        assert handle_event(db, ORG_A, over, inbox=inbox, gateway=gw, fulfillment=reg) == PROCESSED
        assert orders.get_order(db, ORG_A, order["id"])["status"] == "expired"
        handle_event(db, ORG_A, paid_event(order["id"]), inbox=inbox, gateway=gw, fulfillment=reg)
        assert orders.get_order(db, ORG_A, order["id"])["status"] == "paid"

    def test_refund_and_chargeback_only_from_paid(self, placed):
        db, order, gw, inbox, reg, _ = placed
        refund = make_fake_gateway_event(gateway="asaas", kind="charge_refunded", event_id="r0", external_reference=order["id"])
        assert handle_event(db, ORG_A, refund, inbox=inbox, gateway=gw, fulfillment=reg) == IGNORED
        handle_event(db, ORG_A, paid_event(order["id"]), inbox=inbox, gateway=gw, fulfillment=reg)
        cb = make_fake_gateway_event(gateway="asaas", kind="charge_refunded", event_id="r1", external_reference=order["id"],
                                     raw={"event": "PAYMENT_CHARGEBACK_REQUESTED"})
        assert handle_event(db, ORG_A, cb, inbox=inbox, gateway=gw, fulfillment=reg) == PROCESSED
        o = orders.get_order(db, ORG_A, order["id"])
        assert o["status"] == "chargeback" and orders.platform_fee_earned(o) == 0

    def test_late_payment_cannot_resurrect_a_refunded_order(self, placed):
        db, order, gw, inbox, reg, _ = placed
        handle_event(db, ORG_A, paid_event(order["id"]), inbox=inbox, gateway=gw, fulfillment=reg)
        handle_event(db, ORG_A, make_fake_gateway_event(gateway="asaas", kind="charge_refunded", event_id="r", external_reference=order["id"]),
                     inbox=inbox, gateway=gw, fulfillment=reg)
        assert handle_event(db, ORG_A, paid_event(order["id"], event_id="late"), inbox=inbox, gateway=gw, fulfillment=reg) == IGNORED
        assert orders.get_order(db, ORG_A, order["id"])["status"] == "refunded"

    def test_unknown_order_unknown_kind_and_foreign_org_are_ignored(self, placed):
        db, order, gw, inbox, reg, _ = placed
        assert handle_event(db, ORG_A, paid_event("11111111-1111-1111-1111-111111111111", event_id="u"), inbox=inbox, gateway=gw, fulfillment=reg) == IGNORED
        assert handle_event(db, ORG_A, make_fake_gateway_event(gateway="asaas", kind="ignored", event_id="k"), inbox=inbox, gateway=gw, fulfillment=reg) == IGNORED
        assert handle_event(db, ORG_B, paid_event(order["id"], event_id="x"), inbox=inbox, gateway=gw, fulfillment=reg) == IGNORED
        assert orders.get_order(db, ORG_A, order["id"])["status"] == "pending_payment"

    def test_enrichment_failure_never_undoes_the_payment(self, db):
        seed_profile(db)
        _, o = seed_product(db)
        gw = FakeCheckoutGateway(customer_error=RuntimeError("asaas down"))
        create_checkout(db, ORG_A, CFG, gw, checkout_body(o["id"]), order_url_for=lambda t: t)
        order = db.table("commerce_orders").select("*").execute().data[0]
        handle_event(db, ORG_A, paid_event(order["id"]), inbox=FakeEventInbox(), gateway=gw, fulfillment=make_fulfillment_registry())
        assert orders.get_order(db, ORG_A, order["id"])["status"] == "paid"
