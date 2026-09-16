"""`StripePaymentGateway` — the vendor SDK is substituted via `sys.modules`,
never the real network. This is a DI seam on an EXTERNAL dependency
(the standing protocol's `patch.object` external-services carve-out),
not a monkey-patch of our own code: `real_stripe.py`'s `_stripe()`
imports whatever is registered as `stripe` at call time, and this
fixture registers a scripted double there for the duration of each test.
"""
from __future__ import annotations

import re
import sys
import types
from typing import Any

import pytest
from stripe import StripeObject  # the REAL SDK type — bound before the fixture swaps the module

from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.real_stripe import StripePaymentGateway
from noctusai_lib.integrations.payments.types import Money, SubscriptionRequest


class _FakeStripeError(Exception):
    def __init__(self, message: str, *, http_status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.code = code


@pytest.fixture
def stripe_double(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Register a scripted `stripe` module double in `sys.modules`."""
    calls: list[tuple[str, Any]] = []
    customers: dict[str, dict] = {}
    subscriptions: dict[str, dict] = {}
    charges: dict[str, dict] = {}

    real_stripe = sys.modules["stripe"]
    module = types.ModuleType("stripe")
    # A package that falls back to the real module: `StripeObject` lazily
    # imports `stripe._...` submodules while constructing.
    module.__path__ = real_stripe.__path__
    module.__getattr__ = lambda name: getattr(real_stripe, name)
    module.api_key = None
    module.StripeError = _FakeStripeError

    def real(record: dict) -> StripeObject:
        # Every response is a REAL StripeObject (no .get(), dict() raises),
        # so dict-only access in the adapter fails here instead of in prod.
        return StripeObject.construct_from(record, "sk_test_double")

    class _Customer:
        @staticmethod
        def search(query: str) -> Any:
            calls.append(("Customer.search", query))
            match = re.search(r"external_reference'\]:'([^']+)'", query)
            ext_ref = match.group(1) if match else None
            hits = [
                c
                for c in customers.values()
                if (c.get("metadata") or {}).get("external_reference") == ext_ref
            ]
            return types.SimpleNamespace(data=[real(h) for h in hits])

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
            return real(record)

    module.Customer = _Customer

    class _Subscription:
        @staticmethod
        def create(**kwargs: Any) -> dict:
            calls.append(("Subscription.create", kwargs))
            sid = f"sub_{len(subscriptions) + 1:03d}"
            record = {
                "id": sid,
                "customer": kwargs["customer"],
                "status": "incomplete",
                "metadata": kwargs.get("metadata", {}),
                "current_period_end": None,
                "latest_invoice": {"charge": "ch_001"},
            }
            subscriptions[sid] = record
            return real(record)

        @staticmethod
        def retrieve(sid: str, **kwargs: Any) -> StripeObject:
            calls.append(("Subscription.retrieve", sid))
            if sid not in subscriptions:
                raise _FakeStripeError(
                    "No such subscription", http_status=404, code="resource_missing"
                )
            return real(subscriptions[sid])

        @staticmethod
        def cancel(sid: str) -> StripeObject:
            calls.append(("Subscription.cancel", sid))
            record = dict(subscriptions[sid])
            record["status"] = "canceled"
            subscriptions[sid] = record
            return real(record)

    module.Subscription = _Subscription

    class _Charge:
        @staticmethod
        def retrieve(cid: str, **kwargs: Any) -> dict:
            calls.append(("Charge.retrieve", cid))
            return real(charges[cid])

    module.Charge = _Charge

    class _Balance:
        fail: Exception | None = None

        @staticmethod
        def retrieve() -> dict:
            calls.append(("Balance.retrieve", None))
            if _Balance.fail is not None:
                raise _Balance.fail
            return real({"object": "balance"})

    module.Balance = _Balance

    monkeypatch.setitem(sys.modules, "stripe", module)
    return types.SimpleNamespace(
        module=module, calls=calls, customers=customers,
        subscriptions=subscriptions, charges=charges,
    )


@pytest.fixture
def gateway() -> StripePaymentGateway:
    return StripePaymentGateway(api_key="sk_test_dummy")


def test_ensure_customer_creates_new(gateway: StripePaymentGateway, stripe_double: Any) -> None:
    customer = gateway.ensure_customer(external_reference="org-1", email="a@b.com", name="Ana")
    assert customer.id_at_gateway == "cus_001"
    assert customer.external_reference == "org-1"
    assert ("Customer.search", "metadata['external_reference']:'org-1'") in stripe_double.calls


def test_ensure_customer_reuses_existing(gateway: StripePaymentGateway, stripe_double: Any) -> None:
    stripe_double.customers["cus_existing"] = {
        "id": "cus_existing",
        "email": "a@b.com",
        "name": "Ana",
        "metadata": {"external_reference": "org-1"},
    }
    customer = gateway.ensure_customer(external_reference="org-1", email="a@b.com", name="Ana")
    assert customer.id_at_gateway == "cus_existing"
    assert not any(call[0] == "Customer.create" for call in stripe_double.calls)


def test_create_subscription_requires_plan_ref(gateway: StripePaymentGateway, stripe_double: Any) -> None:
    with pytest.raises(PaymentGatewayError):
        gateway.create_subscription(
            SubscriptionRequest(
                external_reference="org-1",
                customer_id_at_gateway="cus_001",
                price=Money(2990, "BRL"),
            )
        )


def test_create_subscription_maps_status_and_charge(gateway: StripePaymentGateway, stripe_double: Any) -> None:
    subscription = gateway.create_subscription(
        SubscriptionRequest(
            external_reference="org-1",
            customer_id_at_gateway="cus_001",
            price=Money(2990, "BRL"),
            plan_ref="price_123",
        )
    )
    assert subscription.status == "incomplete"
    assert subscription.external_reference == "org-1"
    assert subscription.latest_charge_id_at_gateway == "ch_001"


def test_cancel_subscription_maps_to_canceled(gateway: StripePaymentGateway, stripe_double: Any) -> None:
    stripe_double.subscriptions["sub_001"] = {
        "id": "sub_001",
        "customer": "cus_001",
        "status": "active",
        "metadata": {"external_reference": "org-1"},
        "current_period_end": None,
        "latest_invoice": "in_001",
    }
    canceled = gateway.cancel_subscription("sub_001")
    assert canceled.status == "canceled"


def test_get_fee_breakdown_maps_balance_transaction(gateway: StripePaymentGateway, stripe_double: Any) -> None:
    stripe_double.charges["ch_001"] = {
        "id": "ch_001",
        "balance_transaction": {"amount": 2990, "fee": 172, "net": 2818, "currency": "brl"},
    }
    fee = gateway.get_fee_breakdown("ch_001")
    assert fee.gross.amount_cents == 2990
    assert fee.fee.amount_cents == 172
    assert fee.net.amount_cents == 2818
    assert fee.gross.currency == "BRL"


def test_stripe_error_is_translated_to_payment_gateway_error(
    gateway: StripePaymentGateway, stripe_double: Any
) -> None:
    with pytest.raises(PaymentGatewayError) as excinfo:
        gateway.get_subscription("sub_missing")
    assert excinfo.value.gateway == "stripe"
    assert excinfo.value.status == 404
    assert excinfo.value.retryable is False


def test_unknown_stripe_status_maps_to_incomplete(gateway: StripePaymentGateway, stripe_double: Any) -> None:
    stripe_double.subscriptions["sub_weird"] = {
        "id": "sub_weird",
        "customer": "cus_001",
        "status": "some_future_status_stripe_invents",
        "metadata": {},
        "current_period_end": None,
        "latest_invoice": None,
    }
    subscription = gateway.get_subscription("sub_weird")
    assert subscription.status == "incomplete"


def test_create_subscription_passes_trial_period_days(
    gateway: StripePaymentGateway, stripe_double: Any
) -> None:
    gateway.create_subscription(
        SubscriptionRequest(
            external_reference="org-1",
            customer_id_at_gateway="cus_1",
            price=Money(2990, "BRL"),
            plan_ref="price_1",
            trial_days=14,
        )
    )
    name, kwargs = [c for c in stripe_double.calls if c[0] == "Subscription.create"][0]
    assert kwargs["trial_period_days"] == 14


def test_create_subscription_omits_trial_when_zero(
    gateway: StripePaymentGateway, stripe_double: Any
) -> None:
    gateway.create_subscription(
        SubscriptionRequest(
            external_reference="org-1",
            customer_id_at_gateway="cus_1",
            price=Money(2990, "BRL"),
            plan_ref="price_1",
        )
    )
    _, kwargs = [c for c in stripe_double.calls if c[0] == "Subscription.create"][0]
    assert "trial_period_days" not in kwargs


def test_verify_credentials_calls_balance(gateway: StripePaymentGateway, stripe_double: Any) -> None:
    gateway.verify_credentials()
    assert ("Balance.retrieve", None) in stripe_double.calls


def test_verify_credentials_translates_auth_error(
    gateway: StripePaymentGateway, stripe_double: Any
) -> None:
    stripe_double.module.Balance.fail = _FakeStripeError("Invalid API Key", http_status=401)
    with pytest.raises(PaymentGatewayError) as info:
        gateway.verify_credentials()
    assert info.value.status == 401
    assert info.value.retryable is False


def test_subscription_raw_is_a_plain_dict_and_period_falls_back_to_items(
    gateway: StripePaymentGateway, stripe_double: Any
) -> None:
    stripe_double.subscriptions["sub_new"] = {
        "id": "sub_new",
        "customer": "cus_1",
        "status": "active",
        "metadata": {"external_reference": "org-9"},
        "latest_invoice": {"id": "in_1", "charge": "ch_9"},
        "items": {"object": "list", "data": [{"id": "si_1", "current_period_end": 1790000000}]},
    }
    sub = gateway.get_subscription("sub_new")
    assert isinstance(sub.raw, dict) and not isinstance(sub.raw, StripeObject)
    assert sub.external_reference == "org-9"
    assert sub.latest_charge_id_at_gateway == "ch_9"
    assert sub.current_period_end == "1790000000"
