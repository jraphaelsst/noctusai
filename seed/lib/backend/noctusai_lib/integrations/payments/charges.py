"""One-off charge operations -- read, refund, cancel, statement. Commerce P4.

A sibling of `.checkout.HostedCheckout` (which CREATES a charge and hands the
payer a URL): `ChargeOperations` is everything a merchant does to a charge
AFTER that -- `get_charge`, `refund_charge`, `cancel_charge` and the account
statement (`list_balance_transactions`). Contract: `projects/commerce-seed-p4/
CONTRACT.md` §1.1.

Shape = `HostedCheckout`'s: Protocol + `FakeChargeOperations` +
`AsaasChargeOperations` + `StripeChargeOperations` + `make_charge_operations`
(fake-or-refuse). The Real classes COMPOSE the existing `PaymentGateway`
adapters and reuse their HTTP / SDK plumbing (`_request`, `_stripe`, `_call`).

Rules baked in:

* **Never a silent default.** An unknown gateway status raises
  ``PaymentGatewayError(code="unknown_charge_status")``; an unknown payment
  method raises ``code="unknown_payment_method"``. A new vendor state must
  surface, not be guessed (the only catch-all is the statement's ``other`` kind,
  which both vendors document as open-ended).
* **Refund guard before the call.** ``refund_charge`` reads the charge and
  raises ``refund_exceeds_balance`` BEFORE calling out when the amount is above
  what is still refundable.
* **Paid charges are never cancelled.** ``cancel_charge`` on a paid charge
  raises ``charge_already_paid``; refund it instead.

Statuses, event names and the Asaas "dispute lost" signal are documented (with
source URLs) in ``ASAAS-EVENTS.md`` next to this file.
"""
from __future__ import annotations

import datetime as _dt
import logging
from decimal import Decimal
from typing import Any, Callable, Literal, Optional, Protocol, Union, runtime_checkable

import httpx

from ._stripe_fields import stripe_field, stripe_to_dict
from .errors import PaymentGatewayError
from .factory import make_payment_gateway
from .real_asaas import DEFAULT_BASE_URL as ASAAS_DEFAULT_BASE_URL
from .real_asaas import DEFAULT_TIMEOUT_SECONDS as ASAAS_DEFAULT_TIMEOUT_SECONDS
from .real_asaas import AsaasPaymentGateway
from .real_stripe import StripePaymentGateway
from .types import (
    BalanceTransaction,
    BalanceTransactionKind,
    BalanceTransactionPage,
    ChargeStatus,
    GatewayCharge,
    GatewayRefund,
    Money,
    PaymentGatewayName,
    PaymentMethod,
)

logger = logging.getLogger(__name__)

#: Statuses where money has been (at least once) captured: a cancel is refused.
_PAID_STATUSES: frozenset[str] = frozenset(
    {"confirmed", "received", "partially_refunded", "refunded", "disputed", "chargeback"}
)
#: Statuses a refund can start from (money is still with the merchant).
_REFUNDABLE_STATUSES: frozenset[str] = frozenset({"confirmed", "received", "partially_refunded"})

STATEMENT_PAGE_SIZE = 100


@runtime_checkable
class ChargeOperations(Protocol):
    """Read / refund / cancel a one-off charge, and list the account statement.

    ``charge_id_at_gateway`` is whatever the checkout returned as
    ``CheckoutSession.id_at_gateway`` (Asaas ``pay_...``; Stripe ``cs_...``),
    plus the ids a Stripe webhook carries (``pi_...`` / ``ch_...``).
    """

    name: PaymentGatewayName

    def get_charge(self, charge_id_at_gateway: str) -> GatewayCharge:
        """Read-only snapshot of the charge."""
        ...

    def refund_charge(
        self, charge_id_at_gateway: str, *, amount: Optional[Money], description: str
    ) -> GatewayRefund:
        """Refund ``amount`` (``None`` = the full remaining refundable).

        Above the refundable balance => ``PaymentGatewayError(code=
        "refund_exceeds_balance")`` BEFORE any refund call is made."""
        ...

    def cancel_charge(self, charge_id_at_gateway: str) -> GatewayCharge:
        """Cancel an UNPAID charge. Paid => ``code="charge_already_paid"``."""
        ...

    def get_installment(self, installment_id_at_gateway: str) -> GatewayCharge:
        """The WHOLE parcelamento as one charge: ``amount`` = sum of the parcelas, ``refunded`` = refunds across
        all of them, ``refunds`` = one entry per refund OPERATION (a parcelamento refund is spread over the
        parcelas by the gateway). Gateways without parcelamento => ``code="installments_unsupported"``."""
        ...

    def refund_installment(
        self, installment_id_at_gateway: str, *, amount: Optional[Money], description: str
    ) -> GatewayRefund:
        """Refund ``amount`` (``None`` = the full remaining) of a whole parcelamento -- the gateway spreads it.

        Above the refundable balance => ``code="refund_exceeds_balance"`` BEFORE any refund call is made."""
        ...

    def list_balance_transactions(
        self, *, since: _dt.date, cursor: Optional[str] = None
    ) -> BalanceTransactionPage:
        """The account statement from ``since`` (inclusive), one page per call."""
        ...


# ── shared helpers ───────────────────────────────────────────────────────


def _refundable(charge: GatewayCharge) -> Money:
    return charge.amount - charge.refunded


def _check_refund(
    gateway: str, charge: GatewayCharge, amount: Optional[Money]
) -> Money:
    """Resolve the amount to refund, or raise BEFORE any outbound refund call."""
    if charge.status not in _REFUNDABLE_STATUSES:
        raise PaymentGatewayError(
            gateway,
            f"charge {charge.id_at_gateway} is {charge.status!r} and cannot be refunded",
            code="charge_not_refundable",
        )
    remaining = _refundable(charge)
    if amount is None:
        amount = remaining
    if amount.currency != remaining.currency:
        raise PaymentGatewayError(
            gateway,
            f"refund currency {amount.currency} != charge currency {remaining.currency}",
            code="refund_currency_mismatch",
        )
    if amount.amount_cents <= 0 or amount.amount_cents > remaining.amount_cents:
        raise PaymentGatewayError(
            gateway,
            f"refund of {amount.amount_cents} exceeds the refundable balance "
            f"({remaining.amount_cents}) of charge {charge.id_at_gateway}",
            code="refund_exceeds_balance",
        )
    return amount


def _installments_unsupported(gateway: str) -> PaymentGatewayError:
    return PaymentGatewayError(
        gateway, "this gateway has no parcelamento: refund the charge itself", code="installments_unsupported"
    )


def _aggregate_installment(
    gateway: str, installment_id: str, parcelas: list[GatewayCharge]
) -> GatewayCharge:
    """Fold the parcelas of one parcelamento into a single `GatewayCharge` (shared by Fake and Asaas).

    Refunds are grouped by their timestamp: one refund OPERATION touches several parcelas with the same
    instant, and reads back as one `GatewayRefund` of the summed value (`pending` if any piece is)."""
    if not parcelas:
        raise PaymentGatewayError(
            gateway, f"installment {installment_id} has no payments", status=404, code="resource_missing"
        )
    currency = parcelas[0].amount.currency
    amount = Money(sum(p.amount.amount_cents for p in parcelas), currency)
    refunded = Money(sum(p.refunded.amount_cents for p in parcelas), currency)
    groups: dict[Optional[_dt.datetime], list[GatewayRefund]] = {}
    for parcela in parcelas:
        for refund in parcela.refunds:
            groups.setdefault(refund.created_at, []).append(refund)
    refunds = [
        GatewayRefund(
            id_at_gateway=None,
            charge_id_at_gateway=installment_id,
            amount=Money(sum(r.amount.amount_cents for r in items), currency),
            status="pending" if any(r.status == "pending" for r in items) else "done",
            created_at=created_at,
            raw={"parcelas": [r.raw for r in items]},
        )
        for created_at, items in sorted(groups.items(), key=lambda kv: (kv[0] is not None, kv[0] or _dt.datetime.min.replace(tzinfo=_dt.timezone.utc)))
    ]
    statuses = {p.status for p in parcelas}
    if "chargeback" in statuses:
        status: ChargeStatus = "chargeback"
    elif "disputed" in statuses:
        status = "disputed"
    elif refunded.amount_cents > 0 and refunded.amount_cents >= amount.amount_cents:
        status = "refunded"
    elif refunded.amount_cents > 0:
        status = "partially_refunded"
    elif statuses <= {"received"}:
        status = "received"
    elif statuses <= {"received", "confirmed"}:
        status = "confirmed"
    elif statuses == {"cancelled"}:
        status = "cancelled"
    else:  # a parcela still unpaid: the parcelamento is not (fully) paid, so it is not refundable
        status = next(p.status for p in parcelas if p.status not in ("received", "confirmed"))
    fees = [p.fee for p in parcelas]
    nets = [p.net for p in parcelas]
    first = parcelas[0]
    return GatewayCharge(
        id_at_gateway=installment_id,
        status=status,
        method=first.method,
        amount=amount,
        refunded=refunded,
        net=Money(sum(n.amount_cents for n in nets if n), currency) if all(nets) else None,
        fee=Money(sum(f.amount_cents for f in fees if f), currency) if all(fees) else None,
        refunds=refunds,
        installment_count=len(parcelas),
        due_date=min((p.due_date for p in parcelas if p.due_date), default=None),
        paid_at=first.paid_at,
        credit_date=first.credit_date,
        external_reference=first.external_reference,
        raw={"installment": installment_id, "payments": [p.id_at_gateway for p in parcelas]},
    )


def _unknown_status(gateway: str, what: str, value: Any) -> PaymentGatewayError:
    return PaymentGatewayError(
        gateway, f"unknown {what} {value!r}", code="unknown_charge_status"
    )


# ═════════════════════════════════════════════════════════════════════════
# Fake
# ═════════════════════════════════════════════════════════════════════════


class FakeChargeOperations:
    """In-memory `ChargeOperations` -- the executable example of the contract.

    Seed charges with `add_charge`, move them with `set_status` /
    `mark_paid` / `open_dispute` / `lose_dispute` / `win_dispute`, and read
    `calls` to assert on intent. Refund / cancel follow the same rules as the
    Real adapters (refund-exceeds-balance raised first, paid cannot be
    cancelled).
    """

    name = PaymentGatewayName.STRIPE  # arbitrary; consumer tests can override

    def __init__(self) -> None:
        self.charges: dict[str, GatewayCharge] = {}
        self.statement: list[BalanceTransaction] = []
        self.calls: list[tuple[str, object]] = []
        self._seq = 0
        self._disputed_from: dict[str, ChargeStatus] = {}
        self._last_refund_at: Optional[_dt.datetime] = None

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}_{self._seq:06d}"

    # ── test helpers ─────────────────────────────────────────────────

    def add_charge(
        self,
        charge_id: Optional[str] = None,
        *,
        amount: Money,
        status: ChargeStatus = "pending",
        method: PaymentMethod = "pix",
        installment_count: int = 1,
        external_reference: Optional[str] = None,
        fee: Optional[Money] = None,
        due_date: Optional[_dt.date] = None,
        installment_id: Optional[str] = None,
    ) -> GatewayCharge:
        """`installment_id` groups charges into one parcelamento (``raw["installment"]``, like Asaas); an
        `installment_count > 1` charge without one gets a fresh id and stands for the whole parcelamento."""
        charge_id = charge_id or self._next_id("pay")
        if installment_id is None and installment_count > 1:
            installment_id = self._next_id("ins")
        charge = GatewayCharge(
            id_at_gateway=charge_id,
            status=status,
            method=method,
            amount=amount,
            refunded=Money(0, amount.currency),
            net=(amount - fee) if fee is not None else None,
            fee=fee,
            installment_count=installment_count,
            due_date=due_date,
            external_reference=external_reference,
            raw={"installment": installment_id} if installment_id else {},
        )
        self.charges[charge_id] = charge
        return charge

    def _replace(self, charge_id: str, **changes: Any) -> GatewayCharge:
        current = self._require(charge_id)
        values = {f: getattr(current, f) for f in current.__dataclass_fields__}
        values.update(changes)
        updated = GatewayCharge(**values)
        self.charges[charge_id] = updated
        return updated

    def set_status(self, charge_id: str, status: ChargeStatus) -> GatewayCharge:
        return self._replace(charge_id, status=status)

    def mark_paid(
        self, charge_id: str, *, confirmed_only: bool = False, at: Optional[_dt.datetime] = None
    ) -> GatewayCharge:
        at = at or _dt.datetime.now(_dt.timezone.utc)
        return self._replace(
            charge_id,
            status="confirmed" if confirmed_only else "received",
            paid_at=at,
            credit_date=None if confirmed_only else at.date(),
        )

    def open_dispute(self, charge_id: str) -> GatewayCharge:
        current = self._require(charge_id)
        self._disputed_from[charge_id] = current.status
        return self._replace(charge_id, status="disputed")

    def win_dispute(self, charge_id: str) -> GatewayCharge:
        back = self._disputed_from.pop(charge_id, "received")
        return self._replace(charge_id, status=back)

    def lose_dispute(self, charge_id: str) -> GatewayCharge:
        self._disputed_from.pop(charge_id, None)
        return self._replace(charge_id, status="chargeback")

    def add_balance_transaction(self, item: BalanceTransaction) -> None:
        self.statement.append(item)

    def _require(self, charge_id: str) -> GatewayCharge:
        try:
            return self.charges[charge_id]
        except KeyError:
            raise PaymentGatewayError(
                "fake", f"no such charge {charge_id}", status=404, code="resource_missing"
            ) from None

    # ── ChargeOperations ─────────────────────────────────────────────

    def get_charge(self, charge_id_at_gateway: str) -> GatewayCharge:
        self.calls.append(("get_charge", charge_id_at_gateway))
        return self._require(charge_id_at_gateway)

    def refund_charge(
        self, charge_id_at_gateway: str, *, amount: Optional[Money], description: str
    ) -> GatewayRefund:
        self.calls.append(("refund_charge", (charge_id_at_gateway, amount, description)))
        charge = self._require(charge_id_at_gateway)
        value = _check_refund("fake", charge, amount)
        refund = GatewayRefund(
            id_at_gateway=self._next_id("re"),
            charge_id_at_gateway=charge_id_at_gateway,
            amount=value,
            status="done",
            created_at=_dt.datetime.now(_dt.timezone.utc),
            raw={"description": description},
        )
        refunded = charge.refunded + value
        self._replace(
            charge_id_at_gateway,
            refunded=refunded,
            refunds=[*charge.refunds, refund],
            status="refunded" if refunded.amount_cents >= charge.amount.amount_cents else "partially_refunded",
        )
        return refund

    def cancel_charge(self, charge_id_at_gateway: str) -> GatewayCharge:
        self.calls.append(("cancel_charge", charge_id_at_gateway))
        charge = self._require(charge_id_at_gateway)
        if charge.status in _PAID_STATUSES:
            raise PaymentGatewayError(
                "fake",
                f"charge {charge_id_at_gateway} is already paid",
                code="charge_already_paid",
            )
        return self._replace(charge_id_at_gateway, status="cancelled")

    def _parcelas(self, installment_id: str) -> list[GatewayCharge]:
        return [c for c in self.charges.values() if c.raw.get("installment") == installment_id]

    def get_installment(self, installment_id_at_gateway: str) -> GatewayCharge:
        self.calls.append(("get_installment", installment_id_at_gateway))
        return _aggregate_installment("fake", installment_id_at_gateway, self._parcelas(installment_id_at_gateway))

    def refund_installment(
        self, installment_id_at_gateway: str, *, amount: Optional[Money], description: str
    ) -> GatewayRefund:
        self.calls.append(("refund_installment", (installment_id_at_gateway, amount, description)))
        whole = _aggregate_installment("fake", installment_id_at_gateway, self._parcelas(installment_id_at_gateway))
        value = _check_refund("fake", whole, amount)
        now = _dt.datetime.now(_dt.timezone.utc)
        if self._last_refund_at is not None and now <= self._last_refund_at:
            now = self._last_refund_at + _dt.timedelta(microseconds=1)  # one instant per refund operation
        self._last_refund_at = now
        left = value.amount_cents
        for parcela in self._parcelas(installment_id_at_gateway):  # the gateway spreads it; here, in order
            take = min(left, parcela.amount.amount_cents - parcela.refunded.amount_cents)
            if take <= 0:
                continue
            piece = GatewayRefund(
                id_at_gateway=None,
                charge_id_at_gateway=parcela.id_at_gateway,
                amount=Money(take, value.currency),
                status="done",
                created_at=now,
                raw={"description": description},
            )
            refunded = parcela.refunded + piece.amount
            self._replace(
                parcela.id_at_gateway,
                refunded=refunded,
                refunds=[*parcela.refunds, piece],
                status="refunded" if refunded.amount_cents >= parcela.amount.amount_cents else "partially_refunded",
            )
            left -= take
        return GatewayRefund(
            id_at_gateway=None,
            charge_id_at_gateway=installment_id_at_gateway,
            amount=value,
            status="done",
            created_at=now,
            raw={"description": description},
        )

    def list_balance_transactions(
        self, *, since: _dt.date, cursor: Optional[str] = None
    ) -> BalanceTransactionPage:
        self.calls.append(("list_balance_transactions", (since, cursor)))
        rows = sorted(
            (t for t in self.statement if t.occurred_at.date() >= since),
            key=lambda t: (t.occurred_at, t.id_at_gateway),
        )
        start = int(cursor) if cursor else 0
        page = rows[start : start + STATEMENT_PAGE_SIZE]
        nxt = start + STATEMENT_PAGE_SIZE
        return BalanceTransactionPage(items=page, next_cursor=str(nxt) if nxt < len(rows) else None)


# ═════════════════════════════════════════════════════════════════════════
# Asaas
# ═════════════════════════════════════════════════════════════════════════

# Asaas `payment.status` (enum from docs.asaas.com/reference/recuperar-uma-
# unica-cobranca). A refund in flight leaves the money with the merchant, so
# it keeps reading as paid; the pending refund shows in `GatewayCharge.refunds`.
_ASAAS_STATUS_MAP: dict[str, ChargeStatus] = {
    "PENDING": "pending",
    "AWAITING_RISK_ANALYSIS": "pending",
    "CONFIRMED": "confirmed",
    "RECEIVED": "received",
    "RECEIVED_IN_CASH": "received",
    "OVERDUE": "overdue",
    "REFUND_REQUESTED": "received",
    "REFUND_IN_PROGRESS": "received",
    "REFUNDED": "refunded",
    "CHARGEBACK_REQUESTED": "disputed",
    "CHARGEBACK_DISPUTE": "disputed",
    "AWAITING_CHARGEBACK_REVERSAL": "disputed",
    "DUNNING_REQUESTED": "overdue",
    "DUNNING_RECEIVED": "received",
}

# `payment.chargeback.status` (docs.asaas.com/docs/chargeback).
_ASAAS_CHARGEBACK_OPEN = frozenset({"REQUESTED", "IN_DISPUTE"})

_ASAAS_METHOD_MAP: dict[str, PaymentMethod] = {
    "PIX": "pix",
    "BOLETO": "boleto",
    "CREDIT_CARD": "credit_card",
    "UNDEFINED": "undefined",
    "DEBIT_CARD": "other",
    "TRANSFER": "other",
    "DEPOSIT": "other",
}

_ASAAS_REFUND_STATUS_MAP: dict[str, Optional[Literal["pending", "done"]]] = {
    "DONE": "done",
    "PENDING": "pending",
    "AWAITING_CRITICAL_ACTION_AUTHORIZATION": "pending",
    "AWAITING_CUSTOMER_EXTERNAL_AUTHORIZATION": "pending",
    "CANCELLED": None,  # moved no money -- omitted
}


#: `payment.split[].status` (docs.asaas.com/reference/recuperar-uma-unica-cobranca). A split whose transfer
#: moved (or will move) money to the recipient gives its share back on a refund; the others moved nothing.
_ASAAS_SPLIT_LIVE = frozenset({"PENDING", "PROCESSING", "PROCESSING_REFUND", "AWAITING_CREDIT", "DONE"})
_ASAAS_SPLIT_DEAD = frozenset({"CANCELLED", "REFUSED", "REFUNDED", "BLOCKED_BY_VALUE_DIVERGENCE"})


def _asaas_money(value: Any) -> Money:
    return Money.from_decimal_reais(Decimal(str(value)))


def _asaas_split_refunds(charge: GatewayCharge, value: Money) -> list[dict[str, Any]]:
    """`splitRefunds` for refunding ``value`` of ``charge``: every live split gives back its share in
    proportion to the refund (owner decision 2026-10-14). Without it Asaas debits a partial refund from the
    main account alone, so the store would absorb the whole refund while the platform kept its full fee.

    The share is CUMULATIVE -- ``floor(total * refunded_after / amount) - floor(total * refunded_before /
    amount)`` -- so rounding never drifts: refunding the whole charge over several partial refunds returns
    exactly the split's ``totalValue``."""
    amount = charge.amount.amount_cents
    before = charge.refunded.amount_cents
    after = before + value.amount_cents
    out: list[dict[str, Any]] = []
    for split in charge.raw.get("split") or []:
        status = split.get("status")
        if status in _ASAAS_SPLIT_DEAD:
            continue
        if status not in _ASAAS_SPLIT_LIVE:
            raise _unknown_status("asaas", "split status", status)
        total = _asaas_money(split["totalValue"]).amount_cents
        share = total * after // amount - total * before // amount
        if share > 0:
            out.append({"id": split["id"], "value": float(Money(share, value.currency).to_decimal())})
    return out


def _asaas_dt(value: Any) -> Optional[_dt.datetime]:
    """Asaas timestamps are `YYYY-MM-DD[ HH:MM:SS]` (Brasilia wall time, no
    zone in the payload); they are labelled UTC as-is -- consumers use the
    DATE, not the hour."""
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    try:
        return _dt.datetime.fromisoformat(text).replace(tzinfo=_dt.timezone.utc)
    except ValueError:
        raise PaymentGatewayError(
            "asaas", f"unparseable date {value!r}", code="unknown_charge_status"
        ) from None


def _asaas_date(value: Any) -> Optional[_dt.date]:
    if not value:
        return None
    return _dt.date.fromisoformat(str(value)[:10])


class AsaasChargeOperations:
    """`ChargeOperations` over Asaas API v3 (`/payments`, `/financialTransactions`)."""

    name = PaymentGatewayName.ASAAS

    def __init__(self, gateway: AsaasPaymentGateway) -> None:
        self._gateway = gateway

    # mapping --------------------------------------------------------------

    def _to_refunds(self, charge_id: str, raw: dict[str, Any]) -> list[GatewayRefund]:
        refunds: list[GatewayRefund] = []
        for item in raw.get("refunds") or []:
            raw_status = item.get("status")
            if raw_status not in _ASAAS_REFUND_STATUS_MAP:
                raise _unknown_status("asaas", "refund status", raw_status)
            status = _ASAAS_REFUND_STATUS_MAP[raw_status]
            if status is None:
                continue
            refunds.append(
                GatewayRefund(
                    id_at_gateway=None,  # Asaas lists refunds without an id
                    charge_id_at_gateway=charge_id,
                    amount=_asaas_money(item["value"]),
                    status=status,
                    created_at=_asaas_dt(item.get("dateCreated")),
                    raw=item,
                )
            )
        return refunds

    def _map_status(self, raw: dict[str, Any], refunded: Money, amount: Money) -> ChargeStatus:
        if raw.get("deleted"):
            return "cancelled"
        raw_status = raw.get("status")
        if raw_status not in _ASAAS_STATUS_MAP:
            raise _unknown_status("asaas", "payment status", raw_status)
        status = _ASAAS_STATUS_MAP[raw_status]
        chargeback = raw.get("chargeback") or {}
        cb_status = chargeback.get("status")
        if cb_status == "DISPUTE_LOST":
            return "chargeback"
        if cb_status in _ASAAS_CHARGEBACK_OPEN:
            return "disputed"
        # REVERSED (dispute won) => the underlying status stands; DONE is not
        # specified by the docs beyond "process concluded", so it does not
        # override a non-chargeback payment status either.
        if cb_status is not None and cb_status not in ("REVERSED", "DONE"):
            raise _unknown_status("asaas", "chargeback status", cb_status)
        if status in ("confirmed", "received") and 0 < refunded.amount_cents < amount.amount_cents:
            return "partially_refunded"
        return status

    def _installment_count(self, raw: dict[str, Any]) -> int:
        installment_id = raw.get("installment")
        if not installment_id:
            return 1
        inst = self._gateway._request("GET", f"/installments/{installment_id}")
        return int(inst.get("installmentCount") or 1)

    def _to_charge(self, raw: dict[str, Any], *, installment_count: Optional[int] = None) -> GatewayCharge:
        charge_id = raw["id"]
        method_raw = raw.get("billingType")
        if method_raw not in _ASAAS_METHOD_MAP:
            raise PaymentGatewayError(
                "asaas", f"unknown billingType {method_raw!r}", code="unknown_payment_method"
            )
        amount = _asaas_money(raw["value"])
        refunds = self._to_refunds(charge_id, raw)
        refunded = Money(sum(r.amount.amount_cents for r in refunds), amount.currency)
        net = _asaas_money(raw["netValue"]) if raw.get("netValue") is not None else None
        return GatewayCharge(
            id_at_gateway=charge_id,
            status=self._map_status(raw, refunded, amount),
            method=_ASAAS_METHOD_MAP[method_raw],
            amount=amount,
            net=net,
            fee=(amount - net) if net is not None else None,
            refunded=refunded,
            refunds=refunds,
            installment_count=installment_count or self._installment_count(raw),
            due_date=_asaas_date(raw.get("dueDate")),
            paid_at=_asaas_dt(raw.get("paymentDate") or raw.get("confirmedDate")),
            credit_date=_asaas_date(raw.get("creditDate")),
            external_reference=raw.get("externalReference"),
            raw=raw,
        )

    # ChargeOperations ------------------------------------------------------

    def get_charge(self, charge_id_at_gateway: str) -> GatewayCharge:
        return self._to_charge(self._gateway._request("GET", f"/payments/{charge_id_at_gateway}"))

    def refund_charge(
        self, charge_id_at_gateway: str, *, amount: Optional[Money], description: str
    ) -> GatewayRefund:
        charge = self.get_charge(charge_id_at_gateway)
        value = _check_refund("asaas", charge, amount)  # raises before any refund call
        before = len(charge.refunds)
        body: dict[str, Any] = {"value": float(value.to_decimal()), "description": description}
        split_refunds = _asaas_split_refunds(charge, value)
        if split_refunds:
            body["splitRefunds"] = split_refunds
        raw = self._gateway._request("POST", f"/payments/{charge_id_at_gateway}/refund", json=body)
        refunds = self._to_refunds(charge_id_at_gateway, raw)
        if len(refunds) > before:
            return refunds[-1]
        # Asaas accepted the call but lists no new refund yet (async, e.g. Pix).
        return GatewayRefund(
            id_at_gateway=None,
            charge_id_at_gateway=charge_id_at_gateway,
            amount=value,
            status="pending",
            created_at=None,
            raw=raw,
        )

    def cancel_charge(self, charge_id_at_gateway: str) -> GatewayCharge:
        charge = self.get_charge(charge_id_at_gateway)
        if charge.status in _PAID_STATUSES:
            raise PaymentGatewayError(
                "asaas",
                f"charge {charge_id_at_gateway} is already paid ({charge.status})",
                code="charge_already_paid",
            )
        if charge.status == "cancelled":
            return charge
        self._gateway._request("DELETE", f"/payments/{charge_id_at_gateway}")
        # DELETE returns only {"deleted": true, "id": ...}; reflect it locally
        # (same approach as `cancel_subscription`) instead of re-reading.
        return self._to_charge({**charge.raw, "deleted": True})

    def _installment_parcelas(self, installment_id: str) -> list[GatewayCharge]:
        raws: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._gateway._request(
                "GET", f"/installments/{installment_id}/payments", params={"offset": offset, "limit": 100}
            )
            raws.extend(page.get("data") or [])
            if not page.get("hasMore"):
                break
            offset += 100
        return [self._to_charge(raw, installment_count=len(raws)) for raw in raws]

    def get_installment(self, installment_id_at_gateway: str) -> GatewayCharge:
        return _aggregate_installment(
            "asaas", installment_id_at_gateway, self._installment_parcelas(installment_id_at_gateway)
        )

    def refund_installment(
        self, installment_id_at_gateway: str, *, amount: Optional[Money], description: str
    ) -> GatewayRefund:
        # POST /v3/installments/{id}/refund takes only `value` (no description); value omitted = full refund.
        # NOC-REMEDIATE[commerce-installment-split-refund]: the endpoint takes no `splitRefunds`, so a PARTIAL
        # parcelamento refund does not return the platform split share proportionally (a single charge does, see
        # `_asaas_split_refunds`). Remedy: refund the parcelas one by one via /payments/{id}/refund with
        # splitRefunds -- lands with the installment-level charge model (commerce-installment-dispute, P9).
        whole = self.get_installment(installment_id_at_gateway)
        value = _check_refund("asaas", whole, amount)  # raises before any refund call
        before_refunded = whole.refunded.amount_cents
        before = len(whole.refunds)
        body = {} if amount is None and whole.refunded.amount_cents == 0 else {"value": float(value.to_decimal())}
        # From here on the POST may have succeeded at the gateway (a timeout is inconclusive per the Asaas docs).
        self._gateway._request("POST", f"/installments/{installment_id_at_gateway}/refund", json=body)
        pending = GatewayRefund(
            id_at_gateway=None,
            charge_id_at_gateway=installment_id_at_gateway,
            amount=value,
            status="pending",
            created_at=None,
            raw={"description": description},
        )
        # The response is the parcelamento, not the refund: read the refunds back (the parcelas carry them).
        # A failed read-back does NOT mean the refund failed: report `pending`, reconcile settles it from the totals.
        try:
            after = self.get_installment(installment_id_at_gateway)
        except PaymentGatewayError:
            logger.warning("asaas: installment %s refund POSTed but the read-back failed; reporting pending", installment_id_at_gateway)
            return pending
        # Decided from TOTALS: a refund groups by date-granular `dateCreated`, so the group count is unreliable.
        if after.refunded.amount_cents - before_refunded >= value.amount_cents:
            created = after.refunds[-1].created_at if len(after.refunds) > before else None
            return GatewayRefund(
                id_at_gateway=None, charge_id_at_gateway=installment_id_at_gateway, amount=value,
                status="done", created_at=created, raw={"description": description},
            )
        return pending

    @staticmethod
    def _statement_kind(asaas_type: str) -> BalanceTransactionKind:
        if asaas_type in (
            "PAYMENT_RECEIVED", "CARD_SALE_RECEIVED", "PIX_TRANSACTION_CREDIT", "PARTIAL_PAYMENT",
        ):
            return "charge"
        if asaas_type in ("CHARGEBACK", "CHARGEBACK_REVERSAL", "ASAAS_MONEY_TRANSACTION_CHARGEBACK",
                          "ASAAS_MONEY_TRANSACTION_CHARGEBACK_REVERSAL"):
            return "chargeback"
        if asaas_type in ("PAYMENT_REVERSAL", "PIX_TRANSACTION_CREDIT_REFUND", "CARD_SALE_REVERSAL",
                          "PAYMENT_REFUND_CANCELLED", "REFUND_REQUEST_CANCELLED"):
            return "refund"
        if asaas_type.endswith(("_FEE_REVERSAL", "_FEE_REFUND", "_FEE_CANCELLED")):
            return "adjustment"
        if asaas_type.endswith("_FEE") or asaas_type == "REFUND_REQUEST_FEE":
            return "fee"
        if asaas_type.startswith(("TRANSFER", "INTERNAL_TRANSFER")):
            return "transfer"
        if asaas_type in ("DEBIT", "CREDIT", "DEBIT_REVERSAL", "REVERSAL"):
            return "adjustment"
        return "other"  # Asaas documents the type list as open-ended

    def list_balance_transactions(
        self, *, since: _dt.date, cursor: Optional[str] = None
    ) -> BalanceTransactionPage:
        offset = int(cursor) if cursor else 0
        page = self._gateway._request(
            "GET",
            "/financialTransactions",
            params={
                "startDate": since.isoformat(),
                "offset": offset,
                "limit": STATEMENT_PAGE_SIZE,
                "order": "asc",
            },
        )
        items = [
            BalanceTransaction(
                id_at_gateway=row["id"],
                occurred_at=_asaas_dt(row["date"]),  # type: ignore[arg-type]
                kind=self._statement_kind(str(row.get("type"))),
                amount=_asaas_money(row["value"]),
                charge_id_at_gateway=row.get("paymentId"),
                description=row.get("description") or "",
                raw=row,
            )
            for row in page.get("data") or []
        ]
        has_more = bool(page.get("hasMore"))
        return BalanceTransactionPage(
            items=items, next_cursor=str(offset + STATEMENT_PAGE_SIZE) if has_more else None
        )


# ═════════════════════════════════════════════════════════════════════════
# Stripe
# ═════════════════════════════════════════════════════════════════════════

_STRIPE_PI_STATUSES_PENDING = frozenset(
    {"requires_payment_method", "requires_confirmation", "requires_action", "processing", "requires_capture"}
)
#: Dispute statuses that mean "money is contested right now".
_STRIPE_DISPUTE_OPEN = frozenset(
    {"warning_needs_response", "warning_under_review", "needs_response", "under_review"}
)
#: Dispute statuses that leave the charge as it was (inquiry closed / won).
_STRIPE_DISPUTE_NEUTRAL = frozenset({"won", "warning_closed", "prevented"})

_STRIPE_METHOD_MAP: dict[str, PaymentMethod] = {
    "card": "credit_card",
    "boleto": "boleto",
    "pix": "pix",
}

_STRIPE_REFUND_STATUS_MAP: dict[str, Optional[Literal["pending", "done"]]] = {
    "succeeded": "done",
    "pending": "pending",
    "requires_action": "pending",
    "failed": None,
    "canceled": None,
}


def _stripe_dt(ts: Any) -> Optional[_dt.datetime]:
    if ts is None:
        return None
    return _dt.datetime.fromtimestamp(int(ts), tz=_dt.timezone.utc)


class StripeChargeOperations:
    """`ChargeOperations` over the Stripe SDK (lazy import via the composed gateway).

    Accepts a Checkout Session id (``cs_``), a PaymentIntent id (``pi_``) or a
    Charge id (``ch_``) -- the three ids the seam and Stripe's webhooks hand out.
    ``now`` is a clock seam (confirmed vs received depends on the balance
    transaction's ``available_on``).
    """

    name = PaymentGatewayName.STRIPE

    def __init__(
        self,
        gateway: StripePaymentGateway,
        *,
        now: Optional[Callable[[], _dt.datetime]] = None,
    ) -> None:
        self._gateway = gateway
        self._now = now or (lambda: _dt.datetime.now(_dt.timezone.utc))

    # resolution --------------------------------------------------------------

    _EXPAND_CHARGE = ["balance_transaction", "dispute"]

    def _resolve(self, charge_id: str) -> tuple[Any, Any, Any]:
        """-> (session | None, payment_intent | None, charge | None)."""
        stripe = self._gateway._stripe()
        call = self._gateway._call
        if charge_id.startswith("cs_"):
            session = call(
                lambda: stripe.checkout.Session.retrieve(
                    charge_id,
                    expand=[
                        "payment_intent.latest_charge.balance_transaction",
                        "payment_intent.latest_charge.dispute",
                    ],
                )
            )
            pi = stripe_field(session, "payment_intent")
            if isinstance(pi, str):
                pi = call(
                    lambda: stripe.PaymentIntent.retrieve(
                        pi, expand=["latest_charge.balance_transaction", "latest_charge.dispute"]
                    )
                )
        elif charge_id.startswith("pi_"):
            session = None
            pi = call(
                lambda: stripe.PaymentIntent.retrieve(
                    charge_id, expand=["latest_charge.balance_transaction", "latest_charge.dispute"]
                )
            )
        elif charge_id.startswith("ch_"):
            session, pi = None, None
            charge = call(
                lambda: stripe.Charge.retrieve(charge_id, expand=self._EXPAND_CHARGE)
            )
            return session, pi, charge
        else:
            raise PaymentGatewayError(
                "stripe",
                f"unsupported charge id {charge_id!r} (expected cs_/pi_/ch_)",
                code="unsupported_charge_id",
            )
        charge = stripe_field(pi, "latest_charge") if pi is not None else None
        if isinstance(charge, str):
            charge = call(lambda: stripe.Charge.retrieve(charge, expand=self._EXPAND_CHARGE))
        return session, pi, charge

    # mapping -----------------------------------------------------------------

    def _status(self, session: Any, pi: Any, charge: Any) -> ChargeStatus:
        if charge is not None:
            dispute = stripe_field(charge, "dispute")
            if dispute is not None and not isinstance(dispute, str):
                d_status = stripe_field(dispute, "status")
                if d_status == "lost":
                    return "chargeback"
                if d_status in _STRIPE_DISPUTE_OPEN:
                    return "disputed"
                if d_status not in _STRIPE_DISPUTE_NEUTRAL:
                    raise _unknown_status("stripe", "dispute status", d_status)
            elif isinstance(dispute, str):
                # Unexpanded dispute id: we cannot tell lost from won -- refuse to guess.
                raise _unknown_status("stripe", "dispute (not expanded)", dispute)
            c_status = stripe_field(charge, "status")
            if c_status in ("pending", "failed"):
                return "pending"  # not paid; the checkout can still be retried
            if c_status != "succeeded":
                raise _unknown_status("stripe", "charge status", c_status)
            amount = int(stripe_field(charge, "amount", 0))
            refunded = int(stripe_field(charge, "amount_refunded", 0))
            if stripe_field(charge, "refunded") or (amount and refunded >= amount):
                return "refunded"
            if refunded > 0:
                return "partially_refunded"
            txn = stripe_field(charge, "balance_transaction")
            available_on = _stripe_dt(stripe_field(txn, "available_on")) if txn and not isinstance(txn, str) else None
            if available_on is not None and available_on > self._now():
                return "confirmed"
            return "received"
        if pi is not None:
            pi_status = stripe_field(pi, "status")
            if pi_status == "canceled":
                return "cancelled"
            if pi_status in _STRIPE_PI_STATUSES_PENDING:
                return "pending"
            raise _unknown_status("stripe", "payment_intent status", pi_status)
        s_status = stripe_field(session, "status")
        if s_status == "open":
            return "pending"
        if s_status == "expired":
            return "cancelled"
        if s_status == "complete":
            pay = stripe_field(session, "payment_status")
            if pay in ("paid", "no_payment_required"):
                return "received"
            if pay == "unpaid":
                return "pending"
            raise _unknown_status("stripe", "session payment_status", pay)
        raise _unknown_status("stripe", "session status", s_status)

    def _method(self, session: Any, pi: Any, charge: Any) -> PaymentMethod:
        raw_type: Optional[str] = None
        if charge is not None:
            raw_type = stripe_field(stripe_field(charge, "payment_method_details"), "type")
        if raw_type is None and session is not None:
            types_ = stripe_field(session, "payment_method_types") or []
            raw_type = types_[0] if types_ else None
        if raw_type is None and pi is not None:
            types_ = stripe_field(pi, "payment_method_types") or []
            raw_type = types_[0] if types_ else None
        if raw_type not in _STRIPE_METHOD_MAP:
            raise PaymentGatewayError(
                "stripe", f"unknown payment method {raw_type!r}", code="unknown_payment_method"
            )
        return _STRIPE_METHOD_MAP[raw_type]

    def _refunds(self, charge_id: str) -> list[GatewayRefund]:
        stripe = self._gateway._stripe()
        listing = self._gateway._call(lambda: stripe.Refund.list(charge=charge_id, limit=100))
        out: list[GatewayRefund] = []
        for item in listing.data:
            raw_status = stripe_field(item, "status")
            if raw_status not in _STRIPE_REFUND_STATUS_MAP:
                raise _unknown_status("stripe", "refund status", raw_status)
            status = _STRIPE_REFUND_STATUS_MAP[raw_status]
            if status is None:
                continue
            out.append(
                GatewayRefund(
                    id_at_gateway=stripe_field(item, "id"),
                    charge_id_at_gateway=charge_id,
                    amount=Money(int(stripe_field(item, "amount")), str(stripe_field(item, "currency")).upper()),
                    status=status,
                    created_at=_stripe_dt(stripe_field(item, "created")),
                    raw=stripe_to_dict(item),
                )
            )
        return out

    def _build(self, requested_id: str, session: Any, pi: Any, charge: Any) -> GatewayCharge:
        status = self._status(session, pi, charge)
        source = charge if charge is not None else (pi if pi is not None else session)
        currency = str(
            stripe_field(source, "currency") or stripe_field(session, "currency") or "BRL"
        ).upper()
        if charge is not None:
            cents = int(stripe_field(charge, "amount"))
        elif pi is not None:
            cents = int(stripe_field(pi, "amount"))
        else:
            cents = int(stripe_field(session, "amount_total", 0) or 0)
        amount = Money(cents, currency)
        net = fee = None
        credit_date = None
        refunds: list[GatewayRefund] = []
        refunded = Money(0, currency)
        paid_at = None
        if charge is not None:
            txn = stripe_field(charge, "balance_transaction")
            if txn is not None and not isinstance(txn, str):
                fee = Money(int(stripe_field(txn, "fee")), currency)
                net = Money(int(stripe_field(txn, "net")), currency)
                available = _stripe_dt(stripe_field(txn, "available_on"))
                credit_date = available.date() if available else None
            if stripe_field(charge, "status") == "succeeded":
                paid_at = _stripe_dt(stripe_field(charge, "created"))
            refunds = self._refunds(stripe_field(charge, "id"))
            refunded = Money(int(stripe_field(charge, "amount_refunded", 0)), currency)
        metadata = stripe_field(source, "metadata") or {}
        external_reference = (
            stripe_field(metadata, "external_reference")
            or stripe_field(session, "client_reference_id")
        )
        return GatewayCharge(
            id_at_gateway=requested_id,
            status=status,
            method=self._method(session, pi, charge),
            amount=amount,
            net=net,
            fee=fee,
            refunded=refunded,
            refunds=refunds,
            installment_count=1,
            due_date=None,
            paid_at=paid_at,
            credit_date=credit_date,
            external_reference=external_reference,
            raw={
                "session": stripe_to_dict(session),
                "payment_intent": stripe_to_dict(pi),
                "charge": stripe_to_dict(charge),
            },
        )

    # ChargeOperations ------------------------------------------------------

    def get_charge(self, charge_id_at_gateway: str) -> GatewayCharge:
        session, pi, charge = self._resolve(charge_id_at_gateway)
        return self._build(charge_id_at_gateway, session, pi, charge)

    def refund_charge(
        self, charge_id_at_gateway: str, *, amount: Optional[Money], description: str
    ) -> GatewayRefund:
        session, pi, charge = self._resolve(charge_id_at_gateway)
        snapshot = self._build(charge_id_at_gateway, session, pi, charge)
        value = _check_refund("stripe", snapshot, amount)  # raises before any refund call
        if charge is None:  # pragma: no cover - _check_refund refuses unpaid charges first
            raise PaymentGatewayError("stripe", "no charge to refund", code="charge_not_refundable")
        stripe = self._gateway._stripe()
        real_charge_id = stripe_field(charge, "id")
        created = self._gateway._call(
            lambda: stripe.Refund.create(
                charge=real_charge_id,
                amount=value.amount_cents,
                metadata={"description": description[:500]},
            )
        )
        raw_status = stripe_field(created, "status")
        if raw_status not in _STRIPE_REFUND_STATUS_MAP or _STRIPE_REFUND_STATUS_MAP[raw_status] is None:
            raise _unknown_status("stripe", "refund status", raw_status)
        return GatewayRefund(
            id_at_gateway=stripe_field(created, "id"),
            charge_id_at_gateway=charge_id_at_gateway,
            amount=value,
            status=_STRIPE_REFUND_STATUS_MAP[raw_status],  # type: ignore[arg-type]
            created_at=_stripe_dt(stripe_field(created, "created")),
            raw=stripe_to_dict(created),
        )

    def get_installment(self, installment_id_at_gateway: str) -> GatewayCharge:
        raise _installments_unsupported("stripe")

    def refund_installment(
        self, installment_id_at_gateway: str, *, amount: Optional[Money], description: str
    ) -> GatewayRefund:
        raise _installments_unsupported("stripe")

    def cancel_charge(self, charge_id_at_gateway: str) -> GatewayCharge:
        session, pi, charge = self._resolve(charge_id_at_gateway)
        snapshot = self._build(charge_id_at_gateway, session, pi, charge)
        if snapshot.status in _PAID_STATUSES:
            raise PaymentGatewayError(
                "stripe",
                f"charge {charge_id_at_gateway} is already paid ({snapshot.status})",
                code="charge_already_paid",
            )
        if snapshot.status == "cancelled":
            return snapshot
        stripe = self._gateway._stripe()
        call = self._gateway._call
        if charge_id_at_gateway.startswith("cs_"):
            call(lambda: stripe.checkout.Session.expire(charge_id_at_gateway))
        elif pi is not None:
            call(lambda: stripe.PaymentIntent.cancel(stripe_field(pi, "id")))
        else:
            raise PaymentGatewayError(
                "stripe",
                f"charge {charge_id_at_gateway} has no cancellable session or payment intent",
                code="charge_not_cancellable",
            )
        return self._build(charge_id_at_gateway, *self._resolve(charge_id_at_gateway))

    @staticmethod
    def _statement_kind(txn: Any) -> BalanceTransactionKind:
        category = stripe_field(txn, "reporting_category")
        if category in ("charge",):
            return "charge"
        if category in ("fee", "network_cost"):
            return "fee"
        if category == "refund":
            return "refund"
        if category in ("dispute", "dispute_reversal"):
            return "chargeback"
        if category in ("payout", "payout_reversal", "transfer", "transfer_reversal"):
            return "transfer"
        if category in ("other_adjustment", "fx_fee") or stripe_field(txn, "type") == "adjustment":
            return "adjustment"
        return "other"

    def list_balance_transactions(
        self, *, since: _dt.date, cursor: Optional[str] = None
    ) -> BalanceTransactionPage:
        stripe = self._gateway._stripe()
        since_ts = int(_dt.datetime.combine(since, _dt.time.min, tzinfo=_dt.timezone.utc).timestamp())
        params: dict[str, Any] = {
            "created": {"gte": since_ts},
            "limit": STATEMENT_PAGE_SIZE,
            "expand": ["data.source"],
        }
        if cursor:
            params["starting_after"] = cursor
        listing = self._gateway._call(lambda: stripe.BalanceTransaction.list(**params))
        items: list[BalanceTransaction] = []
        for txn in listing.data:
            kind = self._statement_kind(txn)
            currency = str(stripe_field(txn, "currency")).upper()
            occurred = _stripe_dt(stripe_field(txn, "created"))
            source = stripe_field(txn, "source")
            charge_id: Optional[str] = None
            if isinstance(source, str):
                charge_id = source if source.startswith("ch_") else None
            elif source is not None:
                src_obj = stripe_field(source, "object")
                charge_id = (
                    stripe_field(source, "id") if src_obj == "charge" else stripe_field(source, "charge")
                )
                if charge_id is not None and not isinstance(charge_id, str):
                    charge_id = stripe_field(charge_id, "id")
            base = dict(
                occurred_at=occurred,
                charge_id_at_gateway=charge_id,
                description=stripe_field(txn, "description") or "",
                raw=stripe_to_dict(txn),
            )
            items.append(
                BalanceTransaction(
                    id_at_gateway=stripe_field(txn, "id"),
                    kind=kind,
                    amount=Money(int(stripe_field(txn, "amount")), currency),
                    **base,  # type: ignore[arg-type]
                )
            )
            fee_cents = int(stripe_field(txn, "fee", 0) or 0)
            if kind == "charge" and fee_cents:
                items.append(
                    BalanceTransaction(
                        id_at_gateway=f"{stripe_field(txn, 'id')}:fee",
                        kind="fee",
                        amount=Money(-fee_cents, currency),
                        **base,  # type: ignore[arg-type]
                    )
                )
        next_cursor = (
            stripe_field(listing.data[-1], "id") if getattr(listing, "has_more", False) and listing.data else None
        )
        return BalanceTransactionPage(items=items, next_cursor=next_cursor)


# ═════════════════════════════════════════════════════════════════════════
# Factory
# ═════════════════════════════════════════════════════════════════════════


def make_charge_operations(
    *,
    provider: Union[PaymentGatewayName, str, None] = None,
    use_fake: bool = False,
    stripe_api_key: Optional[str] = None,
    asaas_api_key: Optional[str] = None,
    asaas_base_url: str = ASAAS_DEFAULT_BASE_URL,
    asaas_timeout_seconds: float = ASAAS_DEFAULT_TIMEOUT_SECONDS,
    asaas_transport: Optional[httpx.BaseTransport] = None,
) -> Union[FakeChargeOperations, StripeChargeOperations, AsaasChargeOperations]:
    """Build a `ChargeOperations`. Mirrors `make_hosted_checkout`: same args,
    same validation (delegated to `make_payment_gateway`), fake-or-refuse --
    a missing provider / key raises ``ValueError``, never a silent Fake."""
    if use_fake:
        return FakeChargeOperations()
    gateway = make_payment_gateway(
        provider=provider,
        stripe_api_key=stripe_api_key,
        asaas_api_key=asaas_api_key,
        asaas_base_url=asaas_base_url,
        asaas_timeout_seconds=asaas_timeout_seconds,
        asaas_transport=asaas_transport,
    )
    if isinstance(gateway, StripePaymentGateway):
        return StripeChargeOperations(gateway)
    if isinstance(gateway, AsaasPaymentGateway):
        return AsaasChargeOperations(gateway)
    raise ValueError(  # pragma: no cover - make_payment_gateway already validates
        f"make_charge_operations: unsupported gateway {gateway!r}"
    )


__all__ = [
    "AsaasChargeOperations",
    "ChargeOperations",
    "FakeChargeOperations",
    "STATEMENT_PAGE_SIZE",
    "StripeChargeOperations",
    "make_charge_operations",
]
