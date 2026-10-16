"""`CheckoutRequest.reuse_existing` + `due_date` -- a retried one-off charge never double-bills.

The failure this pins: Asaas accepts ``POST /payments`` but the response is lost (timeout); the caller retries.
Without a lookup by ``externalReference`` the retry creates a SECOND charge for the same receivable.
"""
from __future__ import annotations

import datetime as dt
import json as json_lib
from typing import Any

import httpx

from noctusai_lib.integrations.payments.checkout import AsaasHostedCheckout, CheckoutRequest, FakeHostedCheckout
from noctusai_lib.integrations.payments.real_asaas import AsaasPaymentGateway
from noctusai_lib.integrations.payments.types import Money


def _req(**over: Any) -> CheckoutRequest:
    base: dict[str, Any] = dict(
        external_reference="orbity:entry-1", email="a@b.com", name="Ana Ltda", price=Money(150000),
        billing_cycle=None, billing_method="boleto", tax_id="12345678000195",
    )
    base.update(over)
    return CheckoutRequest(**base)


class _AsaasStub:
    """A stateful Asaas: `POST /payments` stores the charge, `GET /payments?externalReference=` finds it."""

    def __init__(self, *, lose_first_response: bool = False) -> None:
        self.payments: list[dict] = []
        self.calls: list[tuple[str, str, dict]] = []
        self._lose_first = lose_first_response

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json_lib.loads(request.content) if request.content else {}
        self.calls.append((request.method, request.url.path, body))
        path = request.url.path
        if path == "/v3/customers" and request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "cus_1", "email": "a@b.com", "name": "Ana Ltda"}]})
        if path == "/v3/payments" and request.method == "POST":
            payment = {"id": f"pay_{len(self.payments) + 1}", "invoiceUrl": "https://asaas.test/i", **body}
            self.payments.append(payment)
            if self._lose_first:
                self._lose_first = False
                raise httpx.ReadTimeout("response lost", request=request)
            return httpx.Response(200, json=payment)
        if path == "/v3/payments" and request.method == "GET":
            ref = request.url.params.get("externalReference")
            return httpx.Response(200, json={"data": [p for p in self.payments if p.get("externalReference") == ref]})
        return httpx.Response(404, json={"errors": [{"description": f"no route {path}"}]})


def _checkout(stub: _AsaasStub) -> AsaasHostedCheckout:
    return AsaasHostedCheckout(AsaasPaymentGateway(api_key="k", transport=httpx.MockTransport(stub)))


def test_a_retry_after_a_lost_response_reuses_the_charge_instead_of_creating_a_second() -> None:
    stub = _AsaasStub(lose_first_response=True)
    checkout = _checkout(stub)
    try:
        checkout.create_checkout(_req(reuse_existing=True))
    except Exception as exc:  # the lost response surfaces as a retryable gateway error
        assert getattr(exc, "retryable", False)
    session = checkout.create_checkout(_req(reuse_existing=True))  # the caller's retry
    assert len(stub.payments) == 1, "the retry must find the first charge, not POST a second one"
    assert session.id_at_gateway == "pay_1"


def test_without_reuse_existing_the_old_behaviour_is_untouched() -> None:
    stub = _AsaasStub()
    checkout = _checkout(stub)
    checkout.create_checkout(_req())
    checkout.create_checkout(_req())
    assert len(stub.payments) == 2
    assert not any(m == "GET" and p == "/v3/payments" for m, p, _ in stub.calls)


def test_the_external_reference_is_always_sent_to_the_gateway() -> None:
    stub = _AsaasStub()
    _checkout(stub).create_checkout(_req(reuse_existing=True))
    assert stub.payments[0]["externalReference"] == "orbity:entry-1"


def test_an_explicit_due_date_wins_over_due_days() -> None:
    stub = _AsaasStub()
    _checkout(stub).create_checkout(_req(due_date=dt.date(2026, 11, 5), due_days=3))
    assert stub.payments[0]["dueDate"] == "2026-11-05"


def test_fake_checkout_honours_reuse_existing() -> None:
    fake = FakeHostedCheckout()
    first = fake.create_checkout(_req(reuse_existing=True))
    again = fake.create_checkout(_req(reuse_existing=True))
    other = fake.create_checkout(_req(external_reference="orbity:entry-2", reuse_existing=True))
    assert again.id_at_gateway == first.id_at_gateway
    assert other.id_at_gateway != first.id_at_gateway
    assert len(fake.sessions) == 2
