"""`make_payment_gateway` — the one seam a consumer touches."""
import pytest

from noctusai_lib.integrations.payments.factory import make_payment_gateway
from noctusai_lib.integrations.payments.fake import FakePaymentGateway
from noctusai_lib.integrations.payments.real_asaas import AsaasPaymentGateway
from noctusai_lib.integrations.payments.real_stripe import StripePaymentGateway


def test_use_fake_wins_regardless_of_provider() -> None:
    gateway = make_payment_gateway(use_fake=True, provider="stripe")
    assert isinstance(gateway, FakePaymentGateway)


def test_stripe_provider_requires_api_key() -> None:
    with pytest.raises(ValueError):
        make_payment_gateway(provider="stripe")


def test_asaas_provider_requires_api_key() -> None:
    with pytest.raises(ValueError):
        make_payment_gateway(provider="asaas")


def test_missing_provider_without_fake_raises() -> None:
    with pytest.raises(ValueError):
        make_payment_gateway()


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError):
        make_payment_gateway(provider="mercadopago")


def test_stripe_provider_builds_stripe_gateway() -> None:
    gateway = make_payment_gateway(provider="stripe", stripe_api_key="sk_test")
    assert isinstance(gateway, StripePaymentGateway)


def test_asaas_provider_builds_asaas_gateway() -> None:
    gateway = make_payment_gateway(provider="asaas", asaas_api_key="asaas_key")
    assert isinstance(gateway, AsaasPaymentGateway)
    gateway.close()
