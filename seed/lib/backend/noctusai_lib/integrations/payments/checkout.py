"""Hosted checkout — the redirect-the-payer-to-a-gateway-page flow.

A sibling to `.protocol.PaymentGateway`, not a replacement: `PaymentGateway`
owns customers/subscriptions/fees as a headless API surface; `HostedCheckout`
owns the ONE extra thing a consumer needs when it wants the GATEWAY to render
the payment form instead of building its own — "give me a URL to redirect the
payer to, and tell me what I got back."

**New file, additive-only.** This module does not edit `protocol.py`,
`factory.py`, `fake.py`, `real_stripe.py`, or `real_asaas.py` — every
`*HostedCheckout` class below COMPOSES the existing `PaymentGateway`
implementations (imported, never duplicated) so `ensure_customer` /
`create_subscription` / the Stripe SDK call + error-translation plumbing
stay defined in exactly one place.

**Stripe vs. Asaas — genuinely different flows, one Protocol:**

* **Stripe** has a first-class hosted page: a Checkout Session in
  `mode="subscription"` IS the create-a-subscription call. This module's
  `StripeHostedCheckout.create_checkout` therefore does **not** also call
  `PaymentGateway.create_subscription` — that would attempt to bill the
  customer twice (once via `Subscription.create`, once implicitly when the
  payer completes the hosted page). `stripe.checkout.Session.create` is
  the only creation call on this path.
* **Asaas has no hosted-checkout equivalent.** There is no "Asaas Checkout
  page" API for a NEW subscription the way Stripe has one — Asaas' own
  checkout-link product is a separate, unrelated feature (ad-hoc payment
  links, not tied to `Subscription` objects). So `AsaasHostedCheckout.
  create_checkout` REUSES `AsaasPaymentGateway.ensure_customer` +
  `.create_subscription` (a real subscription IS created immediately,
  unlike Stripe where creation waits for the payer), then fetches the
  first generated `Payment`'s `invoiceUrl` — Asaas' own hosted payment
  page for that ONE charge — and hands that back as the "checkout url".
  A consumer redirects the payer there exactly as it would a Stripe
  Checkout URL; the difference in WHEN the subscription actually exists
  is a fact this module documents, not one it can paper over.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Union, runtime_checkable

import httpx

from .errors import PaymentGatewayError
from .factory import make_payment_gateway
from .real_asaas import DEFAULT_BASE_URL as ASAAS_DEFAULT_BASE_URL
from .real_asaas import DEFAULT_TIMEOUT_SECONDS as ASAAS_DEFAULT_TIMEOUT_SECONDS
from .real_asaas import AsaasPaymentGateway
from .real_stripe import StripePaymentGateway
from .types import BillingCycle, BillingMethod, Money, PaymentGatewayName, SubscriptionRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PixQr:
    """Asaas' Pix "Copia e Cola" payload + a scannable image, from the
    `GET /payments/{id}/pixQrCode` endpoint. `None` on the `CheckoutSession`
    for every non-Pix `billing_method` and for Stripe (whose hosted page
    renders its own Pix UI internally when the merchant enables it —
    nothing this module's caller ever needs to render itself).
    """

    payload: str  # the "Pix Copia e Cola" string — pasteable into any Pix app
    encoded_image: str  # base64 PNG, ready for an `<img src="data:image/png;base64,...">`
    expiration_date: Optional[str] = None  # ISO date, when Asaas reports one


@dataclass(frozen=True)
class CheckoutRequest:
    """What we want the gateway's hosted page to collect. Zero gateway
    vocabulary — same posture as `SubscriptionRequest`.

    `success_url` / `cancel_url` are Stripe-only (Checkout Sessions require
    both); `AsaasHostedCheckout` ignores them — Asaas' `invoiceUrl` has no
    redirect-back concept, the payer just closes the tab once paid and a
    webhook is how the consumer finds out.
    """

    external_reference: str  # our subscription/org id — the conciliation key
    email: str
    name: str
    price: Money
    billing_cycle: BillingCycle = "monthly"
    billing_method: BillingMethod = "unspecified"
    plan_ref: Optional[str] = None  # Stripe: a pre-created Price id, REQUIRED
    success_url: Optional[str] = None  # Stripe: REQUIRED
    cancel_url: Optional[str] = None  # Stripe: REQUIRED
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckoutSession:
    """What we got back — a URL to redirect the payer to, plus whatever
    the gateway already knows at creation time.

    `subscription_id_at_gateway` is `None` for a freshly-created Stripe
    Checkout Session (Stripe only creates the `Subscription` once the payer
    completes the hosted page) and ALWAYS populated for Asaas (whose
    subscription exists immediately — see the module docstring).
    """

    id_at_gateway: str  # Stripe: `cs_...` Checkout Session id. Asaas: the subscription id (no separate "session" resource exists)
    checkout_url: str  # where to redirect the payer
    customer_id_at_gateway: str
    external_reference: str
    subscription_id_at_gateway: Optional[str] = None
    pix_qr: Optional[PixQr] = None
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class HostedCheckout(Protocol):
    """The Protocol both `create_checkout` implementations and the Fake
    satisfy. Sibling to `.protocol.PaymentGateway`, not a wider surface on
    it — a consumer that only needs a redirect URL implements/consumes
    this Protocol alone; `PaymentGateway` stays the headless surface for
    consumers building their own payment form.
    """

    name: PaymentGatewayName

    def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        ...


class StripeHostedCheckout:
    """`HostedCheckout` over a Stripe Checkout Session in subscription mode.

    Composes a `StripePaymentGateway` instance and reuses its `_stripe()`
    (lazy SDK import + api_key wiring) and `_call()` (StripeError →
    `PaymentGatewayError` translation) private helpers rather than
    re-implementing either — both are internal to the `payments` package,
    and this module lives inside that same package.
    """

    name = PaymentGatewayName.STRIPE

    def __init__(self, gateway: StripePaymentGateway) -> None:
        self._gateway = gateway

    def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        if not request.plan_ref:
            raise PaymentGatewayError(
                "stripe",
                "create_checkout requires plan_ref (a pre-created Stripe "
                "Price id) — same requirement as create_subscription, for "
                "the same reason: this adapter never synthesizes an ad-hoc "
                "Product/Price pair.",
                retryable=False,
            )
        if not request.success_url or not request.cancel_url:
            raise PaymentGatewayError(
                "stripe",
                "create_checkout requires both success_url and cancel_url — "
                "Stripe Checkout Sessions reject a request missing either.",
                retryable=False,
            )

        customer = self._gateway.ensure_customer(
            external_reference=request.external_reference,
            email=request.email,
            name=request.name,
        )

        stripe = self._gateway._stripe()
        metadata = {"external_reference": request.external_reference, **request.metadata}
        session = self._gateway._call(
            lambda: stripe.checkout.Session.create(
                mode="subscription",
                customer=customer.id_at_gateway,
                line_items=[{"price": request.plan_ref, "quantity": 1}],
                success_url=request.success_url,
                cancel_url=request.cancel_url,
                metadata=metadata,
                subscription_data={"metadata": metadata},
            )
        )
        return CheckoutSession(
            id_at_gateway=session["id"],
            checkout_url=session["url"],
            customer_id_at_gateway=customer.id_at_gateway,
            external_reference=request.external_reference,
            subscription_id_at_gateway=session.get("subscription"),
            raw=dict(session),
        )


class AsaasHostedCheckout:
    """`HostedCheckout` over Asaas — no native hosted-checkout resource, so
    this REDIRECTS TO THE FIRST GENERATED PAYMENT'S INVOICE PAGE instead.

    Flow: `ensure_customer` → `create_subscription` (both reused verbatim
    from `AsaasPaymentGateway`) → `GET /subscriptions/{id}/payments` for the
    first generated `Payment` → that payment's `invoiceUrl` IS the
    "checkout url". When `billing_method="pix"`, also fetches the Pix QR
    via `GET /payments/{id}/pixQrCode` so the caller can render it inline
    instead of forcing a redirect.
    """

    name = PaymentGatewayName.ASAAS

    def __init__(self, gateway: AsaasPaymentGateway) -> None:
        self._gateway = gateway

    def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        if request.billing_method not in ("pix", "boleto"):
            raise PaymentGatewayError(
                "asaas",
                "create_checkout requires billing_method='pix' or 'boleto' "
                f"— Asaas has no hosted-checkout page for {request.billing_method!r} "
                "(card checkout is a Stripe-only hosted flow in this package).",
                retryable=False,
            )

        customer = self._gateway.ensure_customer(
            external_reference=request.external_reference,
            email=request.email,
            name=request.name,
        )
        subscription = self._gateway.create_subscription(
            SubscriptionRequest(
                external_reference=request.external_reference,
                customer_id_at_gateway=customer.id_at_gateway,
                price=request.price,
                billing_cycle=request.billing_cycle,
                billing_method=request.billing_method,
                metadata=request.metadata,
            )
        )

        # `_request` is the same package-internal HTTP primitive
        # `AsaasPaymentGateway` itself uses for every other call (shared
        # headers, timeout, error mapping) — reused here rather than a
        # second httpx.Client with duplicated auth wiring.
        payments = self._gateway._request(
            "GET", f"/subscriptions/{subscription.id_at_gateway}/payments"
        )
        rows = payments.get("data") or []
        if not rows:
            raise PaymentGatewayError(
                "asaas",
                f"subscription {subscription.id_at_gateway} was created but "
                "has not generated a payment yet — Asaas generates the first "
                "charge asynchronously; retry shortly.",
                retryable=True,
            )
        first_payment = rows[0]
        invoice_url = first_payment.get("invoiceUrl")
        if not invoice_url:
            raise PaymentGatewayError(
                "asaas",
                f"payment {first_payment.get('id')!r} has no invoiceUrl",
                retryable=True,
            )

        pix_qr: Optional[PixQr] = None
        if request.billing_method == "pix":
            payment_id = first_payment["id"]
            qr_raw = self._gateway._request("GET", f"/payments/{payment_id}/pixQrCode")
            pix_qr = PixQr(
                payload=qr_raw["payload"],
                encoded_image=qr_raw["encodedImage"],
                expiration_date=qr_raw.get("expirationDate"),
            )

        return CheckoutSession(
            id_at_gateway=subscription.id_at_gateway,
            checkout_url=invoice_url,
            customer_id_at_gateway=customer.id_at_gateway,
            external_reference=request.external_reference,
            subscription_id_at_gateway=subscription.id_at_gateway,
            pix_qr=pix_qr,
            raw={"subscription": subscription.raw, "payment": first_payment},
        )


class FakeHostedCheckout:
    """In-memory `HostedCheckout` — no IO, no vendor SDK. Mirrors
    `FakePaymentGateway`'s posture: the executable example of the contract.
    """

    name = PaymentGatewayName.STRIPE  # arbitrary; consumer tests can override

    def __init__(self, *, checkout_base_url: str = "https://checkout.fake.test/") -> None:
        self._base_url = checkout_base_url.rstrip("/")
        self.sessions: dict[str, CheckoutSession] = {}
        # Recorded calls, so a test can assert on intent, not just outcome.
        self.calls: list[tuple[str, object]] = []
        self._seq = 0

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}_{self._seq:06d}"

    def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        self.calls.append(("create_checkout", request))
        session_id = self._next_id("cs")
        pix_qr: Optional[PixQr] = None
        if request.billing_method == "pix":
            pix_qr = PixQr(
                payload="00020126fake-pix-copia-e-cola-payload",
                encoded_image=base64.b64encode(b"fake-qr-png-bytes").decode("ascii"),
                expiration_date=None,
            )
        session = CheckoutSession(
            id_at_gateway=session_id,
            checkout_url=f"{self._base_url}/{session_id}",
            customer_id_at_gateway=self._next_id("cus"),
            external_reference=request.external_reference,
            subscription_id_at_gateway=self._next_id("sub"),
            pix_qr=pix_qr,
        )
        self.sessions[session_id] = session
        return session


def make_hosted_checkout(
    *,
    provider: Union[PaymentGatewayName, str, None] = None,
    use_fake: bool = False,
    stripe_api_key: Optional[str] = None,
    asaas_api_key: Optional[str] = None,
    asaas_base_url: str = ASAAS_DEFAULT_BASE_URL,
    asaas_timeout_seconds: float = ASAAS_DEFAULT_TIMEOUT_SECONDS,
    asaas_transport: Optional[httpx.BaseTransport] = None,
) -> Union[FakeHostedCheckout, StripeHostedCheckout, AsaasHostedCheckout]:
    """Build a `HostedCheckout`. Mirrors `make_payment_gateway`'s shape —
    same args, same validation — and in fact DELEGATES construction of the
    underlying gateway to it, so `provider`/`use_fake`/api-key validation
    lives in exactly one place.

    Raises:
        ValueError: same conditions as `make_payment_gateway` (missing
            provider, missing api key for the chosen provider, unknown
            provider name).
    """
    if use_fake:
        return FakeHostedCheckout()

    gateway = make_payment_gateway(
        provider=provider,
        stripe_api_key=stripe_api_key,
        asaas_api_key=asaas_api_key,
        asaas_base_url=asaas_base_url,
        asaas_timeout_seconds=asaas_timeout_seconds,
        asaas_transport=asaas_transport,
    )
    if isinstance(gateway, StripePaymentGateway):
        return StripeHostedCheckout(gateway)
    if isinstance(gateway, AsaasPaymentGateway):
        return AsaasHostedCheckout(gateway)
    raise ValueError(  # pragma: no cover - make_payment_gateway already validates
        f"make_hosted_checkout: unsupported gateway {gateway!r}"
    )


__all__ = [
    "AsaasHostedCheckout",
    "CheckoutRequest",
    "CheckoutSession",
    "FakeHostedCheckout",
    "HostedCheckout",
    "PixQr",
    "StripeHostedCheckout",
    "make_hosted_checkout",
]
