"""The Stripe-backed `PaymentGateway`.

`stripe` is declared in `pyproject.toml` (every product image gets it,
same convention as `docxtpl`/`resvg-py`/`xhtml2pdf`) but imported LAZILY
inside each method — importing this module, or exercising the Fake, must
never require the SDK to be installed.

Amounts: Stripe already reports money in the smallest currency unit
(cents for BRL/USD), so `Money` construction here is a direct wrap, not
a conversion — unlike the Asaas adapter, which converts from Reais.

Every `stripe.StripeError` is translated to `PaymentGatewayError` at the
boundary — never let the vendor exception escape — so a consumer catches
one exception type regardless of which gateway is configured.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional, TypeVar

from .errors import PaymentGatewayError
from .types import (
    FeeBreakdown,
    GatewayCustomer,
    GatewaySubscription,
    GatewaySubscriptionStatus,
    Money,
    PaymentGatewayName,
    SubscriptionRequest,
)

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Stripe's own subscription statuses → our normalized vocabulary. Kept
# permissive (unknown Stripe status → "incomplete") rather than raising,
# because a status Stripe adds later must not crash a consumer mid-poll —
# it should present as "needs attention", not 500.
_STATUS_MAP: dict[str, GatewaySubscriptionStatus] = {
    "trialing": "trialing",
    "active": "active",
    "past_due": "past_due",
    "canceled": "canceled",
    "incomplete": "incomplete",
    "incomplete_expired": "incomplete",
    "unpaid": "unpaid",
    "paused": "past_due",
}


class StripePaymentGateway:
    """Real `PaymentGateway` over the Stripe Python SDK.

    `api_key` is set on the module-level `stripe` object at call time
    (matching Stripe SDK conventions and `products/core`'s existing
    `stripe_service._ensure_api_key`) rather than at construction, so a
    consumer holding a `StripePaymentGateway` never has a stale key if
    the credential rotates.
    """

    name = PaymentGatewayName.STRIPE

    def __init__(self, *, api_key: str) -> None:
        if not api_key:
            raise ValueError("StripePaymentGateway requires a non-empty api_key")
        self._api_key = api_key

    def _stripe(self) -> Any:
        import stripe  # local import — keeps this module importable w/o the SDK

        stripe.api_key = self._api_key
        return stripe

    def _call(self, fn: Callable[[], _T]) -> _T:
        """Run one Stripe SDK call, translating `stripe.StripeError`.

        A 429 or a 5xx is worth retrying; everything else (bad request,
        auth, not-found) is not — retrying an identical malformed
        request just burns the retry budget for no benefit.
        """
        import stripe

        try:
            return fn()
        except stripe.StripeError as exc:
            status = getattr(exc, "http_status", None)
            code = getattr(exc, "code", None)
            logger.warning("stripe gateway error: status=%s code=%s err=%s", status, code, exc)
            raise PaymentGatewayError(
                "stripe",
                str(exc),
                status=status,
                code=code,
                retryable=status == 429 or (status is not None and status >= 500),
            ) from exc

    @staticmethod
    def _map_status(raw_status: str) -> GatewaySubscriptionStatus:
        return _STATUS_MAP.get(raw_status, "incomplete")

    def _to_gateway_subscription(self, sub: Any) -> GatewaySubscription:
        latest_invoice = sub.get("latest_invoice")
        charge_id: Optional[str] = None
        if latest_invoice is not None:
            # `latest_invoice` may be an id (str) or an expanded object,
            # depending on whether the caller asked Stripe to expand it.
            charge_id = (
                latest_invoice
                if isinstance(latest_invoice, str)
                else latest_invoice.get("charge")
            )
        return GatewaySubscription(
            id_at_gateway=sub["id"],
            customer_id_at_gateway=sub["customer"],
            external_reference=(sub.get("metadata") or {}).get("external_reference"),
            status=self._map_status(sub["status"]),
            current_period_end=(
                None
                if sub.get("current_period_end") is None
                else str(sub["current_period_end"])
            ),
            latest_charge_id_at_gateway=charge_id,
            raw=dict(sub),
        )

    # ── PaymentGateway ───────────────────────────────────────────────

    def ensure_customer(
        self, *, external_reference: str, email: str, name: str
    ) -> GatewayCustomer:
        stripe = self._stripe()
        existing = self._call(
            lambda: stripe.Customer.search(
                query=f"metadata['external_reference']:'{external_reference}'"
            )
        )
        if existing.data:
            found = existing.data[0]
            return GatewayCustomer(
                id_at_gateway=found["id"],
                external_reference=external_reference,
                email=found.get("email") or email,
                name=found.get("name") or name,
            )
        created = self._call(
            lambda: stripe.Customer.create(
                email=email,
                name=name,
                metadata={"external_reference": external_reference},
            )
        )
        return GatewayCustomer(
            id_at_gateway=created["id"],
            external_reference=external_reference,
            email=email,
            name=name,
        )

    def create_subscription(self, request: SubscriptionRequest) -> GatewaySubscription:
        # Stripe's idiomatic flow bills against a pre-created `Price`
        # object. This adapter does not synthesize one from `price` /
        # `billing_cycle` — that would mean creating a throwaway Product
        # per subscription, which pollutes the Stripe dashboard's catalog
        # for every caller. Fail loudly instead of guessing.
        if not request.plan_ref:
            raise PaymentGatewayError(
                "stripe",
                "create_subscription requires plan_ref (a pre-created Stripe "
                "Price id) — this adapter does not create ad-hoc Prices.",
                retryable=False,
            )
        stripe = self._stripe()
        sub = self._call(
            lambda: stripe.Subscription.create(
                customer=request.customer_id_at_gateway,
                items=[{"price": request.plan_ref}],
                metadata={
                    "external_reference": request.external_reference,
                    **request.metadata,
                },
                payment_behavior="default_incomplete",
                expand=["latest_invoice"],
            )
        )
        return self._to_gateway_subscription(sub)

    def get_subscription(self, id_at_gateway: str) -> GatewaySubscription:
        stripe = self._stripe()
        sub = self._call(
            lambda: stripe.Subscription.retrieve(id_at_gateway, expand=["latest_invoice"])
        )
        return self._to_gateway_subscription(sub)

    def cancel_subscription(self, id_at_gateway: str) -> GatewaySubscription:
        stripe = self._stripe()
        sub = self._call(lambda: stripe.Subscription.cancel(id_at_gateway))
        return self._to_gateway_subscription(sub)

    def get_fee_breakdown(self, charge_id_at_gateway: str) -> FeeBreakdown:
        stripe = self._stripe()
        charge = self._call(
            lambda: stripe.Charge.retrieve(
                charge_id_at_gateway, expand=["balance_transaction"]
            )
        )
        txn = charge["balance_transaction"]
        currency = str(txn["currency"]).upper()
        return FeeBreakdown(
            gross=Money(int(txn["amount"]), currency),
            fee=Money(int(txn["fee"]), currency),
            net=Money(int(txn["net"]), currency),
        )


__all__ = ["StripePaymentGateway"]
