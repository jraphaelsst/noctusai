"""`AsaasPaymentGateway` — httpx.MockTransport, no network.

Mirrors `tests/integrations/mailchimp/test_client.py`'s MockTransport
convention: the REAL `_request` path runs end-to-end (headers, URL
construction, JSON decoding, error mapping); only the transport socket
is swapped.
"""
from __future__ import annotations

import json as json_lib
from typing import Any, Callable

import httpx
import pytest

from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.real_asaas import AsaasPaymentGateway
from noctusai_lib.integrations.payments.types import Money, SubscriptionRequest


def _routed_transport(routes: dict[str, Callable[[httpx.Request], httpx.Response]]) -> httpx.MockTransport:
    """`routes` maps `"<METHOD> <path>"` to a handler. Unmatched requests 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url.path}"
        route = routes.get(key)
        if route is None:
            return httpx.Response(404, json={"errors": [{"description": "no route"}]})
        return route(request)

    return httpx.MockTransport(handler)


def _json(status: int, body: dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=json_lib.dumps(body).encode())

    return handler


def test_sends_access_token_header() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.method == "GET":
            return httpx.Response(200, content=json_lib.dumps({"data": []}).encode())
        return httpx.Response(200, content=json_lib.dumps({"id": "cus_new"}).encode())

    gateway = AsaasPaymentGateway(
        api_key="secret-key", transport=httpx.MockTransport(handler)
    )
    gateway.ensure_customer(external_reference="org-1", email="a@b.com", name="Ana")
    assert captured[0].headers["access_token"] == "secret-key"


def test_ensure_customer_reuses_existing() -> None:
    transport = _routed_transport(
        {
            "GET /v3/customers": _json(
                200,
                {
                    "data": [
                        {"id": "cus_existing", "email": "a@b.com", "name": "Ana"}
                    ]
                },
            ),
        }
    )
    gateway = AsaasPaymentGateway(api_key="key", transport=transport)
    customer = gateway.ensure_customer(external_reference="org-1", email="a@b.com", name="Ana")
    assert customer.id_at_gateway == "cus_existing"


def test_ensure_customer_creates_new_when_absent() -> None:
    transport = _routed_transport(
        {
            "GET /v3/customers": _json(200, {"data": []}),
            "POST /v3/customers": _json(200, {"id": "cus_new"}),
        }
    )
    gateway = AsaasPaymentGateway(api_key="key", transport=transport)
    customer = gateway.ensure_customer(external_reference="org-1", email="a@b.com", name="Ana")
    assert customer.id_at_gateway == "cus_new"


def test_create_subscription_maps_active_status() -> None:
    transport = _routed_transport(
        {
            "POST /v3/subscriptions": _json(
                200,
                {
                    "id": "sub_1",
                    "customer": "cus_1",
                    "status": "ACTIVE",
                    "externalReference": "org-1",
                    "nextDueDate": "2026-10-01",
                },
            ),
        }
    )
    gateway = AsaasPaymentGateway(api_key="key", transport=transport)
    subscription = gateway.create_subscription(
        SubscriptionRequest(
            external_reference="org-1",
            customer_id_at_gateway="cus_1",
            price=Money(15000, "BRL"),
            billing_method="pix",
        )
    )
    assert subscription.status == "active"
    assert subscription.external_reference == "org-1"


def test_create_subscription_trial_moves_first_due_date_and_reports_trialing() -> None:
    import datetime

    seen: dict[str, Any] = {}

    def create(request: httpx.Request) -> httpx.Response:
        seen["body"] = json_lib.loads(request.content)
        return httpx.Response(
            200,
            content=json_lib.dumps(
                {"id": "sub_9", "customer": "cus_1", "status": "ACTIVE", "nextDueDate": "2026-09-24"}
            ).encode(),
        )

    transport = _routed_transport(
        {
            "POST /v3/subscriptions": create,
        }
    )
    gateway = AsaasPaymentGateway(
        api_key="key", transport=transport, today=lambda: datetime.date(2026, 9, 17)
    )
    subscription = gateway.create_subscription(
        SubscriptionRequest(
            external_reference="org-1",
            customer_id_at_gateway="cus_1",
            price=Money(9900, "BRL"),
            billing_method="card",
            trial_days=7,
        )
    )
    assert seen["body"]["nextDueDate"] == "2026-09-24"
    assert seen["body"]["billingType"] == "CREDIT_CARD"
    assert subscription.status == "trialing"


def test_ensure_customer_sends_tax_id_as_cpf_cnpj() -> None:
    seen: dict[str, Any] = {}

    def create(request: httpx.Request) -> httpx.Response:
        seen["body"] = json_lib.loads(request.content)
        return httpx.Response(200, content=json_lib.dumps({"id": "cus_new"}).encode())

    transport = _routed_transport(
        {"GET /v3/customers": _json(200, {"data": []}), "POST /v3/customers": create}
    )
    gateway = AsaasPaymentGateway(api_key="key", transport=transport)
    gateway.ensure_customer(
        external_reference="org-1", email="a@b.com", name="Ana", tax_id="12345678909"
    )
    assert seen["body"]["cpfCnpj"] == "12345678909"


def test_verify_credentials_ok() -> None:
    transport = _routed_transport({"GET /v3/customers": _json(200, {"data": []})})
    AsaasPaymentGateway(api_key="key", transport=transport).verify_credentials()


def test_verify_credentials_bad_key_raises() -> None:
    transport = _routed_transport(
        {
            "GET /v3/customers": _json(
                401, {"errors": [{"code": "invalid_access_token", "description": "bad"}]}
            )
        }
    )
    with pytest.raises(PaymentGatewayError) as info:
        AsaasPaymentGateway(api_key="key", transport=transport).verify_credentials()
    assert info.value.status == 401
    assert info.value.retryable is False


def test_get_subscription_maps_expired_to_canceled() -> None:
    transport = _routed_transport(
        {
            "GET /v3/subscriptions/sub_1": _json(
                200,
                {
                    "id": "sub_1",
                    "customer": "cus_1",
                    "status": "EXPIRED",
                    "externalReference": "org-1",
                    "nextDueDate": "2026-09-01",
                },
            ),
        }
    )
    gateway = AsaasPaymentGateway(api_key="key", transport=transport)
    subscription = gateway.get_subscription("sub_1")
    assert subscription.status == "canceled"


def test_get_subscription_maps_inactive_to_incomplete() -> None:
    transport = _routed_transport(
        {
            "GET /v3/subscriptions/sub_1": _json(
                200,
                {"id": "sub_1", "customer": "cus_1", "status": "INACTIVE"},
            ),
        }
    )
    gateway = AsaasPaymentGateway(api_key="key", transport=transport)
    subscription = gateway.get_subscription("sub_1")
    assert subscription.status == "incomplete"


def test_cancel_subscription_fetches_then_deletes() -> None:
    calls: list[str] = []

    def get_handler(request: httpx.Request) -> httpx.Response:
        calls.append("GET")
        return httpx.Response(
            200,
            content=json_lib.dumps(
                {"id": "sub_1", "customer": "cus_1", "status": "ACTIVE"}
            ).encode(),
        )

    def delete_handler(request: httpx.Request) -> httpx.Response:
        calls.append("DELETE")
        return httpx.Response(200, content=json_lib.dumps({"deleted": True, "id": "sub_1"}).encode())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return get_handler(request)
        return delete_handler(request)

    gateway = AsaasPaymentGateway(api_key="key", transport=httpx.MockTransport(handler))
    canceled = gateway.cancel_subscription("sub_1")
    assert calls == ["GET", "DELETE"]
    assert canceled.status == "canceled"


def test_get_fee_breakdown_converts_decimal_reais_to_cents() -> None:
    transport = _routed_transport(
        {
            "GET /v3/payments/pay_1": _json(
                200, {"id": "pay_1", "value": "150.00", "netValue": "145.51"}
            ),
        }
    )
    gateway = AsaasPaymentGateway(api_key="key", transport=transport)
    fee = gateway.get_fee_breakdown("pay_1")
    assert fee.gross.amount_cents == 15000
    assert fee.net.amount_cents == 14551
    assert fee.fee.amount_cents == 449
    assert fee.gross.amount_cents == fee.fee.amount_cents + fee.net.amount_cents


def test_error_response_raises_payment_gateway_error() -> None:
    transport = _routed_transport(
        {
            "GET /v3/subscriptions/sub_missing": _json(
                404, {"errors": [{"code": "invalid_object", "description": "not found"}]}
            ),
        }
    )
    gateway = AsaasPaymentGateway(api_key="key", transport=transport)
    with pytest.raises(PaymentGatewayError) as excinfo:
        gateway.get_subscription("sub_missing")
    assert excinfo.value.gateway == "asaas"
    assert excinfo.value.status == 404
    assert excinfo.value.retryable is False


def test_5xx_is_retryable() -> None:
    transport = _routed_transport(
        {
            "GET /v3/subscriptions/sub_1": _json(500, {"errors": [{"description": "boom"}]}),
        }
    )
    gateway = AsaasPaymentGateway(api_key="key", transport=transport)
    with pytest.raises(PaymentGatewayError) as excinfo:
        gateway.get_subscription("sub_1")
    assert excinfo.value.retryable is True
