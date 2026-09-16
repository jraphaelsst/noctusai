"""The Asaas-backed `PaymentGateway`.

Self-contained: it does NOT import `products/p-studio`'s existing
`ClienteHTTP`/`ProvedorAsaas` (product code is never a seed dependency),
but the status vocabulary below is lifted verbatim from that adapter's
`_STATUS` map — those raw Asaas strings were confirmed against the live
sandbox (see that module's docstring), and re-deriving them from
scratch here would be re-guessing a fact already paid for once.

Amounts: Asaas reports Reais as a decimal string (`"150.00"`), never
cents — `Money.from_decimal_reais` is the conversion boundary, matching
the ONE legal on-ramp documented in `types.py`.

Subscription status: Asaas' `Subscription` object itself only reports a
coarse `ACTIVE` / `EXPIRED` / `INACTIVE` — nothing as granular as
Stripe's `past_due`. That coarseness is a real product-of-record fact,
not a modeling shortcut this adapter invented; a consumer that needs
finer-grained payment health should inspect the subscription's generated
`Payment` rows (`status` per the vocabulary below) directly, the same
way `products/p-studio` already does for one-off charges.
"""
from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from typing import Any, Callable, Optional

import httpx

from .errors import PaymentGatewayError
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

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.asaas.com/v3"
DEFAULT_TIMEOUT_SECONDS = 15.0

# Asaas `Subscription.status` → our normalized vocabulary. Coarse by
# construction (see module docstring) — `INACTIVE` covers both "never
# billed" and "manually deactivated", which Asaas itself does not
# distinguish at the subscription level.
_SUBSCRIPTION_STATUS_MAP: dict[str, GatewaySubscriptionStatus] = {
    "ACTIVE": "active",
    "EXPIRED": "canceled",
    "INACTIVE": "incomplete",
}

_CYCLE_MAP: dict[BillingCycle, str] = {
    "weekly": "WEEKLY",
    "monthly": "MONTHLY",
    "yearly": "YEARLY",
}

_BILLING_METHOD_MAP: dict[BillingMethod, str] = {
    "pix": "PIX",
    "boleto": "BOLETO",
    "card": "CREDIT_CARD",
    "unspecified": "UNDEFINED",
}


class AsaasPaymentGateway:
    """Real `PaymentGateway` over the Asaas API v3.

    `transport` is a test seam (an `httpx.MockTransport`) so suites
    exercise the real `_request` path without monkey-patching, matching
    `noctusai_lib.integrations.mailchimp.HttpxMailchimpClient`.
    """

    name = PaymentGatewayName.ASAAS

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: Optional[httpx.BaseTransport] = None,
        today: Optional[Callable[[], datetime.date]] = None,
    ) -> None:
        if not api_key:
            raise ValueError("AsaasPaymentGateway requires a non-empty api_key")
        # Clock seam: `nextDueDate` is computed from "today", and a trial
        # pushes it forward — tests pin the date instead of racing it.
        self._today = today or datetime.date.today
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={"access_token": api_key, "Content-Type": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    # ── HTTP primitive ───────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise PaymentGatewayError(
                "asaas", f"timeout calling {path}", retryable=True
            ) from exc
        except httpx.TransportError as exc:
            raise PaymentGatewayError(
                "asaas", f"transport error calling {path}: {exc}", retryable=True
            ) from exc

        if response.status_code >= 400:
            body: dict[str, Any] = {}
            try:
                body = response.json()
            except ValueError:
                pass
            errors = body.get("errors") or []
            message = errors[0].get("description") if errors else response.text[:200]
            raise PaymentGatewayError(
                "asaas",
                str(message),
                status=response.status_code,
                code=(errors[0].get("code") if errors else None),
                retryable=response.status_code >= 500,
            )
        if not response.content:
            return {}
        return response.json()

    # ── mapping helpers ──────────────────────────────────────────────

    @staticmethod
    def _map_subscription_status(raw_status: str) -> GatewaySubscriptionStatus:
        return _SUBSCRIPTION_STATUS_MAP.get(raw_status, "incomplete")

    def _to_gateway_subscription(self, raw: dict[str, Any]) -> GatewaySubscription:
        return GatewaySubscription(
            id_at_gateway=raw["id"],
            customer_id_at_gateway=raw["customer"],
            external_reference=raw.get("externalReference"),
            status=self._map_subscription_status(raw["status"]),
            current_period_end=raw.get("nextDueDate"),
            latest_charge_id_at_gateway=None,  # Asaas doesn't return this inline
            raw=raw,
        )

    # ── PaymentGateway ───────────────────────────────────────────────

    def ensure_customer(
        self,
        *,
        external_reference: str,
        email: str,
        name: str,
        tax_id: Optional[str] = None,
    ) -> GatewayCustomer:
        found = self._request(
            "GET", "/customers", params={"externalReference": external_reference}
        )
        existing = (found.get("data") or [])
        if existing:
            row = existing[0]
            return GatewayCustomer(
                id_at_gateway=row["id"],
                external_reference=external_reference,
                email=row.get("email") or email,
                name=row.get("name") or name,
            )
        body: dict[str, Any] = {
            "name": name,
            "email": email,
            "externalReference": external_reference,
        }
        if tax_id:
            # Asaas refuses to issue a charge for a customer without a
            # CPF/CNPJ — the customer row itself is accepted without one,
            # which is why the failure otherwise surfaces far later.
            body["cpfCnpj"] = tax_id
        created = self._request("POST", "/customers", json=body)
        return GatewayCustomer(
            id_at_gateway=created["id"],
            external_reference=external_reference,
            email=email,
            name=name,
        )

    def create_subscription(self, request: SubscriptionRequest) -> GatewaySubscription:
        # Asaas has no trial concept: a trial is the first due date moved
        # forward by `trial_days`.
        first_due = self._today() + datetime.timedelta(days=request.trial_days)
        payload = {
            "customer": request.customer_id_at_gateway,
            "billingType": _BILLING_METHOD_MAP[request.billing_method],
            "value": float(request.price.to_decimal()),
            "cycle": _CYCLE_MAP[request.billing_cycle],
            "nextDueDate": first_due.isoformat(),
            "externalReference": request.external_reference,
        }
        created = self._request("POST", "/subscriptions", json=payload)
        subscription = self._to_gateway_subscription(created)
        if request.trial_days > 0:
            # Asaas reports ACTIVE; in our vocabulary a subscription whose
            # first charge is still days away is trialing.
            subscription = GatewaySubscription(
                id_at_gateway=subscription.id_at_gateway,
                customer_id_at_gateway=subscription.customer_id_at_gateway,
                external_reference=subscription.external_reference,
                status="trialing",
                current_period_end=subscription.current_period_end,
                latest_charge_id_at_gateway=None,
                raw=subscription.raw,
            )
        return subscription

    def verify_credentials(self) -> None:
        # A one-row customer list: read-only, and 401s on a bad key (or
        # `invalid_environment` when a production key hits the sandbox).
        self._request("GET", "/customers", params={"limit": 1})

    def get_subscription(self, id_at_gateway: str) -> GatewaySubscription:
        raw = self._request("GET", f"/subscriptions/{id_at_gateway}")
        return self._to_gateway_subscription(raw)

    def cancel_subscription(self, id_at_gateway: str) -> GatewaySubscription:
        # Asaas' DELETE returns only `{"deleted": true, "id": ...}` — fetch
        # the full row first so the caller still gets a complete
        # `GatewaySubscription`, then mark it canceled locally rather than
        # re-fetching (Asaas may take a moment to reflect EXPIRED).
        raw = self._request("GET", f"/subscriptions/{id_at_gateway}")
        self._request("DELETE", f"/subscriptions/{id_at_gateway}")
        canceled = dict(raw)
        canceled["status"] = "EXPIRED"
        return self._to_gateway_subscription(canceled)

    def get_fee_breakdown(self, charge_id_at_gateway: str) -> FeeBreakdown:
        raw = self._request("GET", f"/payments/{charge_id_at_gateway}")
        gross_value = Decimal(str(raw["value"]))
        net_value = Decimal(str(raw["netValue"]))
        gross = Money.from_decimal_reais(gross_value)
        net = Money.from_decimal_reais(net_value)
        fee = gross - net
        return FeeBreakdown(gross=gross, fee=fee, net=net)


__all__ = ["AsaasPaymentGateway", "DEFAULT_BASE_URL", "DEFAULT_TIMEOUT_SECONDS"]
