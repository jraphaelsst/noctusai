"""social-wiring bridge client — the E.6 "One Chat" auto-reply toggle
(contract §E.6, ``projects/julia-agents-academia-CONTRACT.md``).

Seed IO shape: ``SocialWiringClient`` Protocol + ``FakeSocialWiringClient``
(in-memory, deterministic) + ``HttpSocialWiringClient`` (Real, over
``httpx.AsyncClient``) + ``get_social_wiring_client(settings)`` factory.
See ``KB § PATTERNS/backend/seed-fake-real-adapter.md``.

Calls exactly the two E.6 routes:

  - ``GET  /api/agents-bridge/one-chat/{connection_id}``
  - ``PUT  /api/agents-bridge/one-chat/{connection_id}/auto-reply``

Auth: ``Authorization: Bearer <settings.social_wiring_api_token>`` — a
product token scoped to ``social-wiring:one-chat:read`` +
``:toggle`` only, held by THIS product (never logged; never the raw
secret's value in an exception message).

The caller (``app/routers/agents_router.py``) decides what a failure
means per-route: ``GET /api/agents`` swallows :class:`SocialWiringUnreachable`
into ``estado_externo=None`` + an ``aviso`` string; the toggle route maps it
to ``502 upstream_failed``.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0


class SocialWiringError(Exception):
    """Base class for every social-wiring bridge client error."""


class SocialWiringUnreachable(SocialWiringError):
    """The upstream call failed — network error, timeout, or a non-2xx
    response. Never carries the raw bearer token in its message."""


class SocialWiringClient(Protocol):
    async def get_one_chat_state(self, connection_id: UUID) -> dict[str, Any]:
        """Returns ``{connection_id, label, auto_reply_enabled}``. Raises
        :class:`SocialWiringUnreachable` on any upstream failure — the
        caller decides what that means (contract §E.2: ``null`` +
        ``aviso`` for ``GET /api/agents``)."""
        ...

    async def set_one_chat_auto_reply(
        self, connection_id: UUID, enabled: bool
    ) -> dict[str, Any]:
        """Returns ``{connection_id, auto_reply_enabled}``. Raises
        :class:`SocialWiringUnreachable` on any upstream failure — the
        caller maps that to ``502 upstream_failed`` (contract §E.2)."""
        ...


class FakeSocialWiringClient:
    """In-memory :class:`SocialWiringClient` — tests seed state via
    ``register(...)`` / force a failure via ``fail_connection_ids``."""

    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}
        #: connection_ids (str) that raise `SocialWiringUnreachable` on
        #: every call, regardless of registered state — simulates the
        #: upstream being down.
        self.fail_connection_ids: set[str] = set()

    def register(
        self, connection_id: UUID, *, label: str = "Fake connection",
        auto_reply_enabled: bool = False,
    ) -> None:
        self._states[str(connection_id)] = {
            "connection_id": str(connection_id),
            "label": label,
            "auto_reply_enabled": auto_reply_enabled,
        }

    async def get_one_chat_state(self, connection_id: UUID) -> dict[str, Any]:
        key = str(connection_id)
        if key in self.fail_connection_ids:
            raise SocialWiringUnreachable(f"connection {key} marked unreachable")
        state = self._states.get(key)
        if state is None:
            raise SocialWiringUnreachable(f"connection {key} not found upstream")
        return dict(state)

    async def set_one_chat_auto_reply(
        self, connection_id: UUID, enabled: bool
    ) -> dict[str, Any]:
        key = str(connection_id)
        if key in self.fail_connection_ids:
            raise SocialWiringUnreachable(f"connection {key} marked unreachable")
        state = self._states.setdefault(
            key,
            {"connection_id": key, "label": "Fake connection", "auto_reply_enabled": False},
        )
        state["auto_reply_enabled"] = enabled
        return {"connection_id": key, "auto_reply_enabled": enabled}


class HttpSocialWiringClient:
    """Real :class:`SocialWiringClient` — HTTP over ``httpx.AsyncClient``.

    ``transport`` is an optional DI seam (``httpx.ASGITransport`` in
    tests, ``None`` — real network — in production) — lets tests exercise
    THIS class's actual request/response/error-mapping code against a
    stub ASGI app instead of re-implementing the HTTP call inline.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def get_one_chat_state(self, connection_id: UUID) -> dict[str, Any]:
        url = f"{self._base_url}/api/agents-bridge/one-chat/{connection_id}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            logger.warning(
                "social_wiring_bridge_unreachable connection_id=%s op=get error=%s",
                connection_id,
                type(exc).__name__,
            )
            raise SocialWiringUnreachable(
                f"GET one-chat/{connection_id} failed: {type(exc).__name__}"
            ) from exc

    async def set_one_chat_auto_reply(
        self, connection_id: UUID, enabled: bool
    ) -> dict[str, Any]:
        url = f"{self._base_url}/api/agents-bridge/one-chat/{connection_id}/auto-reply"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                resp = await client.put(
                    url, json={"enabled": enabled}, headers=self._headers()
                )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            logger.warning(
                "social_wiring_bridge_unreachable connection_id=%s op=toggle error=%s",
                connection_id,
                type(exc).__name__,
            )
            raise SocialWiringUnreachable(
                f"PUT one-chat/{connection_id}/auto-reply failed: {type(exc).__name__}"
            ) from exc


def get_social_wiring_client(settings: Any) -> SocialWiringClient:
    """Real when a bridge token resolves (DB-first, env fallback —
    ``app/credentials/resolver.py``); ``FakeSocialWiringClient`` otherwise
    (dev/test — no product token minted yet). Built per request, so a token
    renewed on the Credenciais page is used by the next call."""
    from app.credentials.resolver import get_credential_resolver

    token = get_credential_resolver(settings).social_wiring_api_token() or ""
    if not token:
        return FakeSocialWiringClient()

    from noctusai_lib.config.product_urls import resolve_product_url

    base_url = resolve_product_url("social-wiring")
    return HttpSocialWiringClient(base_url, token)


__all__ = [
    "FakeSocialWiringClient",
    "HttpSocialWiringClient",
    "SocialWiringClient",
    "SocialWiringError",
    "SocialWiringUnreachable",
    "get_social_wiring_client",
]
