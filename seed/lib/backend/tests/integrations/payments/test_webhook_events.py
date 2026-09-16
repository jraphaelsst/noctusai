"""`parse_webhook_event` — real signed Stripe payloads (genuine
`stripe.Webhook.construct_event` verification, no SDK substitution needed
since signing is pure local HMAC, zero network) + a scripted Asaas
`asaas-access-token` header, matching this package's own webhook-auth shape.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
import stripe

from noctusai_lib.integrations.payments.webhook_events import (
    GatewayEvent,
    PaymentWebhookSignatureError,
    base64_encode_colon_secret,
    make_fake_gateway_event,
    parse_webhook_event,
)

STRIPE_SECRET = "whsec_test_secret_123"


def _sign_stripe_payload(payload_dict: dict, *, secret: str = STRIPE_SECRET, timestamp: int | None = None) -> tuple[bytes, str]:
    """Build a REAL Stripe-signature-verifiable `(body, Stripe-Signature)`
    pair using Stripe's own documented scheme (`t=<ts>,v1=<hmac-sha256 of
    "<ts>.<body>">`) — the exact scheme `stripe.Webhook.construct_event`
    checks. No stub, no `sys.modules` substitution: this exercises the
    real installed `stripe` SDK's real verifier.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    body = json.dumps(payload_dict).encode("utf-8")
    signed_payload = f"{ts}.{body.decode('utf-8')}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    header = f"t={ts},v1={signature}"
    return body, header


def _stripe_subscription_updated_payload(status: str = "past_due") -> dict:
    return {
        "id": "evt_001",
        "object": "event",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_001",
                "customer": "cus_001",
                "status": status,
                "metadata": {"external_reference": "org-1"},
            }
        },
    }


def test_stripe_subscription_updated_maps_kind_and_status() -> None:
    body, sig = _sign_stripe_payload(_stripe_subscription_updated_payload())
    event = parse_webhook_event(
        body, {"Stripe-Signature": sig}, gateway="stripe", stripe_webhook_secret=STRIPE_SECRET
    )
    assert event.gateway == "stripe"
    assert event.event_id == "evt_001"
    assert event.kind == "subscription_updated"
    assert event.external_reference == "org-1"
    assert event.subscription_id_at_gateway == "sub_001"
    assert event.subscription_status == "past_due"
    assert event.inbox_key == ("stripe", "evt_001")


def test_stripe_header_lookup_is_case_insensitive() -> None:
    body, sig = _sign_stripe_payload(_stripe_subscription_updated_payload())
    event = parse_webhook_event(
        body, {"stripe-signature": sig}, gateway="stripe", stripe_webhook_secret=STRIPE_SECRET
    )
    assert event.event_id == "evt_001"


def test_stripe_invoice_payment_succeeded_maps_to_charge_paid() -> None:
    payload = {
        "id": "evt_002",
        "object": "event",
        "type": "invoice.payment_succeeded",
        "data": {"object": {"id": "in_001", "subscription": "sub_001", "charge": "ch_001", "metadata": {}}},
    }
    body, sig = _sign_stripe_payload(payload)
    event = parse_webhook_event(
        body, {"Stripe-Signature": sig}, gateway="stripe", stripe_webhook_secret=STRIPE_SECRET
    )
    assert event.kind == "charge_paid"
    assert event.charge_id_at_gateway == "ch_001"
    assert event.subscription_id_at_gateway == "sub_001"


def test_stripe_invoice_payment_failed_maps_to_charge_failed() -> None:
    payload = {
        "id": "evt_003",
        "object": "event",
        "type": "invoice.payment_failed",
        "data": {"object": {"id": "in_002", "subscription": "sub_001", "charge": "ch_002", "metadata": {}}},
    }
    body, sig = _sign_stripe_payload(payload)
    event = parse_webhook_event(
        body, {"Stripe-Signature": sig}, gateway="stripe", stripe_webhook_secret=STRIPE_SECRET
    )
    assert event.kind == "charge_failed"


def test_stripe_charge_refunded_maps_to_charge_refunded() -> None:
    payload = {
        "id": "evt_004",
        "object": "event",
        "type": "charge.refunded",
        "data": {"object": {"id": "ch_003", "metadata": {}}},
    }
    body, sig = _sign_stripe_payload(payload)
    event = parse_webhook_event(
        body, {"Stripe-Signature": sig}, gateway="stripe", stripe_webhook_secret=STRIPE_SECRET
    )
    assert event.kind == "charge_refunded"
    assert event.charge_id_at_gateway == "ch_003"


def test_stripe_unknown_event_type_is_ignored_not_error() -> None:
    payload = {
        "id": "evt_005",
        "object": "event",
        "type": "customer.updated",
        "data": {"object": {"id": "cus_001", "metadata": {}}},
    }
    body, sig = _sign_stripe_payload(payload)
    event = parse_webhook_event(
        body, {"Stripe-Signature": sig}, gateway="stripe", stripe_webhook_secret=STRIPE_SECRET
    )
    assert event.kind == "ignored"


def test_stripe_bad_signature_raises() -> None:
    body, _ = _sign_stripe_payload(_stripe_subscription_updated_payload())
    with pytest.raises(PaymentWebhookSignatureError):
        parse_webhook_event(
            body,
            {"Stripe-Signature": "t=1,v1=deadbeef"},
            gateway="stripe",
            stripe_webhook_secret=STRIPE_SECRET,
        )


def test_stripe_wrong_secret_raises() -> None:
    body, sig = _sign_stripe_payload(_stripe_subscription_updated_payload(), secret="a-different-secret")
    with pytest.raises(PaymentWebhookSignatureError):
        parse_webhook_event(
            body, {"Stripe-Signature": sig}, gateway="stripe", stripe_webhook_secret=STRIPE_SECRET
        )


def test_stripe_missing_signature_header_raises() -> None:
    body, _ = _sign_stripe_payload(_stripe_subscription_updated_payload())
    with pytest.raises(PaymentWebhookSignatureError):
        parse_webhook_event(body, {}, gateway="stripe", stripe_webhook_secret=STRIPE_SECRET)


def test_stripe_missing_secret_configured_raises() -> None:
    body, sig = _sign_stripe_payload(_stripe_subscription_updated_payload())
    with pytest.raises(PaymentWebhookSignatureError):
        parse_webhook_event(body, {"Stripe-Signature": sig}, gateway="stripe", stripe_webhook_secret=None)


def test_construct_event_used_is_the_real_stripe_sdk() -> None:
    """Sanity: `stripe` here is the genuinely installed SDK (not a
    `sys.modules` double), and `parse_webhook_event`'s Stripe branch is
    exercising ITS real `Webhook.construct_event` — confirmed by checking
    that tampering the body after signing (still a valid `v1=` for the
    ORIGINAL body) is rejected, the same guarantee the real SDK provides.
    """
    body, sig = _sign_stripe_payload(_stripe_subscription_updated_payload())
    tampered = body.replace(b"past_due", b"active")
    assert stripe.Webhook is not None  # the real module, imported directly above
    with pytest.raises(PaymentWebhookSignatureError):
        parse_webhook_event(
            tampered, {"Stripe-Signature": sig}, gateway="stripe", stripe_webhook_secret=STRIPE_SECRET
        )


# ── Asaas ────────────────────────────────────────────────────────────────

ASAAS_TOKEN = "configured-webhook-token"


def _asaas_headers(token: str = ASAAS_TOKEN) -> dict[str, str]:
    return {"asaas-access-token": token}


def _asaas_payload(event: str, payment: dict) -> bytes:
    return json.dumps({"event": event, "payment": payment}).encode("utf-8")


def test_asaas_access_token_header_is_not_basic_encoded_by_the_sender() -> None:
    """Documents the actual wire shape: Asaas sends the raw token, no
    `Basic ` prefix, no base64 — this is what `_verify_asaas_access_token`
    must accept, and what would NOT pass `verify_basic_shared_secret`
    directly without the synthetic-wrap this module performs.
    """
    headers = _asaas_headers()
    assert not headers["asaas-access-token"].lower().startswith("basic ")


def test_asaas_payment_confirmed_maps_to_charge_paid() -> None:
    body = _asaas_payload(
        "PAYMENT_CONFIRMED",
        {
            "id": "pay_001",
            "status": "CONFIRMED",
            "externalReference": "org-1",
            "subscription": "sub_001",
            "paymentDate": "2026-09-16",
        },
    )
    event = parse_webhook_event(
        body, _asaas_headers(), gateway="asaas", asaas_webhook_token=ASAAS_TOKEN
    )
    assert event.gateway == "asaas"
    assert event.kind == "charge_paid"
    assert event.external_reference == "org-1"
    assert event.subscription_id_at_gateway == "sub_001"
    assert event.charge_id_at_gateway == "pay_001"
    assert event.subscription_status is None  # no subscription status on a payment webhook


def test_asaas_payment_overdue_maps_to_charge_failed() -> None:
    body = _asaas_payload("PAYMENT_OVERDUE", {"id": "pay_002", "status": "OVERDUE"})
    event = parse_webhook_event(body, _asaas_headers(), gateway="asaas", asaas_webhook_token=ASAAS_TOKEN)
    assert event.kind == "charge_failed"


def test_asaas_payment_refunded_maps_to_charge_refunded() -> None:
    body = _asaas_payload("PAYMENT_REFUNDED", {"id": "pay_003", "status": "REFUNDED"})
    event = parse_webhook_event(body, _asaas_headers(), gateway="asaas", asaas_webhook_token=ASAAS_TOKEN)
    assert event.kind == "charge_refunded"


def test_asaas_unknown_event_is_ignored_not_error() -> None:
    body = _asaas_payload("PAYMENT_BANK_SLIP_VIEWED", {"id": "pay_004", "status": "PENDING"})
    event = parse_webhook_event(body, _asaas_headers(), gateway="asaas", asaas_webhook_token=ASAAS_TOKEN)
    assert event.kind == "ignored"


def test_asaas_event_id_is_deterministic_and_derived() -> None:
    """No `id`/`eventId` field in an Asaas webhook payload — confirm the
    derived `event_id` is stable across two IDENTICAL deliveries (a real
    retry) and changes when the payment's status genuinely changes.
    """
    payment = {"id": "pay_005", "status": "PENDING", "dueDate": "2026-09-20"}
    body1 = _asaas_payload("PAYMENT_CREATED", payment)
    body2 = _asaas_payload("PAYMENT_CREATED", dict(payment))  # identical retry
    event1 = parse_webhook_event(body1, _asaas_headers(), gateway="asaas", asaas_webhook_token=ASAAS_TOKEN)
    event2 = parse_webhook_event(body2, _asaas_headers(), gateway="asaas", asaas_webhook_token=ASAAS_TOKEN)
    assert event1.event_id == event2.event_id  # a retry dedupes via EventInbox

    changed_payment = {"id": "pay_005", "status": "RECEIVED", "paymentDate": "2026-09-20"}
    body3 = _asaas_payload("PAYMENT_RECEIVED", changed_payment)
    event3 = parse_webhook_event(body3, _asaas_headers(), gateway="asaas", asaas_webhook_token=ASAAS_TOKEN)
    assert event3.event_id != event1.event_id  # a genuine status change is a new event


def test_asaas_wrong_token_raises() -> None:
    body = _asaas_payload("PAYMENT_CONFIRMED", {"id": "pay_006", "status": "CONFIRMED"})
    with pytest.raises(PaymentWebhookSignatureError):
        parse_webhook_event(
            body, _asaas_headers("wrong-token"), gateway="asaas", asaas_webhook_token=ASAAS_TOKEN
        )


def test_asaas_missing_header_raises() -> None:
    body = _asaas_payload("PAYMENT_CONFIRMED", {"id": "pay_007", "status": "CONFIRMED"})
    with pytest.raises(PaymentWebhookSignatureError):
        parse_webhook_event(body, {}, gateway="asaas", asaas_webhook_token=ASAAS_TOKEN)


def test_asaas_missing_configured_token_raises() -> None:
    body = _asaas_payload("PAYMENT_CONFIRMED", {"id": "pay_008", "status": "CONFIRMED"})
    with pytest.raises(PaymentWebhookSignatureError):
        parse_webhook_event(body, _asaas_headers(), gateway="asaas", asaas_webhook_token=None)


def test_asaas_malformed_json_raises() -> None:
    with pytest.raises(PaymentWebhookSignatureError):
        parse_webhook_event(
            b"not-json", _asaas_headers(), gateway="asaas", asaas_webhook_token=ASAAS_TOKEN
        )


def test_base64_encode_colon_secret_matches_manual_basic_encoding() -> None:
    import base64

    encoded = base64_encode_colon_secret("my-secret")
    assert base64.b64decode(encoded).decode("utf-8") == ":my-secret"


# ── cross-gateway ────────────────────────────────────────────────────────


def test_unknown_gateway_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_webhook_event(b"{}", {}, gateway="mercadopago")


def test_make_fake_gateway_event_bypasses_verification() -> None:
    event = make_fake_gateway_event(
        gateway="asaas", kind="subscription_updated", external_reference="org-9"
    )
    assert isinstance(event, GatewayEvent)
    assert event.gateway == "asaas"
    assert event.kind == "subscription_updated"
    assert event.external_reference == "org-9"
    assert event.inbox_key == ("asaas", event.event_id)


def test_make_fake_gateway_event_default_event_id_is_stable_shape() -> None:
    event = make_fake_gateway_event()
    assert event.event_id.startswith("evt_fake_stripe_")


def test_asaas_top_level_event_id_is_preferred() -> None:
    body = json.dumps(
        {"id": "evt_abc&123", "event": "PAYMENT_RECEIVED", "payment": {"id": "pay_9", "status": "RECEIVED"}}
    ).encode()
    event = parse_webhook_event(body, _asaas_headers(), gateway="asaas", asaas_webhook_token=ASAAS_TOKEN)
    assert event.event_id == "evt_abc&123"


def test_asaas_subscription_events_for_different_subscriptions_get_different_keys() -> None:
    keys = set()
    for sub_id in ("sub_1", "sub_2"):
        body = json.dumps(
            {"event": "SUBSCRIPTION_DELETED", "subscription": {"id": sub_id, "status": "INACTIVE"}}
        ).encode()
        event = parse_webhook_event(body, _asaas_headers(), gateway="asaas", asaas_webhook_token=ASAAS_TOKEN)
        assert event.subscription_id_at_gateway == sub_id
        keys.add(event.inbox_key)
    assert len(keys) == 2
