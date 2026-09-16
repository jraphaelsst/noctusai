"""Recurring payments — customers, subscriptions, and their fees. One
vocabulary, two gateways today (Stripe, Asaas), more later without
touching a consumer.

**What this is.** The part every recurring-billing integration
otherwise rewrites per-vendor: create a customer, start/cancel/fetch a
subscription, and normalize what the gateway took as its cut into
`gross`/`fee`/`net` — always integer cents, always one explicit
currency, never a float. A consumer swaps Stripe for Asaas by changing
one factory call, not by hunting down every `if provider == "stripe"`.

**What it is deliberately NOT.**

* Not `products/core`'s billing — Core's `stripe_service.py` /
  `billing_service.py` are LIVE with real customers and are untouched by
  this package. This organ ships ALONGSIDE Core; migrating Core onto it
  is a separate, separately-consented slice.
* Not `products/p-studio`'s `ProvedorCobranca` family — that is one-off
  receivables (Pix/boleto/card charges against a real-estate ledger),
  not recurring subscriptions. Different domain, different Protocol;
  this package's Asaas adapter deliberately does not import that one.
* Not webhook idempotency or the subscription state machine — both live
  in `noctusai_lib.domain.payments` (`EventInbox`, `SubscriptionState`)
  because they are pure business rules layered ON TOP of what a gateway
  reports, not gateway I/O.

**Recipe:**

    from noctusai_lib.integrations.payments import make_payment_gateway
    from noctusai_lib.integrations.payments.types import SubscriptionRequest, Money

    gateway = make_payment_gateway(provider="stripe", stripe_api_key=key)
    customer = gateway.ensure_customer(
        external_reference=org_id, email=email, name=name,
    )
    subscription = gateway.create_subscription(
        SubscriptionRequest(
            external_reference=org_id,
            customer_id_at_gateway=customer.id_at_gateway,
            price=Money(2990, "BRL"),
            plan_ref="price_123",  # Stripe only — Asaas ignores it
        )
    )
    fee = gateway.get_fee_breakdown(subscription.latest_charge_id_at_gateway)
    assert fee.gross.amount_cents == fee.fee.amount_cents + fee.net.amount_cents
"""
from __future__ import annotations

from .errors import PaymentGatewayError
from .factory import make_payment_gateway
from .fake import FakePaymentGateway
from .protocol import PaymentGateway
from .real_asaas import AsaasPaymentGateway
from .real_stripe import StripePaymentGateway
from .types import (
    BillingCycle,
    BillingMethod,
    FeeBreakdown,
    GatewayCustomer,
    GatewaySubscription,
    GatewaySubscriptionStatus,
    Money,
    PaymentGatewayName,
    SubscriptionRequest,
)

__all__ = [
    "AsaasPaymentGateway",
    "BillingCycle",
    "BillingMethod",
    "FakePaymentGateway",
    "FeeBreakdown",
    "GatewayCustomer",
    "GatewaySubscription",
    "GatewaySubscriptionStatus",
    "Money",
    "PaymentGateway",
    "PaymentGatewayError",
    "PaymentGatewayName",
    "StripePaymentGateway",
    "SubscriptionRequest",
    "make_payment_gateway",
]
