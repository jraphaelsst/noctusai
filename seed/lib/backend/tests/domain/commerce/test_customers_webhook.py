"""Customer enrichment (D26), privacy, and the idempotent payment webhook."""
from __future__ import annotations

from dataclasses import replace

import pytest

from noctusai_lib.domain.commerce import FakeCheckoutGateway, FulfillmentType, MoneyDeps, customers, make_fulfillment_registry, orders
from noctusai_lib.domain.commerce.checkout import create_checkout
from noctusai_lib.domain.commerce.webhook import DUPLICATE, IGNORED, PROCESSED, handle_event
from noctusai_lib.domain.payments import FakeEventInbox
from noctusai_lib.integrations.payments.webhook_events import make_fake_gateway_event
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import CFG, ORG_A, ORG_B, checkout_body, run, seed_product, seed_profile


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


def paid_event(order, *, event_id="evt1", name="PAYMENT_CONFIRMED", detail="confirmed"):
    return make_fake_gateway_event(
        gateway="asaas", kind="charge_paid", event_id=event_id, external_reference=order["id"],
        charge_id_at_gateway=order["gateway_charge_id"], detail=detail, raw={"event": name},
    )


def he(db, org, event, inbox, gw, reg):
    """Drive the (async) webhook handler with the money deps the router would build."""
    return run(handle_event(db, org, event, inbox=inbox, deps=MoneyDeps(cfg=CFG, gateway=gw, fulfillment=reg)))


class Rec:
    def __init__(self):
        self.calls = []

    def on_paid(self, order, items):
        self.calls.append(order["id"])


def place_order(db, gw, **body):
    """Checkout through the organ, mirror the charge into the fake gateway, and give it a payer record."""
    seed_profile(db)
    _, o = seed_product(db)
    create_checkout(db, ORG_A, CFG, gw, checkout_body(o["id"], **body), order_url_for=lambda t: t)
    gw.sync_charges()
    order = db.table("commerce_orders").select("*").execute().data[0]
    return order


@pytest.fixture
def placed(db):
    gw = FakeCheckoutGateway()
    order = place_order(db, gw)
    session = next(iter(gw.checkout.sessions.values()))
    gw.customers[session.customer_id_at_gateway] = {"name": "Ana Souza Real", "doc": "52998224725", "email": "ana@example.com"}
    gw.charges.charges[order["gateway_charge_id"]] = replace(
        gw.charges.charges[order["gateway_charge_id"]], raw={"customer": session.customer_id_at_gateway}
    )
    gw.charges.mark_paid(order["gateway_charge_id"])
    rec = Rec()
    reg = make_fulfillment_registry({FulfillmentType.DIGITAL_DELIVERY: rec})
    return db, order, gw, FakeEventInbox(), reg, rec


class TestWebhook:
    def test_paid_transitions_enriches_and_fulfils(self, placed):
        db, order, gw, inbox, reg, rec = placed
        assert he(db, ORG_A, paid_event(order), inbox, gw, reg) == PROCESSED
        o = orders.get_order(db, ORG_A, order["id"])
        assert o["status"] == "paid" and o["paid_at"]
        cust = db.table("commerce_customers").select("*").execute().data[0]
        assert cust["name"] == "Ana Souza Real" and cust["field_sources"]["name"]["source"] == "payment"
        assert rec.calls == [order["id"]]
        assert [e["to_status"] for e in orders.list_events(db, ORG_A, order["id"])][-1] == "paid"

    def test_duplicate_delivery_never_double_transitions(self, placed):
        db, order, gw, inbox, reg, rec = placed
        ev = paid_event(order)
        assert he(db, ORG_A, ev, inbox, gw, reg) == PROCESSED
        assert he(db, ORG_A, ev, inbox, gw, reg) == DUPLICATE
        assert len(orders.list_events(db, ORG_A, order["id"])) == 3  # created, pending, paid
        assert rec.calls == [order["id"]]

    def test_second_confirmation_event_is_a_state_noop(self, placed):
        db, order, gw, inbox, reg, rec = placed
        he(db, ORG_A, paid_event(order), inbox, gw, reg)
        he(db, ORG_A, paid_event(order, event_id="evt2", name="PAYMENT_RECEIVED"), inbox, gw, reg)
        assert len(orders.list_events(db, ORG_A, order["id"])) == 3

    def test_failure_releases_the_claim_so_the_retry_lands(self, placed):
        db, order, gw, inbox, reg, rec = placed

        class Bad:
            def on_paid(self, o, i):
                raise RuntimeError("down")

        bad_reg = make_fulfillment_registry({FulfillmentType.DIGITAL_DELIVERY: Bad()})
        ev = paid_event(order)
        with pytest.raises(RuntimeError):
            he(db, ORG_A, ev, inbox, gw, bad_reg)
        assert inbox.releases
        assert he(db, ORG_A, ev, inbox, gw, reg) == PROCESSED

    def test_overdue_expires_then_late_payment_recovers(self, placed):
        db, order, gw, inbox, reg, _ = placed
        over = make_fake_gateway_event(gateway="asaas", kind="charge_failed", event_id="o1", external_reference=order["id"])
        assert he(db, ORG_A, over, inbox, gw, reg) == PROCESSED
        assert orders.get_order(db, ORG_A, order["id"])["status"] == "expired"
        he(db, ORG_A, paid_event(order), inbox, gw, reg)
        assert orders.get_order(db, ORG_A, order["id"])["status"] == "paid"

    def test_refund_and_dispute_only_from_a_paid_order(self, placed):
        db, order, gw, inbox, reg, _ = placed
        refund = make_fake_gateway_event(gateway="asaas", kind="charge_refunded", event_id="r0", external_reference=order["id"],
                                         charge_id_at_gateway=order["gateway_charge_id"])
        assert he(db, ORG_A, refund, inbox, gw, reg) == IGNORED  # never paid
        he(db, ORG_A, paid_event(order), inbox, gw, reg)
        gw.charges.open_dispute(order["gateway_charge_id"])
        cb = make_fake_gateway_event(gateway="asaas", kind="charge_refunded", event_id="r1", external_reference=order["id"],
                                     charge_id_at_gateway=order["gateway_charge_id"], detail="chargeback_opened")
        assert he(db, ORG_A, cb, inbox, gw, reg) == PROCESSED
        o = orders.get_order(db, ORG_A, order["id"])
        assert o["status"] == "disputed" and orders.platform_fee_earned(o) == 0  # opened, NOT yet a chargeback

    def test_late_payment_cannot_resurrect_a_refunded_order(self, placed):
        db, order, gw, inbox, reg, _ = placed
        he(db, ORG_A, paid_event(order), inbox, gw, reg)
        gw.charges.refund_charge(order["gateway_charge_id"], amount=None, description="x")
        refund = make_fake_gateway_event(gateway="asaas", kind="charge_refunded", event_id="r", external_reference=order["id"],
                                         charge_id_at_gateway=order["gateway_charge_id"])
        he(db, ORG_A, refund, inbox, gw, reg)
        assert orders.get_order(db, ORG_A, order["id"])["status"] == "refunded"
        assert he(db, ORG_A, paid_event(order, event_id="late"), inbox, gw, reg) == IGNORED
        assert orders.get_order(db, ORG_A, order["id"])["status"] == "refunded"

    def test_unknown_order_unknown_kind_and_foreign_org_are_ignored(self, placed):
        db, order, gw, inbox, reg, _ = placed
        assert he(db, ORG_A, paid_event({**order, "id": "11111111-1111-1111-1111-111111111111", "gateway_charge_id": "pay_nope"}, event_id="u"), inbox, gw, reg) == IGNORED
        assert he(db, ORG_A, make_fake_gateway_event(gateway="asaas", kind="ignored", event_id="k"), inbox, gw, reg) == IGNORED
        assert he(db, ORG_B, paid_event(order, event_id="x"), inbox, gw, reg) == IGNORED
        assert orders.get_order(db, ORG_A, order["id"])["status"] == "pending_payment"

    def test_enrichment_failure_never_undoes_the_payment(self, db):
        gw = FakeCheckoutGateway(customer_error=RuntimeError("asaas down"))
        order = place_order(db, gw)
        gw.charges.charges[order["gateway_charge_id"]] = replace(gw.charges.charges[order["gateway_charge_id"]], raw={"customer": "cus_x"})
        gw.charges.mark_paid(order["gateway_charge_id"])
        he(db, ORG_A, paid_event(order), FakeEventInbox(), gw, make_fulfillment_registry())
        assert orders.get_order(db, ORG_A, order["id"])["status"] == "paid"


class TestFiscalRetention:
    """D30: paid orders keep buyer doc+name (tax record) through anonymize, until purged."""

    @staticmethod
    def _paid(placed):
        db, order, gw, inbox, reg, _ = placed
        he(db, ORG_A, paid_event(order), inbox, gw, reg)
        return db, order, gw, inbox, reg

    def test_snapshot_on_paid_uses_payment_values_and_sets_window(self, placed):
        db, order, *_ = self._paid(placed)
        o = orders.get_order(db, ORG_A, order["id"])
        assert o["buyer_name"] == "Ana Souza Real" and o["buyer_doc"]
        assert o["fiscal_retain_until"] == f"{int(o['paid_at'][:4]) + 6}-01-01"

    def test_snapshot_is_idempotent_and_never_overwritten(self, placed):
        from noctusai_lib.domain.commerce.fiscal_retention import snapshot_fiscal_identity

        db, order, gw, inbox, reg = self._paid(placed)
        first_ = orders.get_order(db, ORG_A, order["id"])
        cust = db.table("commerce_customers").select("*").execute().data[0]
        db.table("commerce_customers").update({"name": "Outro Nome", "doc": "11111111111"}).eq("id", cust["id"]).execute()
        snapshot_fiscal_identity(db, ORG_A, first_)
        he(db, ORG_A, paid_event(order, event_id="evt2", name="PAYMENT_RECEIVED"), inbox, gw, reg)
        again = orders.get_order(db, ORG_A, order["id"])
        assert (again["buyer_doc"], again["buyer_name"], again["fiscal_retain_until"]) == (
            first_["buyer_doc"], first_["buyer_name"], first_["fiscal_retain_until"])

    def test_anonymize_keeps_paid_scrubs_non_paid(self, placed):
        db, order, *_ = self._paid(placed)
        cust = db.table("commerce_customers").select("*").execute().data[0]
        stray = db.table("commerce_orders").select("*").eq("id", order["id"]).execute().data[0]
        stray = {**stray, "id": "22222222-2222-4222-8222-222222222222", "token": "stray-token", "status": "expired"}
        db.table("commerce_orders").insert(stray).execute()
        customers.anonymize_customer(db, ORG_A, cust["id"])
        kept = orders.get_order(db, ORG_A, order["id"])
        assert kept["buyer_name"] == "Ana Souza Real" and kept["buyer_doc"] and kept["fiscal_retain_until"]
        gone = orders.get_order(db, ORG_A, stray["id"])
        assert gone["buyer_doc"] is None and gone["buyer_name"] is None and gone["fiscal_retain_until"] is None

    def test_purge_boundary(self, placed):
        from datetime import date, timedelta

        db, order, *_ = self._paid(placed)
        until = date.fromisoformat(orders.get_order(db, ORG_A, order["id"])["fiscal_retain_until"])
        assert customers.__name__  # keep import local
        from noctusai_lib.domain.commerce import purge_expired_fiscal_retention as purge

        assert purge(db, ORG_A, today=until - timedelta(days=1)) == 0
        assert orders.get_order(db, ORG_A, order["id"])["buyer_doc"]
        assert purge(db, ORG_B, today=until) == 0  # other org untouched
        assert purge(db, ORG_A, today=until) == 1
        o = orders.get_order(db, ORG_A, order["id"])
        assert o["buyer_doc"] is None and o["buyer_name"] is None and o["fiscal_retain_until"] is None
        assert purge(db, None, today=until) == 0

    def test_export_includes_retained_fields(self, placed):
        db, order, *_ = self._paid(placed)
        cust = db.table("commerce_customers").select("*").execute().data[0]
        exp = customers.export_customer(db, ORG_A, cust["id"])
        o = exp["orders"][0]
        assert o["buyer_name"] == "Ana Souza Real" and o["buyer_doc"] and o["fiscal_retain_until"]
