"""The `PaymentGateway` Protocol both Real adapters and the Fake implement."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import (
    FeeBreakdown,
    GatewayCustomer,
    GatewaySubscription,
    PaymentGatewayName,
    SubscriptionRequest,
)


@runtime_checkable
class PaymentGateway(Protocol):
    """Customers, subscriptions, and their fees. One vocabulary, N vendors.

    Deliberately narrow. It does **not** own:

    * **webhook idempotency** — `noctusai_lib.domain.payments.EventInbox`
      owns proving a duplicate `(gateway, event_id)` delivery is a no-op;
    * **the subscription state machine** — `noctusai_lib.domain.payments`
      owns `trialing → active → past_due → grace → canceled|expired`.
      "grace" in particular is OUR business rule layered on top of
      whatever the gateway reports, not something either vendor has a
      status for;
    * **checkout / hosted-page flows** — Stripe Checkout Sessions and
      Asaas payment links are UI-adjacent concerns a consumer builds on
      top of `create_subscription`, not part of this contract;
    * **one-off charges** — that is `products/p-studio`'s
      `ProvedorCobranca` family (Pix/boleto receivables). This Protocol
      is recurring-billing only.

    A consumer selects an implementation once, at the factory, and never
    branches on `PaymentGatewayName` afterward — that branching is
    exactly the fork this Protocol exists to prevent.
    """

    name: PaymentGatewayName

    def ensure_customer(
        self, *, external_reference: str, email: str, name: str
    ) -> GatewayCustomer:
        """Create the payer, reusing an existing gateway customer when
        one already exists for `external_reference`."""
        ...

    def create_subscription(self, request: SubscriptionRequest) -> GatewaySubscription:
        ...

    def get_subscription(self, id_at_gateway: str) -> GatewaySubscription:
        ...

    def cancel_subscription(self, id_at_gateway: str) -> GatewaySubscription:
        ...

    def get_fee_breakdown(self, charge_id_at_gateway: str) -> FeeBreakdown:
        """Return the gross/fee/net split for one settled charge.

        `charge_id_at_gateway` is whatever identifies a single charge in
        that gateway's own vocabulary (a Stripe `ch_...` charge id, an
        Asaas `pay_...` payment id) — the id a consumer already has from
        `GatewaySubscription.latest_charge_id_at_gateway` or a webhook
        event, never invented by the caller.
        """
        ...


__all__ = ["PaymentGateway"]
