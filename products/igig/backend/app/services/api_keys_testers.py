"""Live probe for `POST /api/settings/api-keys/anthropic_api_key/test`.

Same shape `social-wiring`'s `settings_router._test_anthropic_key` uses
(N=2 recurrence — flagged in the delivery note as a seed-lift
candidate; not lifted in this slice to stay file-disjoint): a one-token
Messages call with the value the operator just entered, so a green
result means THIS org's key will work — not that some key somewhere is
valid.

`http_client_factory` is the injectable DI seam
(`KB § PATTERNS/backend/di-test-seam.md`, Class-B): tests pass a factory
building an `httpx.AsyncClient(transport=httpx.MockTransport(handler))`
instead of a monkeypatch of `httpx.AsyncClient` itself.
"""
from __future__ import annotations

import logging
from typing import Callable

import httpx

from noctusai_lib.integrations.llm.credit_probe import QUOTA_MARKERS
from noctusai_seed.api_keys_router import ApiKeyTester, ApiKeyTestResultOut

logger = logging.getLogger(__name__)

HttpClientFactory = Callable[[], httpx.AsyncClient]

_MODELO_DE_TESTE = "claude-haiku-4-5"


def _default_http_client_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient()


async def _test_anthropic_key(
    value: str, *, http_client_factory: HttpClientFactory
) -> ApiKeyTestResultOut:
    """Probe an Anthropic key with a one-token Messages call.

    `max_tokens` is 1 and the model is the cheapest current one: this is
    a liveness check, not a transcription.
    """
    try:
        async with http_client_factory() as http:
            resp = await http.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": value,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": _MODELO_DE_TESTE,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=20.0,
            )
    except Exception as exc:  # noqa: BLE001 — surfaced to the operator verbatim
        logger.warning("api_keys: Anthropic probe failed to connect (%s)", exc)
        return ApiKeyTestResultOut(
            key="anthropic_api_key", success=False, message=f"Erro de conexão: {exc}"
        )

    corpo = (resp.text or "").lower()
    if resp.status_code == 401:
        return ApiKeyTestResultOut(
            key="anthropic_api_key", success=False, message="API Key inválida ou expirada."
        )
    if resp.status_code in (400, 429) and (
        any(s in corpo for s in QUOTA_MARKERS) or "insufficient" in corpo or "quota" in corpo
    ):
        return ApiKeyTestResultOut(
            key="anthropic_api_key",
            success=False,
            message=(
                "Sem créditos na conta Anthropic. A chave é válida, mas a conta "
                "não tem saldo — adicione créditos em "
                "console.anthropic.com/settings/billing."
            ),
        )
    if resp.status_code == 429:
        return ApiKeyTestResultOut(
            key="anthropic_api_key",
            success=False,
            message="Limite de requisições atingido. Aguarde alguns minutos e teste novamente.",
        )
    if resp.status_code >= 400:
        return ApiKeyTestResultOut(
            key="anthropic_api_key",
            success=False,
            message=f"Erro inesperado: HTTP {resp.status_code}.",
        )
    return ApiKeyTestResultOut(
        key="anthropic_api_key", success=True, message="Conexão com a Anthropic bem-sucedida."
    )


def make_testers(
    *, http_client_factory: HttpClientFactory = _default_http_client_factory
) -> dict[str, ApiKeyTester]:
    """Build the `testers` mapping `create_api_keys_router` dispatches to."""

    async def _anthropic(value: str) -> ApiKeyTestResultOut:
        return await _test_anthropic_key(value, http_client_factory=http_client_factory)

    return {"anthropic_api_key": _anthropic}
