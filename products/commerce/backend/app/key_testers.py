"""The "Testar" probe for the org's Asaas API key (seed `create_api_keys_router` `org_testers=`).

A thin adapter: the probe itself is the organ's `probe_api_key_readiness` (key +
the org's chosen sandbox/production environment + the real post-payment URL), so
a missing Asaas site registration shows up on the button, not at the first
customer's checkout. This module only maps its verdict onto the settings router's
result model. The gateway is the same per-request DI seam the checkout uses
(`commerce_deps.get_gateway`); tests pass their own via `make_asaas_key_tester`.
"""
from __future__ import annotations

from typing import Callable

from noctusai_lib.domain.commerce import CheckoutGateway, probe_api_key_readiness
from noctusai_seed.api_keys_router import ApiKeyOrgTester, ApiKeyTestResultOut

from app.commerce import CFG
from app.commerce_deps import get_gateway
from app.config import settings


def make_asaas_key_tester(gateway_factory: Callable[[], CheckoutGateway] = get_gateway) -> ApiKeyOrgTester:
    async def test_asaas_api_key(value: str, org_id: str) -> ApiKeyTestResultOut:
        verdict = await probe_api_key_readiness(
            gateway_factory(),
            CFG,
            org_id=org_id,
            api_key=value,
            public_url=settings.commerce_public_url,
        )
        return ApiKeyTestResultOut(key=CFG.asaas_api_key_name, success=verdict.success, message=verdict.message)

    return test_asaas_api_key


__all__ = ["make_asaas_key_tester"]
