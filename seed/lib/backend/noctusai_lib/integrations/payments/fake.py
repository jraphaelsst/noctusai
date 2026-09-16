"""In-memory `PaymentGateway` — the reference implementation.

Lives in `noctusai_lib/` and not in `tests/` on purpose, mirroring
`noctusai_lib.domain.jobs.repo.FakeJobRepository`: it is the executable
example of the contract, so if it drifts from the Protocol, static
typing catches it before a Real adapter does. No IO, no vendor SDK — a
consumer's tests run against this with no network and no keys.
"""
from __future__ import annotations

from typing import Optional

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


class FakePaymentGateway:
    """Deterministic, in-process `PaymentGateway`.

    Args:
        default_fee_bps: the fee, in basis points of the gross amount,
            `get_fee_breakdown` charges by default when no per-charge
            fee was scripted via `script_fee`. Defaults to 299 (2.99%),
            a plausible card-processing rate — tests that care about the
            exact split should call `script_fee` instead of relying on
            this default.
    """

    name = PaymentGatewayName.STRIPE  # arbitrary; consumer tests can override

    def __init__(self, *, default_fee_bps: int = 299) -> None:
        self._default_fee_bps = default_fee_bps
        self.customers: dict[str, GatewayCustomer] = {}
        self.subscriptions: dict[str, GatewaySubscription] = {}
        self._scripted_fees: dict[str, FeeBreakdown] = {}
        # Recorded calls, so tests can assert on intent, not just outcome.
        self.calls: list[tuple[str, object]] = []
        self._seq = 0
        self._credentials_error: Exception | None = None

    # ── test helpers ─────────────────────────────────────────────────

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}_{self._seq:06d}"

    def set_status(self, id_at_gateway: str, status: GatewaySubscriptionStatus) -> GatewaySubscription:
        """Force a subscription into a status, simulating a webhook-driven
        change the consumer hasn't polled for yet."""
        sub = self._require(id_at_gateway)
        updated = GatewaySubscription(
            id_at_gateway=sub.id_at_gateway,
            customer_id_at_gateway=sub.customer_id_at_gateway,
            external_reference=sub.external_reference,
            status=status,
            current_period_end=sub.current_period_end,
            latest_charge_id_at_gateway=sub.latest_charge_id_at_gateway,
            raw=sub.raw,
        )
        self.subscriptions[id_at_gateway] = updated
        return updated

    def script_fee(self, charge_id_at_gateway: str, fee: FeeBreakdown) -> None:
        """Pin the exact `FeeBreakdown` a future `get_fee_breakdown` call
        returns for this charge id."""
        self._scripted_fees[charge_id_at_gateway] = fee

    # ── PaymentGateway ───────────────────────────────────────────────

    def fail_credentials(self, error: Exception | None) -> None:
        """Script the next `verify_credentials` outcome (None = succeed)."""
        self._credentials_error = error

    def ensure_customer(
        self,
        *,
        external_reference: str,
        email: str,
        name: str,
        tax_id: Optional[str] = None,
    ) -> GatewayCustomer:
        self.calls.append(("ensure_customer", external_reference))
        for existing in self.customers.values():
            if existing.external_reference == external_reference:
                return existing
        customer = GatewayCustomer(
            id_at_gateway=self._next_id("cus"),
            external_reference=external_reference,
            email=email,
            name=name,
        )
        self.customers[customer.id_at_gateway] = customer
        return customer

    def create_subscription(self, request: SubscriptionRequest) -> GatewaySubscription:
        self.calls.append(("create_subscription", request))
        charge_id = self._next_id("ch")
        subscription = GatewaySubscription(
            id_at_gateway=self._next_id("sub"),
            customer_id_at_gateway=request.customer_id_at_gateway,
            external_reference=request.external_reference,
            status="trialing" if request.trial_days > 0 else "incomplete",
            latest_charge_id_at_gateway=charge_id,
            raw={
                "price_cents": request.price.amount_cents,
                "currency": request.price.currency,
                "billing_cycle": request.billing_cycle,
                "billing_method": request.billing_method,
                "plan_ref": request.plan_ref,
                "trial_days": request.trial_days,
                "metadata": dict(request.metadata),
            },
        )
        self.subscriptions[subscription.id_at_gateway] = subscription
        return subscription

    def _require(self, id_at_gateway: str) -> GatewaySubscription:
        # Same failure shape as the Real adapters' 404 — a consumer that
        # handles `PaymentGatewayError` must not meet a bare KeyError here.
        try:
            return self.subscriptions[id_at_gateway]
        except KeyError:
            raise PaymentGatewayError(
                self.name.value if hasattr(self.name, "value") else str(self.name),
                f"No such subscription: {id_at_gateway}",
                status=404,
                code="resource_missing",
            ) from None

    def get_subscription(self, id_at_gateway: str) -> GatewaySubscription:
        self.calls.append(("get_subscription", id_at_gateway))
        return self._require(id_at_gateway)

    def cancel_subscription(self, id_at_gateway: str) -> GatewaySubscription:
        self.calls.append(("cancel_subscription", id_at_gateway))
        return self.set_status(id_at_gateway, "canceled")

    def verify_credentials(self) -> None:
        self.calls.append(("verify_credentials", None))
        if self._credentials_error is not None:
            raise self._credentials_error

    def get_fee_breakdown(self, charge_id_at_gateway: str) -> FeeBreakdown:
        self.calls.append(("get_fee_breakdown", charge_id_at_gateway))
        scripted = self._scripted_fees.get(charge_id_at_gateway)
        if scripted is not None:
            return scripted
        # Deterministic default: a plausible gross derived from the id's
        # numeric suffix, fee at `default_fee_bps`, so a test that never
        # scripted a fee still gets a self-consistent, non-zero split.
        gross_cents = 10_000
        fee_cents = (gross_cents * self._default_fee_bps) // 10_000
        net_cents = gross_cents - fee_cents
        return FeeBreakdown(
            gross=Money(gross_cents, "BRL"),
            fee=Money(fee_cents, "BRL"),
            net=Money(net_cents, "BRL"),
        )


__all__ = ["FakePaymentGateway"]
