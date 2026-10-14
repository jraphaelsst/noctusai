"""`CheckoutRequest.installment_count` + `customer_reference` (commerce P4, §1.2)."""
from __future__ import annotations

import json as json_lib
from typing import Any

import httpx
import pytest

from noctusai_lib.integrations.payments.checkout import (
    AsaasHostedCheckout,
    CheckoutRequest,
    StripeHostedCheckout,
)
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.real_asaas import AsaasPaymentGateway
from noctusai_lib.integrations.payments.real_stripe import StripePaymentGateway
from noctusai_lib.integrations.payments.types import Money


def _one_off(**over: Any) -> CheckoutRequest:
    base: dict[str, Any] = dict(
        external_reference="order-1", email="a@b.com", name="Ana", price=Money(30000),
        billing_cycle=None, billing_method="card", tax_id="12345678909",
        success_url="https://x.test/ok", cancel_url="https://x.test/no",
    )
    base.update(over)
    return CheckoutRequest(**base)


def test_defaults_are_backward_compatible() -> None:
    req = _one_off()
    assert req.installment_count == 1 and req.customer_reference is None
    assert req.customer_key == "order-1"
    assert _one_off(customer_reference="buyer-9").customer_key == "buyer-9"


@pytest.mark.parametrize(
    "over",
    [
        dict(installment_count=0),
        dict(installment_count=3, billing_method="pix"),
        dict(installment_count=3, billing_cycle="monthly"),
    ],
)
def test_installment_count_validation(over: dict) -> None:
    with pytest.raises(ValueError):
        _one_off(**over)


def _asaas_checkout(captured: list[tuple[str, str, dict]]) -> AsaasHostedCheckout:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json_lib.loads(request.content) if request.content else {}
        captured.append((request.method, request.url.path, body))
        if request.method == "GET" and request.url.path == "/v3/customers":
            return httpx.Response(200, json={"data": []})
        if request.method == "POST" and request.url.path == "/v3/customers":
            return httpx.Response(200, json={"id": "cus_1"})
        if request.method == "POST" and request.url.path == "/v3/payments":
            return httpx.Response(200, json={"id": "pay_1", "invoiceUrl": "https://asaas.test/i/pay_1"})
        return httpx.Response(404, json={"errors": [{"description": "no route"}]})

    return AsaasHostedCheckout(AsaasPaymentGateway(api_key="k", transport=httpx.MockTransport(handler)))


def test_asaas_one_off_installments_send_count_and_total_value() -> None:
    captured: list = []
    _asaas_checkout(captured).create_checkout(_one_off(installment_count=6))
    body = next(b for m, p, b in captured if m == "POST" and p == "/v3/payments")
    assert body["installmentCount"] == 6 and body["totalValue"] == 300.0
    assert "value" not in body


def test_asaas_one_off_single_payment_unchanged() -> None:
    captured: list = []
    _asaas_checkout(captured).create_checkout(_one_off())
    body = next(b for m, p, b in captured if m == "POST" and p == "/v3/payments")
    assert body["value"] == 300.0 and "installmentCount" not in body and "totalValue" not in body


def test_asaas_customer_is_keyed_on_customer_reference() -> None:
    captured: list = []
    _asaas_checkout(captured).create_checkout(_one_off(customer_reference="buyer-9"))
    create = next(b for m, p, b in captured if m == "POST" and p == "/v3/customers")
    assert create["externalReference"] == "buyer-9"
    payment = next(b for m, p, b in captured if m == "POST" and p == "/v3/payments")
    assert payment["externalReference"] == "order-1"  # still the per-charge key


def test_stripe_refuses_installments_before_calling_out() -> None:
    checkout = StripeHostedCheckout(StripePaymentGateway(api_key="sk_test"))
    with pytest.raises(PaymentGatewayError) as exc:
        checkout.create_checkout(_one_off(installment_count=3))
    assert exc.value.code == "installments_unsupported"
