"""Live probes for `POST /api/settings/api-keys/{key}/test` — Stripe
and Asaas only (cheap, side-effect-free reads; Stripe webhook secret /
Asaas webhook token / Turnstile secret have no live-probe endpoint and
stay `testable=False` in `api_keys_store.API_KEY_SPECS`).

`http_client_factory` is the injectable DI seam
(`KB § PATTERNS/backend/di-test-seam.md`, Class-B): tests pass a factory
building an `httpx.AsyncClient(transport=httpx.MockTransport(handler))`
— same seam `AsaasPaymentGateway` / `HttpxMailchimpClient` use for their
own `transport=` kwarg — never a monkeypatch of `httpx.AsyncClient`
itself.
"""
from __future__ import annotations

import logging
from typing import Callable

import httpx

from noctusai_seed.api_keys_router import ApiKeyTester, ApiKeyTestResultOut

from app.config import settings

logger = logging.getLogger(__name__)

HttpClientFactory = Callable[[], httpx.AsyncClient]

_STRIPE_BALANCE_URL = "https://api.stripe.com/v1/balance"


def _default_http_client_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient()


async def _test_stripe_key(
    value: str, *, http_client_factory: HttpClientFactory
) -> ApiKeyTestResultOut:
    """Probe a Stripe secret key with a read-only `GET /v1/balance` call
    (no side effects, cheapest authenticated Stripe endpoint)."""
    try:
        async with http_client_factory() as http:
            resp = await http.get(_STRIPE_BALANCE_URL, auth=(value, ""), timeout=20.0)
    except Exception as exc:  # noqa: BLE001 — surfaced to the operator verbatim
        logger.warning("api_keys: Stripe probe failed to connect (%s)", exc)
        return ApiKeyTestResultOut(
            key="stripe_secret_key", success=False, message=f"Erro de conexão: {exc}"
        )
    if resp.status_code == 401:
        return ApiKeyTestResultOut(
            key="stripe_secret_key", success=False, message="API Key inválida ou expirada."
        )
    if resp.status_code >= 400:
        return ApiKeyTestResultOut(
            key="stripe_secret_key",
            success=False,
            message=f"Erro inesperado: HTTP {resp.status_code}.",
        )
    return ApiKeyTestResultOut(
        key="stripe_secret_key", success=True, message="Conexão com Stripe bem-sucedida."
    )


async def _test_asaas_key(
    value: str, *, http_client_factory: HttpClientFactory
) -> ApiKeyTestResultOut:
    """Probe an Asaas API key with a read-only `GET /myAccount` call.

    `asaas-access-token`-style auth (see `real_asaas.AsaasPaymentGateway`
    — the `access_token` header, not Bearer) against `settings.
    asaas_base_url` (defaults to `https://api.asaas.com/v3`, so the
    resolved URL is `.../v3/myAccount`)."""
    url = f"{settings.asaas_base_url.rstrip('/')}/myAccount"
    try:
        async with http_client_factory() as http:
            resp = await http.get(url, headers={"access_token": value}, timeout=20.0)
    except Exception as exc:  # noqa: BLE001 — surfaced to the operator verbatim
        logger.warning("api_keys: Asaas probe failed to connect (%s)", exc)
        return ApiKeyTestResultOut(
            key="asaas_api_key", success=False, message=f"Erro de conexão: {exc}"
        )
    if resp.status_code == 401:
        return ApiKeyTestResultOut(
            key="asaas_api_key", success=False, message="API Key inválida ou expirada."
        )
    if resp.status_code >= 400:
        return ApiKeyTestResultOut(
            key="asaas_api_key",
            success=False,
            message=f"Erro inesperado: HTTP {resp.status_code}.",
        )
    return ApiKeyTestResultOut(
        key="asaas_api_key", success=True, message="Conexão com Asaas bem-sucedida."
    )


def make_testers(
    *, http_client_factory: HttpClientFactory = _default_http_client_factory
) -> dict[str, ApiKeyTester]:
    """Build the `testers` mapping `create_api_keys_router` dispatches to.

    `http_client_factory` defaults to a real `httpx.AsyncClient`; tests
    pass one building a client wired to `httpx.MockTransport` instead.
    """
    async def _stripe(value: str) -> ApiKeyTestResultOut:
        return await _test_stripe_key(value, http_client_factory=http_client_factory)

    async def _asaas(value: str) -> ApiKeyTestResultOut:
        return await _test_asaas_key(value, http_client_factory=http_client_factory)

    return {"stripe_secret_key": _stripe, "asaas_api_key": _asaas}
