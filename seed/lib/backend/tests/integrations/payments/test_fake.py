"""`FakePaymentGateway` exercises the full `PaymentGateway` Protocol —
no network, no keys. Also the reference contract a Real adapter must
satisfy identically.
"""
import pytest

from noctusai_lib.integrations.payments.fake import FakePaymentGateway
from noctusai_lib.integrations.payments.protocol import PaymentGateway
from noctusai_lib.integrations.payments.types import (
    FeeBreakdown,
    Money,
    SubscriptionRequest,
)


@pytest.fixture
def gateway() -> FakePaymentGateway:
    return FakePaymentGateway()


def test_satisfies_protocol(gateway: FakePaymentGateway) -> None:
    assert isinstance(gateway, PaymentGateway)


def test_ensure_customer_creates_new(gateway: FakePaymentGateway) -> None:
    customer = gateway.ensure_customer(
        external_reference="org-1", email="a@b.com", name="Ana"
    )
    assert customer.external_reference == "org-1"
    assert customer.id_at_gateway in gateway.customers


def test_ensure_customer_reuses_existing(gateway: FakePaymentGateway) -> None:
    first = gateway.ensure_customer(external_reference="org-1", email="a@b.com", name="Ana")
    second = gateway.ensure_customer(external_reference="org-1", email="a@b.com", name="Ana")
    assert first.id_at_gateway == second.id_at_gateway
    assert len(gateway.customers) == 1


def test_create_subscription_starts_trialing(gateway: FakePaymentGateway) -> None:
    customer = gateway.ensure_customer(external_reference="org-1", email="a@b.com", name="Ana")
    subscription = gateway.create_subscription(
        SubscriptionRequest(
            external_reference="org-1",
            customer_id_at_gateway=customer.id_at_gateway,
            price=Money(2990, "BRL"),
        )
    )
    assert subscription.status == "trialing"
    assert subscription.customer_id_at_gateway == customer.id_at_gateway
    assert subscription.latest_charge_id_at_gateway is not None


def test_get_subscription_round_trips(gateway: FakePaymentGateway) -> None:
    customer = gateway.ensure_customer(external_reference="org-1", email="a@b.com", name="Ana")
    created = gateway.create_subscription(
        SubscriptionRequest(
            external_reference="org-1",
            customer_id_at_gateway=customer.id_at_gateway,
            price=Money(2990, "BRL"),
        )
    )
    fetched = gateway.get_subscription(created.id_at_gateway)
    assert fetched == created


def test_cancel_subscription_moves_to_canceled(gateway: FakePaymentGateway) -> None:
    customer = gateway.ensure_customer(external_reference="org-1", email="a@b.com", name="Ana")
    created = gateway.create_subscription(
        SubscriptionRequest(
            external_reference="org-1",
            customer_id_at_gateway=customer.id_at_gateway,
            price=Money(2990, "BRL"),
        )
    )
    canceled = gateway.cancel_subscription(created.id_at_gateway)
    assert canceled.status == "canceled"
    assert gateway.get_subscription(created.id_at_gateway).status == "canceled"


def test_get_fee_breakdown_default_is_internally_consistent(gateway: FakePaymentGateway) -> None:
    fee = gateway.get_fee_breakdown("ch_000001")
    assert isinstance(fee, FeeBreakdown)
    assert fee.gross.amount_cents == fee.fee.amount_cents + fee.net.amount_cents


def test_get_fee_breakdown_scripted(gateway: FakePaymentGateway) -> None:
    scripted = FeeBreakdown(
        gross=Money(5000, "BRL"), fee=Money(150, "BRL"), net=Money(4850, "BRL")
    )
    gateway.script_fee("ch_000042", scripted)
    assert gateway.get_fee_breakdown("ch_000042") == scripted


def test_calls_are_recorded_for_intent_assertions(gateway: FakePaymentGateway) -> None:
    gateway.ensure_customer(external_reference="org-1", email="a@b.com", name="Ana")
    assert gateway.calls[0][0] == "ensure_customer"
