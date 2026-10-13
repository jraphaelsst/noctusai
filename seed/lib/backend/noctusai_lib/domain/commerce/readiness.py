"""The Asaas key readiness probe -- what the settings page's "Testar" button runs.

Builds the org's checkout client with the TYPED/stored key, in the org's chosen
environment (`CheckoutGateway.checkout_for_key`), and runs the payments seam's
`readiness_verdict` against the real post-payment return URL -- so a missing Asaas
site registration (400 `invalid_object` "Não há nenhum domínio configurado...")
shows up on the button, not at the first customer's checkout.

Lifted from the two product copies (`products/store` + `products/commerce`
`app/key_testers.py`, 2026-10-13). The host keeps only the thin adapter onto its
settings router's result model. `products/store` still carries its own copy (an
inactive product slated for retirement) -- the one consumer left to migrate.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from noctusai_lib.integrations.payments.checkout import ReadinessVerdict, readiness_verdict

from .config import CommerceConfig
from .errors import GatewayNotConfigured
from .gateway import CheckoutGateway

logger = logging.getLogger(__name__)


def order_return_url(cfg: CommerceConfig, public_url: str) -> str:
    """The storefront's post-payment landing URL WITHOUT a token -- the URL shape the
    checkout sends Asaas as `callback.successUrl` (token appended per order)."""
    return f"{public_url.rstrip('/')}{cfg.order_path_template.format(token='')}".rstrip("/")


async def probe_api_key_readiness(
    gateway: CheckoutGateway,
    cfg: CommerceConfig,
    *,
    org_id: Any,
    api_key: str,
    public_url: str,
) -> ReadinessVerdict:
    """Is `api_key` usable for checkout in `org_id`'s Asaas environment? Never raises:
    every failure is a `success=False` verdict with a pt-BR operator line."""
    try:
        checkout = gateway.checkout_for_key(org_id, api_key)
    except GatewayNotConfigured as exc:
        logger.warning("commerce: readiness probe could not build the checkout: %s", exc)
        return ReadinessVerdict(
            False, "Ambiente do Asaas inválido: escolha Sandbox ou Produção em Configurações › Chaves de API."
        )
    return await asyncio.to_thread(readiness_verdict, checkout, order_return_url(cfg, public_url))


__all__ = ["order_return_url", "probe_api_key_readiness"]
