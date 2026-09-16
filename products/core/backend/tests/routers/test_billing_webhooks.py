"""Gateway webhooks end to end: real Stripe signatures (the installed SDK
verifies them), Asaas tokens, idempotency through the inbox, and the
managed/legacy split. Wiring is `dependency_overrides` only.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.integrations.payments import FakePaymentGateway, PaymentGatewayError
from noctusai_lib.integrations.payments.types import FeeBreakdown, GatewaySubscription, Money

from app.main import app
from app.services.billing_context import get_billing_context
from tests.billing_fakes import (
    ASAAS_TOKEN_LIVE,
    ASAAS_TOKEN_TEST,
    NOW,
    ORG_ID,
    PRODUCT_ID,
    STRIPE_WHSEC_LIVE,
    STRIPE_WHSEC_TEST,
    asaas_event,
    legacy_subscription,
    make_ctx,
    managed_subscription,
    seed_catalog,
    sign_stripe,
    stripe_event,
)

SUB = "66666666-6666-6666-6666-666666666666"
STRIPE_URL = "/api/billing/webhook"
ASAAS_URL = "/api/billing/webhooks/asaas"


@pytest.fixture
def env():
    ctx, fakes = make_ctx(ptax={date(2026, 9, 16): Decimal("5.00000")})
    seed_catalog(fakes.db)
    for table in ("licenses", "billing_payments", "cost_ledger", "payment_events", "fx_rates",
                  "billing_events", "webhook_endpoints"):
        fakes.db.set_table_data(table, [])
    fakes.db.set_table_data("subscriptions", [])
    app.dependency_overrides[get_billing_context] = lambda: ctx
    yield ctx, fakes, TestClient(app)
    app.dependency_overrides.clear()


def _sub(fakes):
    return fakes.db.table("subscriptions").select("*").eq("id", SUB).execute().data[0]


def _licenses(fakes):
    return fakes.db.table("licenses").select("*").execute().data


def _post_stripe(client, body, secret=STRIPE_WHSEC_TEST):
    return client.post(STRIPE_URL, content=body, headers=sign_stripe(body, secret))


# ── Stripe signature verification ───────────────────────────────────────


def test_stripe_missing_signature_is_400_and_nothing_is_recorded(env):
    ctx, fakes, client = env
    body = stripe_event("evt_1", "invoice.paid", {})
    resp = client.post(STRIPE_URL, content=body, headers={"content-type": "application/json"})
    assert resp.status_code == 400
    assert fakes.inbox.claims == []


def test_stripe_wrong_secret_is_400(env):
    ctx, fakes, client = env
    body = stripe_event("evt_1", "invoice.paid", {})
    assert _post_stripe(client, body, secret="whsec_attacker").status_code == 400
    assert fakes.inbox.claims == []


def test_stripe_tampered_body_is_400(env):
    ctx, fakes, client = env
    body = stripe_event("evt_1", "invoice.paid", {})
    headers = sign_stripe(body, STRIPE_WHSEC_TEST)
    tampered = body.replace(b"evt_1", b"evt_2")
    assert client.post(STRIPE_URL, content=tampered, headers=headers).status_code == 400


def test_stripe_without_any_configured_secret_is_503():
    ctx, fakes = make_ctx(secrets={})
    app.dependency_overrides[get_billing_context] = lambda: ctx
    try:
        body = stripe_event("evt_1", "invoice.paid", {})
        resp = TestClient(app).post(STRIPE_URL, content=body, headers=sign_stripe(body, "whsec_x"))
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 503


def test_stripe_livemode_must_match_the_secret_that_signed_it(env):
    ctx, fakes, client = env
    body = stripe_event("evt_1", "invoice.paid", {}, livemode=True)
    assert _post_stripe(client, body, secret=STRIPE_WHSEC_TEST).status_code == 400
    assert _post_stripe(client, body, secret=STRIPE_WHSEC_LIVE).status_code == 200


def test_unhandled_stripe_event_is_200_ignored(env):
    ctx, fakes, client = env
    resp = _post_stripe(client, stripe_event("evt_x", "customer.created", {"id": "cus_1"}))
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# ── Stripe lifecycle on a managed subscription ─────────────────────────


def _checkout_completed(event_id="evt_cs"):
    return stripe_event(event_id, "checkout.session.completed", {
        "id": "cs_1", "customer": "cus_gw_1", "subscription": "sub_gw_1",
        "client_reference_id": ORG_ID, "metadata": {"subscription_id": SUB, "org_id": ORG_ID},
    })


def _seed_pending(fakes, **overrides):
    fakes.db.set_table_data("subscriptions", [managed_subscription(
        status="incomplete", gateway_subscription_id=None, current_period_end=None, **overrides)])
    fakes.gateways["stripe"].subscriptions["sub_gw_1"] = GatewaySubscription(
        id_at_gateway="sub_gw_1", customer_id_at_gateway="cus_gw_1", external_reference=ORG_ID,
        status="trialing",
        raw={"id": "sub_gw_1", "status": "trialing", "trial_end": 1790000000,
             "items": {"data": [{"current_period_end": 1790000000}]}},
    )


def test_checkout_completed_starts_the_trial_and_grants_the_license(env):
    ctx, fakes, client = env
    _seed_pending(fakes)
    resp = _post_stripe(client, _checkout_completed())
    assert resp.status_code == 200 and resp.json()["status"] == "processed"
    sub = _sub(fakes)
    assert sub["status"] == "trial"
    assert sub["gateway_subscription_id"] == "sub_gw_1"
    assert sub["trial_ends_at"].startswith("2026-09-21")
    assert [(l["source"], l["subscription_id"], l["product_id"]) for l in _licenses(fakes)] == [
        ("subscription", SUB, PRODUCT_ID)
    ]
    event_rows = fakes.db.table("payment_events").updated_payloads
    assert event_rows[-1]["status"] == "processed" and event_rows[-1]["gateway_mode"] == "test"


def test_duplicate_delivery_is_a_no_op(env):
    ctx, fakes, client = env
    _seed_pending(fakes)
    body = _checkout_completed()
    first = _post_stripe(client, body)
    writes_after_first = (
        len(fakes.db.table("subscriptions").updated_payloads),
        len(fakes.db.table("licenses").inserted_payloads),
    )
    second = _post_stripe(client, body)
    assert first.json()["status"] == "processed"
    assert second.status_code == 200 and second.json()["status"] == "duplicate"
    assert (
        len(fakes.db.table("subscriptions").updated_payloads),
        len(fakes.db.table("licenses").inserted_payloads),
    ) == writes_after_first
    assert fakes.inbox.claims == [("stripe", "evt_cs"), ("stripe", "evt_cs")]


def test_invoice_paid_activates_records_fee_and_books_cost(env):
    ctx, fakes, client = env
    fakes.db.set_table_data("subscriptions", [managed_subscription(status="trial")])
    fakes.gateways["stripe"].script_fee("ch_1", FeeBreakdown(Money(9900), Money(399), Money(9501)))
    body = stripe_event("evt_inv", "invoice.paid", {
        "id": "in_1", "subscription": "sub_gw_1", "charge": "ch_1", "amount_paid": 9900,
        "currency": "brl", "status_transitions": {"paid_at": 1789560000},
        "lines": {"data": [{"period": {"start": 1789560000, "end": 1792152000}}]},
    })
    assert _post_stripe(client, body).json()["status"] == "processed"
    assert _sub(fakes)["status"] == "active"
    payment = fakes.db.table("billing_payments").inserted_payloads[0]
    assert (payment["gross_cents"], payment["fee_cents"], payment["net_cents"]) == (9900, 399, 9501)
    assert payment["currency"] == "BRL" and payment["fee_pending"] is False
    cost = fakes.db.table("cost_ledger").inserted_payloads[0]
    assert (cost["category"], cost["amount_native"], cost["amount_brl"]) == ("payment_fee", "3.99", "3.99")


class _UnsettledFeeGateway(FakePaymentGateway):
    """Stripe has not settled the charge yet: no balance transaction."""

    def get_fee_breakdown(self, charge_id_at_gateway):
        raise PaymentGatewayError("stripe", "balance_transaction not ready", status=404)


def test_invoice_paid_without_settled_fee_is_left_pending(env):
    ctx, fakes, client = env
    fakes.db.set_table_data("subscriptions", [managed_subscription(status="active")])
    body = stripe_event("evt_inv2", "invoice.paid", {
        "id": "in_2", "subscription": "sub_gw_1", "charge": "ch_unknown", "amount_paid": 9900, "currency": "brl",
    })
    fakes.gateways["stripe"] = _UnsettledFeeGateway()
    assert _post_stripe(client, body).json()["status"] == "processed"
    payment = fakes.db.table("billing_payments").inserted_payloads[0]
    assert payment["fee_pending"] is True and payment["gateway_charge_id"] == "ch_unknown"
    assert fakes.db.table("cost_ledger").inserted_payloads == []


def test_invoice_failed_moves_active_to_past_due_but_keeps_access(env):
    ctx, fakes, client = env
    fakes.db.set_table_data("subscriptions", [managed_subscription(status="active")])
    fakes.db.set_table_data("licenses", [{"id": "l1", "org_id": ORG_ID, "product_id": PRODUCT_ID,
                                          "status": "active", "source": "subscription", "subscription_id": SUB}])
    body = stripe_event("evt_fail", "invoice.payment_failed", {
        "id": "in_3", "subscription": "sub_gw_1", "amount_due": 9900, "currency": "brl",
    })
    assert _post_stripe(client, body).json()["status"] == "processed"
    sub = _sub(fakes)
    assert sub["status"] == "past_due" and sub["past_due_since"] == NOW.isoformat()
    assert _licenses(fakes)[0]["status"] == "active"
    assert fakes.db.table("billing_payments").inserted_payloads[0]["status"] == "failed"


def test_subscription_deleted_revokes_only_the_subscription_license(env):
    ctx, fakes, client = env
    fakes.db.set_table_data("subscriptions", [managed_subscription(status="active")])
    fakes.db.set_table_data("licenses", [
        {"id": "l-sub", "org_id": ORG_ID, "product_id": PRODUCT_ID, "status": "active",
         "source": "subscription", "subscription_id": SUB},
        {"id": "l-legacy", "org_id": ORG_ID, "product_id": "other", "status": "active",
         "source": "legacy", "subscription_id": None},
    ])
    body = stripe_event("evt_del", "customer.subscription.deleted",
                        {"id": "sub_gw_1", "status": "canceled", "customer": "cus_gw_1"})
    assert _post_stripe(client, body).json()["status"] == "processed"
    assert _sub(fakes)["status"] == "canceled"
    states = {l["id"]: l["status"] for l in _licenses(fakes)}
    assert states == {"l-sub": "revoked", "l-legacy": "active"}


def test_out_of_order_update_after_cancel_is_ignored_not_500(env):
    ctx, fakes, client = env
    fakes.db.set_table_data("subscriptions", [managed_subscription(status="canceled")])
    body = stripe_event("evt_late", "customer.subscription.updated",
                        {"id": "sub_gw_1", "status": "active", "customer": "cus_gw_1"})
    resp = _post_stripe(client, body)
    assert resp.status_code == 200 and resp.json()["status"] == "ignored"
    assert _sub(fakes)["status"] == "canceled"


def test_processing_failure_releases_the_claim_so_the_retry_runs(env):
    ctx, fakes, client = env
    _seed_pending(fakes)
    del fakes.gateways["stripe"].subscriptions["sub_gw_1"]  # the gateway read will fail
    body = _checkout_completed("evt_retry")
    assert _post_stripe(client, body).status_code == 500
    assert fakes.inbox.releases == [("stripe", "evt_retry")]
    _seed_pending(fakes)
    resp = _post_stripe(client, body)
    assert resp.status_code == 200 and resp.json()["status"] == "processed"


# ── legacy Stripe customers keep the old behaviour ─────────────────────


def test_legacy_subscription_update_goes_through_the_old_handler_only(env):
    ctx, fakes, client = env
    legacy = legacy_subscription(stripe_subscription_id="sub_legacy", status="active")
    fakes.db.set_table_data("subscriptions", [legacy])
    fakes.db.set_table_data("licenses", [{"id": "l-legacy", "org_id": ORG_ID, "product_id": PRODUCT_ID,
                                          "status": "active", "source": "legacy", "subscription_id": None}])
    body = stripe_event("evt_leg", "customer.subscription.updated",
                        {"id": "sub_legacy", "status": "past_due", "customer": "cus_legacy"})
    resp = _post_stripe(client, body)
    assert resp.status_code == 200 and resp.json()["status"] == "processed"
    # Pre-050 behaviour: past_due still maps to 'active' in the legacy handler.
    updates = fakes.db.table("subscriptions").updated_payloads
    assert updates == [{"status": "active"}]
    assert fakes.db.table("licenses").updated_payloads == []


# ── Asaas ───────────────────────────────────────────────────────────────


def _post_asaas(client, body, token=ASAAS_TOKEN_TEST):
    headers = {"content-type": "application/json"}
    if token is not None:
        headers["asaas-access-token"] = token
    return client.post(ASAAS_URL, content=body, headers=headers)


def test_asaas_missing_or_wrong_token_is_401(env):
    ctx, fakes, client = env
    body = asaas_event("evt_a1", "PAYMENT_RECEIVED", payment={"id": "pay_1"})
    assert _post_asaas(client, body, token=None).status_code == 401
    assert _post_asaas(client, body, token="nope-nope-nope-nope").status_code == 401
    assert fakes.inbox.claims == []


def test_asaas_payment_received_activates_with_fee_from_net_value(env):
    ctx, fakes, client = env
    fakes.db.set_table_data("subscriptions", [managed_subscription(
        status="incomplete", gateway="asaas", gateway_subscription_id="sub_as_1", billing_method="pix")])
    body = asaas_event("evt_a2", "PAYMENT_RECEIVED", payment={
        "id": "pay_1", "subscription": "sub_as_1", "status": "RECEIVED", "billingType": "PIX",
        "value": 99.0, "netValue": 97.01, "dueDate": "2026-09-16", "paymentDate": "2026-09-16",
    })
    resp = _post_asaas(client, body)
    assert resp.status_code == 200 and resp.json()["status"] == "processed"
    sub = _sub(fakes)
    assert sub["status"] == "active"
    assert sub["current_period_end"].startswith("2026-10-16")
    payment = fakes.db.table("billing_payments").inserted_payloads[0]
    assert (payment["gross_cents"], payment["fee_cents"], payment["net_cents"]) == (9900, 199, 9701)
    assert payment["billing_method"] == "pix"
    assert _licenses(fakes)[0]["source"] == "subscription"


def test_asaas_live_token_is_accepted_and_tagged_live(env):
    ctx, fakes, client = env
    body = asaas_event("evt_live", "PAYMENT_CREATED", payment={"id": "pay_x"})
    resp = _post_asaas(client, body, token=ASAAS_TOKEN_LIVE)
    assert resp.status_code == 200
    assert fakes.db.table("payment_events").updated_payloads[-1]["gateway_mode"] == "live"


def test_asaas_duplicate_is_a_no_op(env):
    ctx, fakes, client = env
    fakes.db.set_table_data("subscriptions", [managed_subscription(
        status="active", gateway="asaas", gateway_subscription_id="sub_as_1")])
    body = asaas_event("evt_dup", "PAYMENT_OVERDUE", payment={
        "id": "pay_2", "subscription": "sub_as_1", "status": "OVERDUE", "value": 99.0, "dueDate": "2026-09-10"})
    assert _post_asaas(client, body).json()["status"] == "processed"
    assert _post_asaas(client, body).json()["status"] == "duplicate"
    assert _sub(fakes)["status"] == "past_due"
    assert len(fakes.db.table("billing_payments").inserted_payloads) == 1


def test_asaas_subscription_deleted_in_grace_expires(env):
    ctx, fakes, client = env
    fakes.db.set_table_data("subscriptions", [managed_subscription(
        status="grace", gateway="asaas", gateway_subscription_id="sub_as_1")])
    body = asaas_event("evt_sd", "SUBSCRIPTION_DELETED", subscription={"id": "sub_as_1", "status": "INACTIVE"})
    assert _post_asaas(client, body).json()["status"] == "processed"
    assert _sub(fakes)["status"] == "expired"


def test_asaas_event_for_an_unknown_subscription_is_ignored(env):
    ctx, fakes, client = env
    body = asaas_event("evt_other", "PAYMENT_RECEIVED", payment={"id": "pay_z", "subscription": "sub_elsewhere"})
    resp = _post_asaas(client, body)
    assert resp.status_code == 200 and resp.json()["status"] == "ignored"
    assert fakes.db.table("billing_payments").inserted_payloads == []
