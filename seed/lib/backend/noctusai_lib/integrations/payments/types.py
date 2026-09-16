"""Gateway-agnostic value objects for recurring payments.

Pure: no IO, no clock, no vendor SDK. The whole point of this module is
that ``Money`` and ``FeeBreakdown`` mean the same thing whether the
gateway is Stripe or Asaas, so a consumer never branches on which one it
is talking to.

**Money is integer cents, never float.** Stripe already reports amounts
in the smallest currency unit (cents for BRL/USD); Asaas reports Reais
as a decimal string ("150.00"). `Money.from_decimal_reais` is the ONE
legal place a `Decimal` amount is converted — every other path in this
package works in cents from the start. A float would silently drift on
arithmetic (0.1 + 0.2 != 0.3) and that drift is exactly the kind of bug
that shows up as "the ledger is off by one cent" three months later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any, Literal, Optional


class PaymentGatewayName(str, Enum):
    """Which vendor issued a `PaymentGateway`. Used for logging/metrics
    only — never for branching in consumer code (that defeats the
    Protocol)."""

    STRIPE = "stripe"
    ASAAS = "asaas"


#: Normalized subscription lifecycle status as REPORTED BY THE GATEWAY.
#: This is deliberately narrower than `noctusai_lib.domain.payments`'s own
#: `SubscriptionState` — "grace" is a business decision this seed makes
#: on top of gateway data, not something either vendor reports natively.
GatewaySubscriptionStatus = Literal[
    "trialing",
    "active",
    "past_due",
    "canceled",
    "incomplete",
    "unpaid",
]


@dataclass(frozen=True)
class Money:
    """An amount as INTEGER CENTS + an explicit ISO-4217 currency code.

    Arithmetic refuses to mix currencies — adding BRL cents to USD cents
    silently would produce a number that means nothing.
    """

    amount_cents: int
    currency: str = "BRL"

    def __post_init__(self) -> None:
        if not isinstance(self.amount_cents, int) or isinstance(self.amount_cents, bool):
            raise TypeError(
                f"Money.amount_cents must be an int (cents), got "
                f"{type(self.amount_cents).__name__}: {self.amount_cents!r}"
            )
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError(
                f"Money.currency must be a 3-letter uppercase ISO-4217 code, "
                f"got {self.currency!r}"
            )

    def _check_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"currency mismatch: {self.currency} vs {other.currency}"
            )

    def __add__(self, other: "Money") -> "Money":
        self._check_currency(other)
        return Money(self.amount_cents + other.amount_cents, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check_currency(other)
        return Money(self.amount_cents - other.amount_cents, self.currency)

    @classmethod
    def from_decimal_reais(cls, value: Decimal, currency: str = "BRL") -> "Money":
        """Convert a `Decimal` amount in the major unit (e.g. Asaas'
        `"150.00"`) to integer cents. The ONE legal on-ramp for a
        `Decimal` amount into this package.
        """
        if not isinstance(value, Decimal):
            raise TypeError(f"expected Decimal, got {type(value).__name__}: {value!r}")
        cents = (value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return cls(int(cents), currency)

    def to_decimal(self) -> Decimal:
        """Back to the major unit, for display / vendor payloads that
        require it (e.g. Asaas' `value` field)."""
        return Decimal(self.amount_cents) / Decimal(100)


@dataclass(frozen=True)
class FeeBreakdown:
    """One charge's economics, normalized across gateways.

    `gross` is what the payer paid, `fee` is the gateway's cut, `net` is
    what lands in our account. The invariant `gross == fee + net` is
    enforced at construction — each gateway adapter computes `net` as
    `gross - fee` or vice-versa depending on what the vendor actually
    reports, but the object itself never allows the three to disagree.
    """

    gross: Money
    fee: Money
    net: Money

    def __post_init__(self) -> None:
        if not (self.gross.currency == self.fee.currency == self.net.currency):
            raise ValueError(
                "FeeBreakdown: gross/fee/net must share one currency, got "
                f"{self.gross.currency}/{self.fee.currency}/{self.net.currency}"
            )
        if self.gross.amount_cents != self.fee.amount_cents + self.net.amount_cents:
            raise ValueError(
                "FeeBreakdown invariant violated: gross("
                f"{self.gross.amount_cents}) != fee({self.fee.amount_cents}) + "
                f"net({self.net.amount_cents})"
            )


@dataclass(frozen=True)
class GatewayCustomer:
    """The payer, as the gateway knows them."""

    id_at_gateway: str
    external_reference: str  # our own org/customer id — the conciliation key
    email: str
    name: str


#: How often the subscription bills. Not every gateway supports every
#: cycle (Asaas has no native "weekly" for card, Stripe supports all
#: three) — the Real adapter is the one place that fact is allowed to
#: matter; a consumer never sees a gateway-specific cycle name.
BillingCycle = Literal["weekly", "monthly", "yearly"]

#: How the payer settles each cycle. Named after `products/p-studio`'s
#: `FormaCobranca` vocabulary (pix/boleto/cartao/indefinido) for the same
#: reason that module gives: Pix and boleto behave differently enough
#: (D+1 settlement, no chargebacks) that collapsing them into "card or
#: not" would hide real reconciliation differences.
BillingMethod = Literal["pix", "boleto", "card", "unspecified"]


@dataclass(frozen=True)
class SubscriptionRequest:
    """What we want to start charging. Zero gateway vocabulary.

    `plan_ref` is OPTIONAL and gateway-specific: Stripe's idiomatic flow
    bills against a pre-created `Price` object, so `StripePaymentGateway`
    REQUIRES it and raises rather than inventing an ad-hoc Product/Price
    pair. Asaas has no equivalent first-class price catalog — its
    adapter bills directly off `price`/`billing_cycle`/`billing_method`
    and ignores `plan_ref`. Both branches are the Real adapter's problem,
    never the caller's: the caller fills in every field it has and each
    gateway uses what applies to it.
    """

    external_reference: str  # our subscription/org id — the conciliation key
    customer_id_at_gateway: str
    price: Money
    billing_cycle: BillingCycle = "monthly"
    billing_method: BillingMethod = "unspecified"
    plan_ref: Optional[str] = None  # Stripe: a pre-created Price id
    metadata: dict[str, Any] = field(default_factory=dict)
    # Days before the first charge. 0 = charge now. Stripe maps it to
    # `trial_period_days`; Asaas has no trial concept, so its adapter
    # pushes the first `nextDueDate` forward by this many days instead.
    trial_days: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.trial_days, int) or isinstance(self.trial_days, bool):
            raise TypeError(f"trial_days must be an int, got {self.trial_days!r}")
        if self.trial_days < 0:
            raise ValueError(f"trial_days must be >= 0, got {self.trial_days}")


@dataclass(frozen=True)
class GatewaySubscription:
    """A subscription as the gateway reports it, translated to our lexicon."""

    id_at_gateway: str
    customer_id_at_gateway: str
    external_reference: Optional[str]
    status: GatewaySubscriptionStatus
    current_period_end: Optional[str] = None  # ISO-8601, when known
    latest_charge_id_at_gateway: Optional[str] = None
    # Raw payload. Forensic — the normalized fields are a lossy
    # projection and "what did the gateway actually send?" needs an
    # answer independent of how well this module's mapping aged.
    raw: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "BillingCycle",
    "BillingMethod",
    "FeeBreakdown",
    "GatewayCustomer",
    "GatewaySubscription",
    "GatewaySubscriptionStatus",
    "Money",
    "PaymentGatewayName",
    "SubscriptionRequest",
]
