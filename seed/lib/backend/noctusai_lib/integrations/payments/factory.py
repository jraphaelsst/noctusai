"""The single seam consumers reach for — Fake or one Real gateway, by flag."""
from __future__ import annotations

from typing import Optional, Union

import httpx

from .fake import FakePaymentGateway
from .real_asaas import DEFAULT_BASE_URL as ASAAS_DEFAULT_BASE_URL
from .real_asaas import DEFAULT_TIMEOUT_SECONDS as ASAAS_DEFAULT_TIMEOUT_SECONDS
from .real_asaas import AsaasPaymentGateway
from .real_stripe import StripePaymentGateway
from .types import PaymentGatewayName


def make_payment_gateway(
    *,
    provider: Union[PaymentGatewayName, str, None] = None,
    use_fake: bool = False,
    stripe_api_key: Optional[str] = None,
    asaas_api_key: Optional[str] = None,
    asaas_base_url: str = ASAAS_DEFAULT_BASE_URL,
    asaas_timeout_seconds: float = ASAAS_DEFAULT_TIMEOUT_SECONDS,
    asaas_transport: Optional[httpx.BaseTransport] = None,
    fake_default_fee_bps: int = 299,
) -> Union[FakePaymentGateway, StripePaymentGateway, AsaasPaymentGateway]:
    """Build a `PaymentGateway`. Every branch satisfies the same Protocol,
    so a consumer selects here once and never branches on the gateway
    name afterward.

    Args:
        provider: `"stripe"` or `"asaas"` (or the `PaymentGatewayName`
            enum value). Required unless `use_fake=True`.
        use_fake: when True, return `FakePaymentGateway` regardless of
            `provider` — the dev/test path.
        stripe_api_key: required when `provider="stripe"`.
        asaas_api_key: required when `provider="asaas"`.
        asaas_base_url / asaas_timeout_seconds / asaas_transport: Asaas
            adapter tuning; `asaas_transport` is the test seam.
        fake_default_fee_bps: forwarded to `FakePaymentGateway`.

    Raises:
        ValueError: `use_fake=False` and `provider` is missing/unknown,
            or the matching `*_api_key` for the chosen provider is absent.
    """
    if use_fake:
        return FakePaymentGateway(default_fee_bps=fake_default_fee_bps)

    if provider is None:
        raise ValueError(
            "make_payment_gateway: provider is required when use_fake=False"
        )
    normalized = PaymentGatewayName(provider)

    if normalized is PaymentGatewayName.STRIPE:
        if not stripe_api_key:
            raise ValueError(
                "make_payment_gateway: stripe_api_key is required for provider='stripe'"
            )
        return StripePaymentGateway(api_key=stripe_api_key)

    if normalized is PaymentGatewayName.ASAAS:
        if not asaas_api_key:
            raise ValueError(
                "make_payment_gateway: asaas_api_key is required for provider='asaas'"
            )
        return AsaasPaymentGateway(
            api_key=asaas_api_key,
            base_url=asaas_base_url,
            timeout_seconds=asaas_timeout_seconds,
            transport=asaas_transport,
        )

    raise ValueError(f"make_payment_gateway: unknown provider {provider!r}")


__all__ = ["make_payment_gateway"]
