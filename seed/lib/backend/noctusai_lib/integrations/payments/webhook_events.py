"""Webhook event parsing — verify the delivery, normalize it, hand back a
gateway-agnostic `GatewayEvent`.

**New file, additive-only.** Sibling to `.checkout`: does not edit
`protocol.py` / `factory.py` / `fake.py` / `real_stripe.py` / `real_asaas.py`.
Reuses each gateway's existing status-mapping helpers by IMPORTING them
(`StripePaymentGateway._map_status`, `AsaasPaymentGateway.
_map_subscription_status` — both `@staticmethod`, callable without an
instance) rather than re-deriving either vendor's status vocabulary here.

**What this module does NOT do**, mirroring `.protocol.PaymentGateway`'s
own "deliberately narrow" posture:

* it does not call `noctusai_lib.domain.payments.EventInbox.claim` — a
  consumer's webhook handler does that itself with `GatewayEvent.
  inbox_key`, exactly like the recipe `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/
  payments.md` already documents for `event["id"]`;
* it does not call `noctusai_lib.domain.payments.transition` — a consumer
  decides the target `SubscriptionState` from `GatewayEvent.
  subscription_status` (when present); this module never invents its own
  parallel state machine.

**Signature verification, one call each:**

* **Stripe** — `stripe.Webhook.construct_event(payload, sig_header, secret)`.
  Don't wrap it, don't reinvent it (`noctusai_lib.security.
  webhook_signatures`'s own module docstring names this as the one scheme
  that MUST go through the vendor SDK). `stripe` is imported lazily inside
  the parsing function, matching `real_stripe.py`'s convention — importing
  this module, or using the Fake event builder, never requires the SDK.
* **Asaas** — the `asaas-access-token` header. Asaas sends the raw
  configured token VERBATIM in this header: no `Basic`/base64 envelope, no
  username half, no body-binding signature at all — it is a bare
  shared-secret compare (see `docs.asaas.com/docs/webhook-authentication`).
  That shape does not literally match `noctusai_lib.security.
  webhook_signatures.verify_basic_shared_secret`'s `Authorization: Basic
  base64("<user>:<secret>")` input, but wrapping the raw token in a
  synthetic empty-username Basic credential (`expected_username=None`)
  reuses that helper's constant-time `hmac.compare_digest` call instead of
  adding a second one here — see `_verify_asaas_access_token` below.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Optional, Union

from noctusai_lib.security.webhook_signatures import verify_basic_shared_secret

from ._stripe_fields import stripe_field
from .real_stripe import StripePaymentGateway
from .types import GatewaySubscriptionStatus, PaymentGatewayName

logger = logging.getLogger(__name__)

#: Normalized shape every consumer branches on, regardless of gateway.
#: `"ignored"` is a first-class, expected outcome for any event type
#: neither gateway-specific map below recognizes — NOT an error. A
#: gateway adding a new event type later must never turn into a webhook
#: 500; it turns into a `GatewayEvent(kind="ignored")` a consumer skips.
EventKind = Literal[
    "subscription_updated", "charge_paid", "charge_failed", "charge_refunded", "ignored"
]


class PaymentWebhookSignatureError(Exception):
    """A webhook delivery failed signature/token verification.

    Distinct from `.errors.PaymentGatewayError` on purpose: a bad signature
    is not "the gateway call failed" (nothing was called — this fires
    before any request even reached the vendor), it's "someone who is not
    the configured gateway sent us this payload." A consumer's router
    translates this to a 401, never a 5xx.
    """

    def __init__(self, gateway: str, detail: str) -> None:
        self.gateway = gateway
        self.detail = detail
        super().__init__(f"[{gateway}] webhook signature invalid: {detail}")


@dataclass(frozen=True)
class GatewayEvent:
    """One verified, normalized webhook delivery.

    `event_id` is the gateway's own delivery id when it has one (Stripe's
    `evt_...`) or a documented deterministic derivation when it doesn't
    (Asaas — see `_derive_asaas_event_id`). Either way `inbox_key` is what
    a consumer hands to `noctusai_lib.domain.payments.EventInbox.claim`.
    """

    gateway: str  # "stripe" | "asaas"
    event_id: str
    kind: EventKind
    external_reference: Optional[str] = None
    subscription_id_at_gateway: Optional[str] = None
    charge_id_at_gateway: Optional[str] = None
    #: The gateway-reported subscription status AT THE TIME OF THIS EVENT,
    #: when the event carries one — `None` for a charge-only event (Asaas
    #: payment webhooks never carry a subscription status; see module
    #: docstring). A consumer maps this to a `noctusai_lib.domain.payments.
    #: SubscriptionState` transition itself; this module never guesses one.
    subscription_status: Optional[GatewaySubscriptionStatus] = None
    #: Forensic — the normalized fields above are a lossy projection.
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def inbox_key(self) -> tuple[str, str]:
        """`(gateway, event_id)` — pass straight to `EventInbox.claim`."""
        return (self.gateway, self.event_id)


# ── header lookup (plain Mapping — headers may not be case-normalized) ──


def _get_header(headers: Mapping[str, str], name: str) -> Optional[str]:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


# ── Stripe ───────────────────────────────────────────────────────────────

# Stripe event `type` → our normalized `kind`. Anything not listed here is
# `"ignored"` — deliberately permissive (see `EventKind` docstring).
_STRIPE_EVENT_KIND_MAP: dict[str, EventKind] = {
    "customer.subscription.created": "subscription_updated",
    "customer.subscription.updated": "subscription_updated",
    "customer.subscription.deleted": "subscription_updated",
    "invoice.paid": "charge_paid",
    "invoice.payment_succeeded": "charge_paid",
    "invoice.payment_failed": "charge_failed",
    "charge.refunded": "charge_refunded",
}


# Promoted to `._stripe_fields` (now shared with `real_stripe` and
# `checkout`); the private name stays importable for existing callers.
_stripe_field = stripe_field


def _parse_stripe_event(
    body: bytes, headers: Mapping[str, str], *, secret: Optional[str]
) -> GatewayEvent:
    if not secret:
        raise PaymentWebhookSignatureError("stripe", "stripe_webhook_secret not configured")
    signature = _get_header(headers, "stripe-signature")
    if not signature:
        raise PaymentWebhookSignatureError("stripe", "missing Stripe-Signature header")

    import stripe  # local import — keeps this module importable w/o the SDK

    try:
        event = stripe.Webhook.construct_event(payload=body, sig_header=signature, secret=secret)
    except stripe.SignatureVerificationError as exc:
        raise PaymentWebhookSignatureError("stripe", str(exc)) from exc
    except ValueError as exc:  # malformed JSON payload
        raise PaymentWebhookSignatureError("stripe", f"invalid payload: {exc}") from exc

    event_type = event["type"]
    data_object = event["data"]["object"]
    kind = _STRIPE_EVENT_KIND_MAP.get(event_type, "ignored")

    metadata = _stripe_field(data_object, "metadata", {})
    external_reference = _stripe_field(metadata, "external_reference")
    subscription_id: Optional[str] = None
    charge_id: Optional[str] = None
    subscription_status: Optional[GatewaySubscriptionStatus] = None

    if event_type.startswith("customer.subscription."):
        subscription_id = _stripe_field(data_object, "id")
        raw_status = _stripe_field(data_object, "status")
        if raw_status is not None:
            # Reuse — not re-derive — the exact map `real_stripe.py` uses.
            subscription_status = StripePaymentGateway._map_status(raw_status)
    elif event_type in ("invoice.paid", "invoice.payment_succeeded", "invoice.payment_failed"):
        subscription_id = _stripe_field(data_object, "subscription")
        charge_id = _stripe_field(data_object, "charge")
    elif event_type == "charge.refunded":
        charge_id = _stripe_field(data_object, "id")

    return GatewayEvent(
        gateway="stripe",
        event_id=event["id"],
        kind=kind,
        external_reference=external_reference,
        subscription_id_at_gateway=subscription_id,
        charge_id_at_gateway=charge_id,
        subscription_status=subscription_status,
        raw=event.to_dict(),
    )


# ── Asaas ────────────────────────────────────────────────────────────────

# Asaas `event` → our normalized `kind`. Asaas webhooks are PAYMENT-level
# only — there is no `SUBSCRIPTION_*` event in its catalog, so
# `"subscription_updated"` never fires on this path (documented finding,
# not an oversight: a consumer that needs the subscription's own coarse
# ACTIVE/EXPIRED/INACTIVE status polls `AsaasPaymentGateway.
# get_subscription` directly). Anything not listed here is `"ignored"`.
_ASAAS_EVENT_KIND_MAP: dict[str, EventKind] = {
    "PAYMENT_CONFIRMED": "charge_paid",
    "PAYMENT_RECEIVED": "charge_paid",
    "PAYMENT_OVERDUE": "charge_failed",
    "PAYMENT_REFUNDED": "charge_refunded",
    "PAYMENT_CHARGEBACK_REQUESTED": "charge_refunded",
}


def _verify_asaas_access_token(headers: Mapping[str, str], *, token: Optional[str]) -> None:
    if not token:
        raise PaymentWebhookSignatureError("asaas", "asaas_webhook_token not configured")
    received = _get_header(headers, "asaas-access-token")
    if not received:
        raise PaymentWebhookSignatureError("asaas", "missing asaas-access-token header")
    # See module docstring: wrap the raw token as a synthetic
    # empty-username Basic credential purely to route the compare through
    # `verify_basic_shared_secret`'s existing `hmac.compare_digest` call.
    synthetic_header = "Basic " + base64_encode_colon_secret(received)
    if not verify_basic_shared_secret(synthetic_header, token, expected_username=None):
        raise PaymentWebhookSignatureError("asaas", "asaas-access-token mismatch")


def base64_encode_colon_secret(secret: str) -> str:
    """`base64(":" + secret)` — the synthetic Basic-credential encoding
    `_verify_asaas_access_token` needs. A tiny named helper (not inlined)
    so the encoding step has a name a test can call directly.
    """
    return base64.b64encode(f":{secret}".encode("utf-8")).decode("ascii")


def _derive_asaas_event_id(event_name: str, payment: Mapping[str, Any]) -> str:
    """Asaas webhook payloads carry NO stable per-delivery id — confirmed
    against `docs.asaas.com/docs/webhook-events`: the payload is
    `{"event": "...", "payment": {...}}`, no top-level `id`/`eventId` field
    (unlike Stripe's `evt_...`). This derives a deterministic substitute
    from `(event name, payment id, payment status, the payment's own
    moment field)` so:

    * a genuine RETRY of the identical delivery (same event, same payment
      snapshot) produces the same key → `EventInbox.claim` correctly
      dedupes it;
    * a real STATE CHANGE on the same payment (a later webhook reporting
      a new status, e.g. `PAYMENT_CREATED` → `PAYMENT_RECEIVED`, or the
      same status re-fired after `paymentDate`/`dueDate` moved) produces a
      different key → treated as a new event, not silently swallowed.

    This is OUR construction, not a gateway-issued id — documented here and
    in `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/payments.md` precisely because
    a future reader must not mistake it for something Asaas guarantees.
    """
    payment_id = payment.get("id", "")
    status = payment.get("status", "")
    moment = payment.get("paymentDate") or payment.get("clientPaymentDate") or payment.get("dueDate") or ""
    return f"{event_name}:{payment_id}:{status}:{moment}"


def _parse_asaas_event(
    body: bytes, headers: Mapping[str, str], *, token: Optional[str]
) -> GatewayEvent:
    _verify_asaas_access_token(headers, token=token)

    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise PaymentWebhookSignatureError("asaas", f"invalid JSON payload: {exc}") from exc

    event_name = payload.get("event", "")
    payment = payload.get("payment") or {}
    subscription = payload.get("subscription") or {}
    kind = _ASAAS_EVENT_KIND_MAP.get(event_name, "ignored")

    # Current Asaas deliveries carry a top-level `id` (`evt_...`) — the
    # gateway's own dedupe key, preferred when present. The derivation is
    # the fallback, and it must not collapse non-payment events: a
    # `SUBSCRIPTION_*` delivery has no `payment`, so without the
    # subscription snapshot every one of them would share one key and the
    # inbox would drop all but the first.
    event_id = payload.get("id") or (
        _derive_asaas_event_id(event_name, payment)
        if payment
        else _derive_asaas_event_id(event_name, subscription)
    )

    return GatewayEvent(
        gateway="asaas",
        event_id=str(event_id),
        kind=kind,
        external_reference=payment.get("externalReference"),
        subscription_id_at_gateway=payment.get("subscription") or subscription.get("id"),
        charge_id_at_gateway=payment.get("id"),
        # No subscription-status field on an Asaas payment webhook — see
        # `_ASAAS_EVENT_KIND_MAP`'s docstring. A consumer that needs the
        # subscription's own coarse status calls `AsaasPaymentGateway.
        # get_subscription` directly (its `_map_subscription_status` is
        # what that call already reuses — nothing to map on this path).
        subscription_status=None,
        raw=payload,
    )


# ── entry point ──────────────────────────────────────────────────────────


def parse_webhook_event(
    body: bytes,
    headers: Mapping[str, str],
    *,
    gateway: Union[PaymentGatewayName, str],
    stripe_webhook_secret: Optional[str] = None,
    asaas_webhook_token: Optional[str] = None,
) -> GatewayEvent:
    """Verify + normalize one inbound webhook delivery.

    Args:
        body: RAW request body bytes — Stripe's signature is computed over
            the exact bytes sent; re-serializing parsed JSON breaks it.
        headers: request headers (case-insensitive lookup; a plain `dict`
            with any casing works, so does FastAPI's `Headers`).
        gateway: which gateway sent this delivery — the caller's route
            already knows this (e.g. `/webhooks/stripe` vs `/webhooks/asaas`);
            this function does not sniff it from the payload.
        stripe_webhook_secret: required when `gateway="stripe"`.
        asaas_webhook_token: required when `gateway="asaas"` — the same
            token value configured on the Asaas webhook registration.

    Raises:
        PaymentWebhookSignatureError: missing/wrong secret or token,
            missing/malformed signature header, or unparseable payload.
        ValueError: `gateway` is neither `"stripe"` nor `"asaas"`.
    """
    normalized = PaymentGatewayName(gateway)
    if normalized is PaymentGatewayName.STRIPE:
        return _parse_stripe_event(body, headers, secret=stripe_webhook_secret)
    if normalized is PaymentGatewayName.ASAAS:
        return _parse_asaas_event(body, headers, token=asaas_webhook_token)
    raise ValueError(f"parse_webhook_event: unknown gateway {gateway!r}")  # pragma: no cover


def make_fake_gateway_event(
    *,
    gateway: Union[PaymentGatewayName, str] = PaymentGatewayName.STRIPE,
    kind: EventKind = "charge_paid",
    event_id: Optional[str] = None,
    external_reference: Optional[str] = None,
    subscription_id_at_gateway: Optional[str] = None,
    charge_id_at_gateway: Optional[str] = None,
    subscription_status: Optional[GatewaySubscriptionStatus] = None,
    raw: Optional[dict[str, Any]] = None,
) -> GatewayEvent:
    """Build a `GatewayEvent` directly — the dev/test seam for consumer code
    (webhook handlers, job workers) that needs one WITHOUT constructing a
    real signed Stripe payload or an Asaas token. Bypasses
    `parse_webhook_event` and every signature check entirely; never call
    this from a real webhook route.
    """
    normalized = PaymentGatewayName(gateway)
    return GatewayEvent(
        gateway=normalized.value,
        event_id=event_id or f"evt_fake_{normalized.value}_{kind}",
        kind=kind,
        external_reference=external_reference,
        subscription_id_at_gateway=subscription_id_at_gateway,
        charge_id_at_gateway=charge_id_at_gateway,
        subscription_status=subscription_status,
        raw=raw or {},
    )


__all__ = [
    "EventKind",
    "GatewayEvent",
    "PaymentWebhookSignatureError",
    "make_fake_gateway_event",
    "parse_webhook_event",
]
