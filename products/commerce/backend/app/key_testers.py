"""The "Testar" probe for the org's Asaas API key (seed `create_api_keys_router` `testers=`).

Builds the seed `HostedCheckout` with the typed key and runs its
`check_checkout_readiness` against the real post-payment URL, so a missing Asaas
site registration shows up on the button, not at the first customer's checkout.
`CheckoutProbe` is the DI seam (`use(factory=...)` / `reset()`): production builds
the real seed adapter; tests inject the seed Fake or a MockTransport-backed one.

Lifted from `products/store/backend/app/key_testers.py`. NOC-REMEDIATE[commerce-readiness-probe-lift]:
the organ does not ship this probe yet; a second consumer (store + commerce) makes it N=2 --
lift into `noctusai_lib.domain.commerce` before a third copy. -- 2026-10-13
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

from app.commerce import CFG
from app.config import settings

logger = logging.getLogger(__name__)

CheckoutFactory = Callable[[str], HostedCheckout]  # (api_key)

READY_MESSAGE = "Chave válida e conta pronta para receber pagamentos."


def _default_factory(api_key: str) -> HostedCheckout:
    # Same environment the organ's gateway charges against (its default base URL).
    return make_hosted_checkout(provider="asaas", asaas_api_key=api_key)


class CheckoutProbe:
    def __init__(self) -> None:
        self._factory: Optional[CheckoutFactory] = None

    def use(self, *, factory: Optional[CheckoutFactory] = None) -> None:
        self._factory = factory

    def reset(self) -> None:
        self.use()

    def success_url(self) -> str:
        return f"{settings.commerce_public_url.rstrip('/')}{CFG.order_path_template.format(token='')}".rstrip("/")

    def _run(self, value: str) -> list[ReadinessIssue]:
        return (self._factory or _default_factory)(value).check_checkout_readiness(success_url=self.success_url())

    async def test_asaas_api_key(self, value: str) -> ApiKeyTestResultOut:
        key = CFG.asaas_api_key_name
        try:
            issues = await run_in_threadpool(self._run, value)
        except PaymentGatewayError as exc:
            logger.warning("asaas readiness probe failed: %s", exc)
            return ApiKeyTestResultOut(key=key, success=False, message=f"Não foi possível consultar o Asaas: {exc.message}")
        if not issues:
            return ApiKeyTestResultOut(key=key, success=True, message=READY_MESSAGE)
        ok = readiness_ok(issues)
        lines = " ".join(i.message for i in issues)
        return ApiKeyTestResultOut(key=key, success=ok, message=f"{READY_MESSAGE} {lines}" if ok else lines)


checkout_probe = CheckoutProbe()

__all__ = ["CheckoutProbe", "READY_MESSAGE", "checkout_probe"]
