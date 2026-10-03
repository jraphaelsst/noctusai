"""The "Testar" probe for the owner's managed keys (seed `create_api_keys_router`
`testers=`). Product-owned, as the seed router prescribes.

`asaas_api_key`: builds the seed `HostedCheckout` with the stored key against the
environment the owner chose, and runs its `check_checkout_readiness` for the real
post-payment URL — so a missing Asaas site registration (Asaas 400
`invalid_object` "Não há nenhum domínio configurado…") shows up on the button,
not at the first customer's checkout.

`CheckoutProbe` is the DI seam (same shape as `KeyProvider.use/reset`): production
builds the real seed adapter; tests inject the seed Fake or a MockTransport-backed
adapter via `use(factory=...)`.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from fastapi.concurrency import run_in_threadpool
from noctusai_lib.integrations.payments.checkout import (
    HostedCheckout,
    ReadinessIssue,
    make_hosted_checkout,
    readiness_ok,
)
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_seed.api_keys_router import ApiKeyTestResultOut

from app.api_keys import key_provider
from app.config import settings

logger = logging.getLogger(__name__)

CheckoutFactory = Callable[[str, str], HostedCheckout]  # (api_key, base_url)

READY_MESSAGE = "Chave válida e conta pronta para receber pagamentos."


def _default_factory(api_key: str, base_url: str) -> HostedCheckout:
    return make_hosted_checkout(provider="asaas", asaas_api_key=api_key, asaas_base_url=base_url)


class CheckoutProbe:
    def __init__(self) -> None:
        self._factory: Optional[CheckoutFactory] = None

    def use(self, *, factory: Optional[CheckoutFactory] = None) -> None:
        self._factory = factory

    def reset(self) -> None:
        self.use()

    def success_url(self) -> str:
        return f"{settings.store_public_url.rstrip('/')}/obrigado"

    def _run(self, value: str) -> list[ReadinessIssue]:
        factory = self._factory or _default_factory
        return factory(value, key_provider.asaas_base_url()).check_checkout_readiness(
            success_url=self.success_url()
        )

    async def test_asaas_api_key(self, value: str) -> ApiKeyTestResultOut:
        try:
            issues = await run_in_threadpool(self._run, value)
        except PaymentGatewayError as exc:
            logger.warning("asaas readiness probe failed: %s", exc)
            return ApiKeyTestResultOut(
                key="asaas_api_key", success=False, message=f"Não foi possível consultar o Asaas: {exc.message}"
            )
        if not issues:
            return ApiKeyTestResultOut(key="asaas_api_key", success=True, message=READY_MESSAGE)
        ok = readiness_ok(issues)
        lines = " ".join(i.message for i in issues)
        return ApiKeyTestResultOut(
            key="asaas_api_key", success=ok, message=f"{READY_MESSAGE} {lines}" if ok else lines
        )


checkout_probe = CheckoutProbe()

__all__ = ["CheckoutProbe", "READY_MESSAGE", "checkout_probe"]
