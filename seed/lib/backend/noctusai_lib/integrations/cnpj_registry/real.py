"""Real public-CNPJ-registry adapter — BrasilAPI primary, ReceitaWS
fallback, both keyless.

**Why two sources.** Neither is an SLA-backed service (BrasilAPI is a
community-run aggregator; ReceitaWS's free tier is a single small server) —
either can be down, slow, or momentarily wrong about a specific CNPJ. Since
the whole point of this lookup is to let social-wiring resolve a company's
`situação cadastral` BY ITSELF instead of blocking on a human uploading a
Cartão CNPJ, a single-source failure must not stop that — hence a fallback,
same posture `documents.cartao_cnpj`'s text-layer-then-vision ladder takes
for the same reason (never one shot at an answer).

**BrasilAPI** — `GET https://brasilapi.com.br/api/cnpj/v1/{cnpj}`. 200 with
the company's JSON, or 404 (`{"name": "NotFoundError", ...}`) when the CNPJ
does not exist. No API key.

**ReceitaWS** — `GET https://receitaws.com.br/v1/cnpj/{cnpj}`. Always 200;
the BODY carries `"status": "OK"` on success or `"status": "ERROR"` (with a
`"message"`) on failure — an invalid/unknown CNPJ and a rate-limited caller
look the same at the HTTP layer and are told apart only by that message
text (`_mensagem_indica_nao_encontrado`). No API key (free tier; no
`Authorization` header sent).

**Fallback resolution.** Whichever source answers FIRST with a definitive
verdict (found, or a confirmed not-found) wins; a not-found from the
primary is retried against the secondary (a single flaky aggregator saying
"unknown" is not treated as gospel) before this raises `CnpjNotFoundError`.
Only when BOTH sources fail does this raise — preferring to surface a
`CnpjNotFoundError` over an `CnpjRegistryUpstreamError` when either source
produced one, because "confirmed absent" is a more useful answer to a
caller than "nobody could tell me" whenever one is actually available.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from noctusai_lib.integrations.documents.cnpj import normalize as normalize_cnpj

from .errors import CnpjNotFoundError, CnpjRegistryError, CnpjRegistryUpstreamError
from .mappers import parse_brasilapi_response, parse_receitaws_response
from .types import CnpjRegistryFields
from noctusai_lib.primitives.accents import fold_accents

logger = logging.getLogger(__name__)

BRASILAPI_URL = "https://brasilapi.com.br/api/cnpj/v1"
RECEITAWS_URL = "https://receitaws.com.br/v1/cnpj"

#: Short on purpose — this lookup runs inline in a Crednet-apply request
#: (§ module docstring's "creation path") and again in a bounded scheduled
#: sweep; neither should block on a slow public API for long. Mirrors
#: `fx.bcb_adapter`'s own `_DEFAULT_TIMEOUT = 10.0` for the same class of
#: "public, keyless, best-effort" dependency.
DEFAULT_TIMEOUT_SECONDS = 8.0

#: Substrings of a ReceitaWS `status="ERROR"` `message` that mean "this
#: CNPJ specifically does not exist / is not a valid registration" as
#: opposed to a transient/rate-limit failure. Matched case-insensitively,
#: unaccented (ReceitaWS's own error copy is in Portuguese and has been
#: observed with and without accents). Anything NOT matching one of these
#: is treated as `CnpjRegistryUpstreamError` — never guessed either way.
_MENSAGENS_NAO_ENCONTRADO = ("nao encontrad", "invalido", "invalida")


def _sem_acento(texto: str) -> str:
    """Unicode NFKD accent fold (drop every combining mark) — the standard
    library's own primitive, not a hand-rolled translation table (an
    earlier draft of this function used `str.maketrans` with two
    same-length literals and got the alignment wrong; this is the
    boring-and-correct version)."""
    return fold_accents(texto)


def _mensagem_indica_nao_encontrado(mensagem: str) -> bool:
    alvo = _sem_acento(mensagem).lower()
    return any(pista in alvo for pista in _MENSAGENS_NAO_ENCONTRADO)


class RealCnpjRegistryLookup:
    """BrasilAPI-primary, ReceitaWS-fallback public CNPJ registry lookup.

    Construct via `make_cnpj_registry_lookup(real=True)`. `http_client`/
    `transport` are constructor-injectable (mirrors `turnstile.real.
    RealTurnstileVerifier`'s own seam) so a test can drive this against
    `httpx.MockTransport` with no network at all — this class's own test
    suite never calls the real BrasilAPI/ReceitaWS.
    """

    def __init__(
        self,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._http_client = http_client
        self._timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, transport=self._transport)

    async def _get(self, url: str, *, provider: str) -> httpx.Response:
        client = self._http_client or self._client()
        try:
            try:
                return await client.get(url)
            except httpx.HTTPError as exc:
                logger.warning("cnpj_registry: %s unreachable: %s", provider, exc)
                raise CnpjRegistryUpstreamError(f"{provider} unreachable: {exc}") from exc
        finally:
            if self._http_client is None:
                await client.aclose()

    async def _buscar_brasilapi(self, cnpj: str) -> CnpjRegistryFields:
        response = await self._get(f"{BRASILAPI_URL}/{cnpj}", provider="brasilapi")
        if response.status_code == 404:
            raise CnpjNotFoundError(cnpj, source="brasilapi")
        if response.status_code != 200:
            raise CnpjRegistryUpstreamError(
                f"brasilapi returned HTTP {response.status_code} for {cnpj}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CnpjRegistryUpstreamError(f"brasilapi returned non-JSON body: {exc}") from exc
        try:
            return parse_brasilapi_response(payload, cnpj)
        except (KeyError, TypeError, AttributeError) as exc:
            raise CnpjRegistryUpstreamError(
                f"brasilapi response shape unexpected: {payload!r}"
            ) from exc

    async def _buscar_receitaws(self, cnpj: str) -> CnpjRegistryFields:
        response = await self._get(f"{RECEITAWS_URL}/{cnpj}", provider="receitaws")
        if response.status_code != 200:
            raise CnpjRegistryUpstreamError(
                f"receitaws returned HTTP {response.status_code} for {cnpj}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CnpjRegistryUpstreamError(f"receitaws returned non-JSON body: {exc}") from exc
        status = str(payload.get("status") or "").upper()
        if status == "ERROR":
            mensagem = str(payload.get("message") or "")
            if _mensagem_indica_nao_encontrado(mensagem):
                raise CnpjNotFoundError(cnpj, source="receitaws")
            raise CnpjRegistryUpstreamError(f"receitaws returned an error: {mensagem!r}")
        try:
            return parse_receitaws_response(payload, cnpj)
        except (KeyError, TypeError, AttributeError) as exc:
            raise CnpjRegistryUpstreamError(
                f"receitaws response shape unexpected: {payload!r}"
            ) from exc

    async def lookup(self, cnpj: str) -> CnpjRegistryFields:
        cnpj_norm = normalize_cnpj(cnpj)

        primeiro_erro: Optional[CnpjRegistryError] = None
        try:
            return await self._buscar_brasilapi(cnpj_norm)
        except CnpjRegistryError as exc:
            primeiro_erro = exc
            logger.info(
                "cnpj_registry: brasilapi failed for %s (%s) — trying receitaws",
                cnpj_norm, exc,
            )

        try:
            return await self._buscar_receitaws(cnpj_norm)
        except CnpjRegistryError as exc:
            # Both sources failed — prefer surfacing whichever failure was
            # a DEFINITIVE not-found verdict over an inconclusive upstream
            # one (see the module header's fallback-resolution note). The
            # other failure still travels as `__cause__` so nothing about
            # the discarded attempt is silently lost.
            if isinstance(primeiro_erro, CnpjNotFoundError):
                raise primeiro_erro from exc
            raise exc from primeiro_erro


__all__ = [
    "BRASILAPI_URL",
    "DEFAULT_TIMEOUT_SECONDS",
    "RECEITAWS_URL",
    "RealCnpjRegistryLookup",
]
