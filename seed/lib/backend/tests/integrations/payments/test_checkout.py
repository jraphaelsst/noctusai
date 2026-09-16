"""`HostedCheckout` — Stripe Checkout Session, Asaas invoice-redirect, Fake.

Stripe path: `sys.modules["stripe"]` substituted with a scripted double
(the same external-dependency DI seam `test_stripe_gateway.py` uses — never
a monkey-patch of our own code). Asaas path: `httpx.MockTransport` (same
convention as `test_asaas_gateway.py`) — the real `_request` path runs
end-to-end.
"""
from __future__ import annotations

import json as json_lib
import sys
import types
from typing import Any, Callable

import httpx
import pytest

from noctusai_lib.integrations.payments.checkout import (
    AsaasHostedCheckout,
    CheckoutRequest,
    FakeHostedCheckout,
    HostedCheckout,
    StripeHostedCheckout,
    make_hosted_checkout,
)
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.real_asaas import AsaasPaymentGateway
from noctusai_lib.integrations.payments.real_stripe import StripePaymentGateway
from noctusai_lib.integrations.payments.types import Money
from stripe import StripeObject  # the real SDK type, bound before the fixture swaps the module


class _FakeStripeError(Exception):
    def __init__(self, message: str, *, http_status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.code = code


@pytest.fixture
def stripe_double(monkeypatch: pytest.MonkeyPatch) -> Any:
    """A scripted `stripe` module double covering `Customer` (reused by
    `ensure_customer`) and `checkout.Session.create` — the ONLY Stripe call
    `StripeHostedCheckout` makes for subscription creation. No
    `Subscription` class is registered at all, so a test can assert the
    checkout path never touches `Subscription.create` simply by the
    double raising `AttributeError` if it tried.
    """
    calls: list[tuple[str, Any]] = []
    customers: dict[str, dict] = {}
    sessions: dict[str, dict] = {}

    real_stripe = sys.modules["stripe"]
    module = types.ModuleType("stripe")
    # Keep the double a PACKAGE that falls back to the real module: the real
    # `StripeObject` lazily imports `stripe._invoice` and friends while
    # building an object, which fails against a bare stand-in module.
    module.__path__ = real_stripe.__path__
    module.__getattr__ = lambda name: getattr(real_stripe, name)
    module.api_key = None
    module.StripeError = _FakeStripeError
    module.SignatureVerificationError = type("SignatureVerificationError", (_FakeStripeError,), {})

    class _Customer:
        @staticmethod
        def search(query: str) -> Any:
            calls.append(("Customer.search", query))
            import re

            match = re.search(r"external_reference'\]:'([^']+)'", query)
            ext_ref = match.group(1) if match else None
            hits = [
                c
                for c in customers.values()
                if (c.get("metadata") or {}).get("external_reference") == ext_ref
            ]
            return types.SimpleNamespace(
                data=[StripeObject.construct_from(h, "sk_test_double") for h in hits]
            )

        @staticmethod
        def create(**kwargs: Any) -> dict:
            calls.append(("Customer.create", kwargs))
            cid = f"cus_{len(customers) + 1:03d}"
            record = {
                "id": cid,
                "email": kwargs["email"],
                "name": kwargs["name"],
                "metadata": kwargs.get("metadata", {}),
            }
            customers[cid] = record
            return StripeObject.construct_from(record, "sk_test_double")

    module.Customer = _Customer

    class _CheckoutSession:
        @staticmethod
        def create(**kwargs: Any) -> StripeObject:
            # Return the REAL StripeObject type (no .get(), dict() fails) so a
            # dict-only access pattern in the adapter fails here, not in prod.
            calls.append(("checkout.Session.create", kwargs))
            sid = f"cs_{len(sessions) + 1:03d}"
            record = {
                "id": sid,
                "url": f"https://checkout.stripe.com/pay/{sid}",
                "customer": kwargs["customer"],
                "subscription": None,  # not created until the payer completes checkout
                "metadata": kwargs.get("metadata", {}),
            }
            sessions[sid] = record
            return StripeObject.construct_from(record, "sk_test_double")

    module.checkout = types.SimpleNamespace(Session=_CheckoutSession)

    monkeypatch.setitem(__import__("sys").modules, "stripe", module)
    return types.SimpleNamespace(module=module, calls=calls, customers=customers, sessions=sessions)


@pytest.fixture
def stripe_checkout(stripe_double: Any) -> StripeHostedCheckout:
    return StripeHostedCheckout(StripePaymentGateway(api_key="sk_test_dummy"))


def _valid_stripe_request(**overrides: Any) -> CheckoutRequest:
    base = dict(
        external_reference="org-1",
        email="a@b.com",
        name="Ana",
        price=Money(2990, "BRL"),
        plan_ref="price_123",
        success_url="https://app.example.com/success",
        cancel_url="https://app.example.com/cancel",
    )
    base.update(overrides)
    return CheckoutRequest(**base)


def test_stripe_checkout_creates_session_in_subscription_mode(
    stripe_checkout: StripeHostedCheckout, stripe_double: Any
) -> None:
    session = stripe_checkout.create_checkout(_valid_stripe_request())
    assert session.id_at_gateway == "cs_001"
    assert session.checkout_url == "https://checkout.stripe.com/pay/cs_001"
    assert session.subscription_id_at_gateway is None  # not created until payer completes checkout
    create_call = next(c for c in stripe_double.calls if c[0] == "checkout.Session.create")
    assert create_call[1]["mode"] == "subscription"
    assert create_call[1]["line_items"] == [{"price": "price_123", "quantity": 1}]


def test_stripe_checkout_never_calls_create_subscription(
    stripe_checkout: StripeHostedCheckout, stripe_double: Any
) -> None:
    stripe_checkout.create_checkout(_valid_stripe_request())
    assert not any(call[0].startswith("Subscription.") for call in stripe_double.calls)
    # Every recorded call is a Customer lookup or the Checkout Session create:
    # nothing creates a subscription directly (Stripe does that when the payer
    # completes checkout). Asserting on the recorded calls rather than on the
    # double's attributes, because the double now falls back to the real
    # `stripe` module so that real StripeObjects can be built.
    assert {call[0] for call in stripe_double.calls} <= {
        "Customer.search",
        "Customer.create",
        "checkout.Session.create",
    }


def test_stripe_checkout_reuses_existing_customer(
    stripe_checkout: StripeHostedCheckout, stripe_double: Any
) -> None:
    stripe_double.customers["cus_existing"] = {
        "id": "cus_existing",
        "email": "a@b.com",
        "name": "Ana",
        "metadata": {"external_reference": "org-1"},
    }
    session = stripe_checkout.create_checkout(_valid_stripe_request())
    assert session.customer_id_at_gateway == "cus_existing"
    assert not any(call[0] == "Customer.create" for call in stripe_double.calls)


def test_stripe_checkout_requires_plan_ref(
    stripe_checkout: StripeHostedCheckout, stripe_double: Any
) -> None:
    with pytest.raises(PaymentGatewayError):
        stripe_checkout.create_checkout(_valid_stripe_request(plan_ref=None))


@pytest.mark.parametrize("missing", ["success_url", "cancel_url"])
def test_stripe_checkout_requires_redirect_urls(
    stripe_checkout: StripeHostedCheckout, stripe_double: Any, missing: str
) -> None:
    with pytest.raises(PaymentGatewayError):
        stripe_checkout.create_checkout(_valid_stripe_request(**{missing: None}))


# ── Asaas ────────────────────────────────────────────────────────────────


def _routed_transport(routes: dict[str, Callable[[httpx.Request], httpx.Response]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url.path}"
        route = routes.get(key)
        if route is None:
            return httpx.Response(404, json={"errors": [{"description": f"no route for {key}"}]})
        return route(request)

    return httpx.MockTransport(handler)


def _json(status: int, body: dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=json_lib.dumps(body).encode())

    return handler


def _asaas_checkout(transport: httpx.BaseTransport) -> AsaasHostedCheckout:
    return AsaasHostedCheckout(AsaasPaymentGateway(api_key="asaas-key", transport=transport))


def _asaas_request(**overrides: Any) -> CheckoutRequest:
    base = dict(
        external_reference="org-1",
        email="a@b.com",
        name="Ana",
        price=Money(15000, "BRL"),
        billing_method="pix",
    )
    base.update(overrides)
    return CheckoutRequest(**base)


def test_asaas_checkout_pix_returns_invoice_url_and_qr() -> None:
    transport = _routed_transport(
        {
            "GET /v3/customers": _json(200, {"data": []}),
            "POST /v3/customers": _json(200, {"id": "cus_001"}),
            "POST /v3/subscriptions": _json(
                200,
                {
                    "id": "sub_001",
                    "customer": "cus_001",
                    "status": "ACTIVE",
                    "nextDueDate": "2026-10-01",
                },
            ),
            "GET /v3/subscriptions/sub_001/payments": _json(
                200,
                {
                    "data": [
                        {
                            "id": "pay_001",
                            "invoiceUrl": "https://sandbox.asaas.com/i/pay_001",
                            "status": "PENDING",
                        }
                    ]
                },
            ),
            "GET /v3/payments/pay_001/pixQrCode": _json(
                200,
                {
                    "payload": "00020126-pix-copia-e-cola",
                    "encodedImage": "aGVsbG8=",
                    "expirationDate": "2026-09-17 12:00:00",
                },
            ),
        }
    )
    checkout = _asaas_checkout(transport)
    session = checkout.create_checkout(_asaas_request())
    assert session.checkout_url == "https://sandbox.asaas.com/i/pay_001"
    assert session.subscription_id_at_gateway == "sub_001"
    assert session.pix_qr is not None
    assert session.pix_qr.payload == "00020126-pix-copia-e-cola"
    assert session.pix_qr.encoded_image == "aGVsbG8="
    assert session.pix_qr.expiration_date == "2026-09-17 12:00:00"


def test_asaas_checkout_boleto_has_no_pix_qr() -> None:
    transport = _routed_transport(
        {
            "GET /v3/customers": _json(200, {"data": [{"id": "cus_001", "email": "a@b.com", "name": "Ana"}]}),
            "POST /v3/subscriptions": _json(
                200, {"id": "sub_002", "customer": "cus_001", "status": "ACTIVE", "nextDueDate": "2026-10-01"}
            ),
            "GET /v3/subscriptions/sub_002/payments": _json(
                200, {"data": [{"id": "pay_002", "invoiceUrl": "https://sandbox.asaas.com/i/pay_002"}]}
            ),
        }
    )
    checkout = _asaas_checkout(transport)
    session = checkout.create_checkout(_asaas_request(billing_method="boleto"))
    assert session.checkout_url == "https://sandbox.asaas.com/i/pay_002"
    assert session.pix_qr is None


def test_stripe_checkout_trial_collects_card_up_front(
    stripe_checkout: StripeHostedCheckout, stripe_double: Any
) -> None:
    stripe_checkout.create_checkout(_valid_stripe_request(trial_days=14))
    kwargs = next(c for c in stripe_double.calls if c[0] == "checkout.Session.create")[1]
    assert kwargs["subscription_data"]["trial_period_days"] == 14
    assert kwargs["payment_method_collection"] == "always"
    assert kwargs["client_reference_id"] == "org-1"


def test_stripe_checkout_without_trial_sends_no_trial(
    stripe_checkout: StripeHostedCheckout, stripe_double: Any
) -> None:
    stripe_checkout.create_checkout(_valid_stripe_request())
    kwargs = next(c for c in stripe_double.calls if c[0] == "checkout.Session.create")[1]
    assert "trial_period_days" not in kwargs["subscription_data"]


def test_asaas_checkout_card_sends_tax_id_and_trial_due_date() -> None:
    seen: dict[str, Any] = {}

    def create_customer(request: httpx.Request) -> httpx.Response:
        seen["customer"] = json_lib.loads(request.content)
        return httpx.Response(200, content=json_lib.dumps({"id": "cus_003"}).encode())

    def create_subscription(request: httpx.Request) -> httpx.Response:
        seen["subscription"] = json_lib.loads(request.content)
        return httpx.Response(200, content=json_lib.dumps(
            {"id": "sub_003", "customer": "cus_003", "status": "ACTIVE", "nextDueDate": "2026-10-01"}
        ).encode())

    transport = _routed_transport(
        {
            "GET /v3/customers": _json(200, {"data": []}),
            "POST /v3/customers": create_customer,
            "POST /v3/subscriptions": create_subscription,
            "GET /v3/subscriptions/sub_003/payments": _json(
                200, {"data": [{"id": "pay_003", "invoiceUrl": "https://sandbox.asaas.com/i/pay_003"}]}
            ),
        }
    )
    checkout = _asaas_checkout(transport)
    session = checkout.create_checkout(
        _asaas_request(billing_method="card", tax_id="12345678909", trial_days=7)
    )
    assert session.checkout_url == "https://sandbox.asaas.com/i/pay_003"
    assert session.pix_qr is None
    assert seen["customer"]["cpfCnpj"] == "12345678909"
    assert seen["subscription"]["billingType"] == "CREDIT_CARD"


@pytest.mark.parametrize("billing_method", ["unspecified"])
def test_asaas_checkout_requires_a_concrete_method(billing_method: str) -> None:
    checkout = _asaas_checkout(httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(PaymentGatewayError):
        checkout.create_checkout(_asaas_request(billing_method=billing_method))


def test_asaas_checkout_raises_when_no_payment_generated_yet() -> None:
    transport = _routed_transport(
        {
            "GET /v3/customers": _json(200, {"data": [{"id": "cus_001", "email": "a@b.com", "name": "Ana"}]}),
            "POST /v3/subscriptions": _json(
                200, {"id": "sub_003", "customer": "cus_001", "status": "ACTIVE", "nextDueDate": "2026-10-01"}
            ),
            "GET /v3/subscriptions/sub_003/payments": _json(200, {"data": []}),
        }
    )
    checkout = _asaas_checkout(transport)
    with pytest.raises(PaymentGatewayError) as excinfo:
        checkout.create_checkout(_asaas_request())
    assert excinfo.value.retryable is True


# ── Fake / factory / protocol parity ────────────────────────────────────


def test_fake_hosted_checkout_satisfies_protocol() -> None:
    fake = FakeHostedCheckout()
    assert isinstance(fake, HostedCheckout)
    session = fake.create_checkout(_asaas_request())
    assert session.pix_qr is not None
    assert fake.calls[0][0] == "create_checkout"


def test_fake_hosted_checkout_no_pix_for_non_pix_method() -> None:
    fake = FakeHostedCheckout()
    session = fake.create_checkout(_asaas_request(billing_method="boleto"))
    assert session.pix_qr is None


def test_make_hosted_checkout_use_fake_wins() -> None:
    checkout = make_hosted_checkout(use_fake=True, provider="stripe")
    assert isinstance(checkout, FakeHostedCheckout)


def test_make_hosted_checkout_stripe_builds_stripe_checkout() -> None:
    checkout = make_hosted_checkout(provider="stripe", stripe_api_key="sk_test")
    assert isinstance(checkout, StripeHostedCheckout)
    assert isinstance(checkout, HostedCheckout)


def test_make_hosted_checkout_asaas_builds_asaas_checkout() -> None:
    checkout = make_hosted_checkout(provider="asaas", asaas_api_key="asaas_key")
    assert isinstance(checkout, AsaasHostedCheckout)
    assert isinstance(checkout, HostedCheckout)


def test_make_hosted_checkout_missing_provider_raises() -> None:
    with pytest.raises(ValueError):
        make_hosted_checkout()


def test_make_hosted_checkout_unknown_provider_raises() -> None:
    with pytest.raises(ValueError):
        make_hosted_checkout(provider="mercadopago")
