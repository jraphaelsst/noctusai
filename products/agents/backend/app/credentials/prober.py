"""Live health check for one credential value — the "Testar" button.

Seed IO shape: ``CredentialProber`` Protocol + ``FakeCredentialProber`` +
``HttpCredentialProber`` + ``get_credential_prober()`` factory
(``KB § PATTERNS/backend/seed-fake-real-adapter.md``).

Each probe is the cheapest authenticated READ the credential is for:

- academia token → ``GET /api/decisions`` (``academia:read``, contract §B.2).
- social-wiring token → ``GET /api/agents-bridge/one-chat/{connection_id}``
  (§E.6). With no connection configured yet the nil UUID is probed: a 404
  can only come AFTER auth + scope + issuer checks passed, so it proves the
  token works.
- Anthropic key → ``GET https://api.anthropic.com/v1/models`` (lists models;
  spends no tokens).

The secret is only ever placed in the request header — never in a log line,
an exception message, or the returned result.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Literal, Protocol
from uuid import UUID

import httpx

from app.credentials.registry import (
    ACADEMIA_API_TOKEN,
    ANTHROPIC_API_KEY,
    SOCIAL_WIRING_API_TOKEN,
    CredentialSpec,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CredentialProber",
    "FakeCredentialProber",
    "HttpCredentialProber",
    "ProbeResult",
    "ProbeStatus",
    "get_credential_prober",
]

ProbeStatus = Literal["ok", "unauthorized", "forbidden", "unreachable", "error"]

_NIL_UUID = UUID("00000000-0000-0000-0000-000000000000")
_ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
_ANTHROPIC_VERSION = "2023-06-01"
_TIMEOUT_SECONDS = 10.0

_MESSAGES: dict[str, str] = {
    "ok": "Credencial válida.",
    "unauthorized": "Credencial recusada (401) — inválida, revogada ou expirada.",
    "forbidden": "Credencial aceita mas sem permissão (403) — escopo ou emissor incorreto.",
    "unreachable": "Serviço de destino indisponível.",
    "error": "Resposta inesperada do serviço de destino.",
}


@dataclass(frozen=True)
class ProbeResult:
    status: ProbeStatus
    http_status: int | None
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @classmethod
    def of(cls, status: ProbeStatus, http_status: int | None = None, detail: str | None = None) -> "ProbeResult":
        return cls(status=status, http_status=http_status, detail=detail or _MESSAGES[status])


class CredentialProber(Protocol):
    async def probe(
        self, spec: CredentialSpec, secret: str, *, connection_id: UUID | None = None
    ) -> ProbeResult: ...


class FakeCredentialProber:
    """Deterministic prober. ``results[spec.name]`` overrides the default
    ``ok``; ``calls`` records ``(name, secret)`` so a test can assert WHICH
    value was probed (e.g. the freshly minted token, not the old one)."""

    def __init__(self) -> None:
        self.results: dict[str, ProbeResult] = {}
        self.by_secret: dict[str, ProbeResult] = {}
        self.calls: list[tuple[str, str]] = []

    async def probe(
        self, spec: CredentialSpec, secret: str, *, connection_id: UUID | None = None
    ) -> ProbeResult:
        self.calls.append((spec.name, secret))
        if secret in self.by_secret:
            return self.by_secret[secret]
        return self.results.get(spec.name, ProbeResult.of("ok", 200))


def _classify(status_code: int, *, not_found_is_ok: bool) -> ProbeResult:
    if 200 <= status_code < 300 or (not_found_is_ok and status_code == 404):
        return ProbeResult.of("ok", status_code)
    if status_code == 401:
        return ProbeResult.of("unauthorized", status_code)
    if status_code == 403:
        return ProbeResult.of("forbidden", status_code)
    if status_code >= 500:
        return ProbeResult.of("unreachable", status_code)
    return ProbeResult.of("error", status_code)


class HttpCredentialProber:
    """Real prober over ``httpx``. ``transport`` is the test seam
    (``httpx.MockTransport``); ``base_url_for`` resolves a product slug to
    its URL (``resolve_product_url`` in production)."""

    def __init__(
        self,
        *,
        base_url_for: Callable[[str], str],
        transport: httpx.AsyncBaseTransport | None = None,
        anthropic_models_url: str = _ANTHROPIC_MODELS_URL,
    ) -> None:
        self._base_url_for = base_url_for
        self._transport = transport
        self._anthropic_url = anthropic_models_url

    async def probe(
        self, spec: CredentialSpec, secret: str, *, connection_id: UUID | None = None
    ) -> ProbeResult:
        not_found_is_ok = False
        params: dict[str, int] | None = None
        if spec.name == ACADEMIA_API_TOKEN.name:
            url = f"{self._base_url_for('academia-de-reciclagem').rstrip('/')}/api/decisions"
            headers = {"Authorization": f"Bearer {secret}"}
        elif spec.name == SOCIAL_WIRING_API_TOKEN.name:
            target = connection_id or _NIL_UUID
            url = f"{self._base_url_for('social-wiring').rstrip('/')}/api/agents-bridge/one-chat/{target}"
            headers = {"Authorization": f"Bearer {secret}"}
            not_found_is_ok = True
        elif spec.name == ANTHROPIC_API_KEY.name:
            url = self._anthropic_url
            headers = {"x-api-key": secret, "anthropic-version": _ANTHROPIC_VERSION}
            params = {"limit": 1}
        else:
            return ProbeResult.of("error", None, "Esta credencial não tem teste ao vivo.")
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, transport=self._transport) as client:
                resp = await client.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            logger.warning("agents.credential_probe credential=%s error=%s", spec.name, type(exc).__name__)
            return ProbeResult.of("unreachable")
        result = _classify(resp.status_code, not_found_is_ok=not_found_is_ok)
        logger.info(
            "agents.credential_probe credential=%s status=%s http=%s",
            spec.name, result.status, resp.status_code,
        )
        return result


def get_credential_prober() -> CredentialProber:
    from noctusai_lib.config.product_urls import resolve_product_url

    return HttpCredentialProber(base_url_for=resolve_product_url)
