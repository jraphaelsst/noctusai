"""``POST /api/settings/api-keys/{key}/test`` probes for the per-org LLM keys.

A free, read-only ``GET /v1/models`` per vendor (no tokens spent): a 200 means
THIS org's key is accepted. ``http_client_factory`` is the DI seam (tests pass
an ``httpx.AsyncClient(transport=httpx.MockTransport(...))`` factory).
"""
from __future__ import annotations

import logging
from typing import Callable

import httpx

from noctusai_seed.api_keys_router import ApiKeyTester, ApiKeyTestResultOut

logger = logging.getLogger(__name__)

__all__ = ["make_llm_key_testers"]

HttpClientFactory = Callable[[], httpx.AsyncClient]

_OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
_ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
_ANTHROPIC_VERSION = "2023-06-01"


def _default_http_client_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15.0)


async def _probe(
    *, key: str, vendor: str, url: str, headers: dict[str, str], params: dict[str, int] | None,
    http_client_factory: HttpClientFactory,
) -> ApiKeyTestResultOut:
    try:
        async with http_client_factory() as http:
            resp = await http.get(url, headers=headers, params=params)
    except httpx.HTTPError as exc:
        logger.warning("agents.llm_key_probe vendor=%s error=%s", vendor, type(exc).__name__)
        return ApiKeyTestResultOut(key=key, success=False, message=f"{vendor} indisponível no momento.")
    if resp.status_code in (401, 403):
        return ApiKeyTestResultOut(key=key, success=False, message="Chave inválida, revogada ou sem permissão.")
    if resp.status_code == 429:
        return ApiKeyTestResultOut(
            key=key, success=False, message="Limite de requisições atingido. Tente novamente em instantes."
        )
    if resp.status_code >= 400:
        return ApiKeyTestResultOut(key=key, success=False, message=f"Resposta inesperada: HTTP {resp.status_code}.")
    return ApiKeyTestResultOut(key=key, success=True, message=f"Conexão com a {vendor} bem-sucedida.")


def make_llm_key_testers(
    *, http_client_factory: HttpClientFactory = _default_http_client_factory
) -> dict[str, ApiKeyTester]:
    async def _openai(value: str) -> ApiKeyTestResultOut:
        return await _probe(
            key="openai_api_key", vendor="OpenAI", url=_OPENAI_MODELS_URL,
            headers={"Authorization": f"Bearer {value}"}, params=None,
            http_client_factory=http_client_factory,
        )

    async def _anthropic(value: str) -> ApiKeyTestResultOut:
        return await _probe(
            key="anthropic_api_key", vendor="Anthropic", url=_ANTHROPIC_MODELS_URL,
            headers={"x-api-key": value, "anthropic-version": _ANTHROPIC_VERSION},
            params={"limit": 1}, http_client_factory=http_client_factory,
        )

    return {"openai_api_key": _openai, "anthropic_api_key": _anthropic}
