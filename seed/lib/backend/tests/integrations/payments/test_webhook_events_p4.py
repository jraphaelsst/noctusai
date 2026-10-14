"""`GatewayEvent.detail` + the P4 kinds (CONTRACT §1.3) and the ADDITIVE rule:
every pre-existing kind mapping is pinned to its old value."""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from noctusai_lib.integrations.payments.webhook_events import make_fake_gateway_event, parse_webhook_event

TOKEN = "asaas-token"
SECRET = "whsec_p4"


def _asaas(event: str, **payment: object):
    body = json.dumps({"event": event, "payment": {"id": "pay_1", "status": "X", "externalReference": "o-1", **payment}}).encode()
    return parse_webhook_event(body, {"asaas-access-token": TOKEN}, gateway="asaas", asaas_webhook_token=TOKEN)


def _stripe(event_type: str, obj: dict, event_id: str = "evt_1"):
    body = json.dumps({"id": event_id, "object": "event", "type": event_type, "data": {"object": obj}}).encode()
    ts = int(time.time())
    sig = hmac.new(SECRET.encode(), f"{ts}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    return parse_webhook_event(body, {"Stripe-Signature": f"t={ts},v1={sig}"}, gateway="stripe", stripe_webhook_secret=SECRET)


# Pre-existing mappings -- MUST NOT change (store / community / core depend on them).
@pytest.mark.parametrize(
    "event,old_kind",
    [
        ("PAYMENT_CONFIRMED", "charge_paid"),
        ("PAYMENT_RECEIVED", "charge_paid"),
        ("PAYMENT_OVERDUE", "charge_failed"),
        ("PAYMENT_REFUNDED", "charge_refunded"),
        ("PAYMENT_CHARGEBACK_REQUESTED", "charge_refunded"),
        ("PAYMENT_CREATED", "ignored"),
        ("PAYMENT_UPDATED", "ignored"),
        ("PAYMENT_RESTORED", "ignored"),
        ("PAYMENT_REFUND_IN_PROGRESS", "ignored"),
        ("PAYMENT_ANTICIPATED", "ignored"),
        ("SOMETHING_NEW", "ignored"),
    ],
)
def test_asaas_pre_existing_kinds_are_unchanged(event: str, old_kind: str) -> None:
    assert _asaas(event).kind == old_kind


@pytest.mark.parametrize(
    "event_type,obj,old_kind",
    [
        ("customer.subscription.created", {"id": "sub_1", "status": "active"}, "subscription_updated"),
        ("customer.subscription.updated", {"id": "sub_1", "status": "past_due"}, "subscription_updated"),
        ("customer.subscription.deleted", {"id": "sub_1", "status": "canceled"}, "subscription_updated"),
        ("invoice.paid", {"id": "in_1", "subscription": "sub_1", "charge": "ch_1"}, "charge_paid"),
        ("invoice.payment_succeeded", {"id": "in_1", "subscription": "sub_1", "charge": "ch_1"}, "charge_paid"),
        ("invoice.payment_failed", {"id": "in_1", "subscription": "sub_1", "charge": "ch_1"}, "charge_failed"),
        ("charge.refunded", {"id": "ch_1", "amount": 100, "amount_refunded": 100}, "charge_refunded"),
        ("charge.refunded", {"id": "ch_1", "amount": 100, "amount_refunded": 40}, "charge_refunded"),
        ("checkout.session.completed", {"id": "cs_1"}, "ignored"),
        ("payment_intent.succeeded", {"id": "pi_1"}, "ignored"),
    ],
)
def test_stripe_pre_existing_kinds_are_unchanged(event_type: str, obj: dict, old_kind: str) -> None:
    assert _stripe(event_type, obj).kind == old_kind


@pytest.mark.parametrize(
    "event,kind,detail",
    [
        ("PAYMENT_CONFIRMED", "charge_paid", "confirmed"),
        ("PAYMENT_RECEIVED", "charge_paid", "received"),
        ("PAYMENT_OVERDUE", "charge_failed", "overdue"),
        ("PAYMENT_REFUNDED", "charge_refunded", None),
        ("PAYMENT_PARTIALLY_REFUNDED", "charge_partially_refunded", "partial"),
        ("PAYMENT_CHARGEBACK_REQUESTED", "charge_refunded", "chargeback_opened"),
        ("PAYMENT_CHARGEBACK_DISPUTE", "charge_dispute", "evidence_submitted"),
        ("PAYMENT_AWAITING_CHARGEBACK_REVERSAL", "charge_dispute", "won"),
        ("PAYMENT_DELETED", "charge_cancelled", None),
    ],
)
def test_asaas_kind_and_detail_table(event: str, kind: str, detail: str | None) -> None:
    got = _asaas(event)
    assert (got.kind, got.detail) == (kind, detail)
    assert got.charge_id_at_gateway == "pay_1"


def test_stripe_charge_refunded_detail_partial_only_when_not_fully_refunded() -> None:
    assert _stripe("charge.refunded", {"id": "ch_1", "amount": 100, "amount_refunded": 40}).detail == "partial"
    assert _stripe("charge.refunded", {"id": "ch_1", "amount": 100, "amount_refunded": 100}).detail is None


def test_stripe_dispute_events() -> None:
    opened = _stripe("charge.dispute.created", {"id": "dp_1", "charge": "ch_1", "status": "needs_response"})
    assert (opened.kind, opened.detail, opened.charge_id_at_gateway) == ("charge_dispute", "chargeback_opened", "ch_1")
    for status in ("won", "lost"):
        closed = _stripe("charge.dispute.closed", {"id": "dp_1", "charge": "ch_1", "status": status})
        assert (closed.kind, closed.detail) == ("charge_dispute", status)
    inquiry = _stripe("charge.dispute.closed", {"id": "dp_1", "charge": "ch_1", "status": "warning_closed"})
    assert inquiry.kind == "ignored" and inquiry.detail is None


def test_fake_event_builder_carries_detail() -> None:
    event = make_fake_gateway_event(kind="charge_dispute", detail="lost")
    assert event.detail == "lost"
    assert make_fake_gateway_event().detail is None
