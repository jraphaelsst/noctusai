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
from collections.abc import Callable
from typing import Any, Protocol
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0

#: Lais F-AG (build contract §2.1(c)/(f)): the per-org callback token SW mints
#: for agents (scope ``social-wiring:lais-tools``). Stored encrypted through the
#: SAME per-org writer the api-keys router uses (``agents.credentials``).
LAIS_TOOLS_TOKEN_KEY = "social_wiring_lais_tools_token"
#: A read tool must answer inside this; past it the model is told to carry on.
LAIS_TOOL_TIMEOUT_SECONDS = 8.0
#: What a tool call returns when SW cannot answer (never an exception text).
LAIS_TOOL_UNAVAILABLE: dict[str, Any] = {"erro": "indisponivel"}


def resolve_lais_tools_token(
    org_id: UUID | str,
    *,
    store_factory: Callable[[], Any] | None = None,
    org_settings_reader: Callable[[str, str], str | None] | None = None,
) -> str | None:
    """THIS org's tools token, or ``None``. Never a process-wide fallback:
    the encrypted per-org store first, then this org's own ``org_settings`` row
    (``resolve_org_credential`` — it cannot reach platform settings or env)."""
    from noctusai_lib.config.credentials import resolve_org_credential
    from noctusai_lib.security.api_keys import EncryptionNotConfigured, read_local_api_key

    org = str(org_id)
    reader = org_settings_reader or resolve_org_credential
    if store_factory is None:
        from app.credentials.org_keys import build_llm_key_store

        store_factory = build_llm_key_store
    try:
        store = store_factory()
    except EncryptionNotConfigured as exc:
        logger.warning("agents.lais_tools_token.store_unavailable: %s", exc)
        store = None
    if store is not None:
        stored = read_local_api_key(store, org, LAIS_TOOLS_TOKEN_KEY)
        value = (stored.tokens or {}).get("value") if stored else None
        if value:
            return value
    return reader(LAIS_TOOLS_TOKEN_KEY, org) or None


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

    def lais_tools_available(self, org_id: UUID) -> bool:
        """``True`` when THIS org has a tools token (read tools are exposed
        to the model only then — never a process-wide fallback)."""
        ...

    async def lais_ferramenta(self, org_id: UUID, nome: str, args: dict[str, Any]) -> dict[str, Any]:
        """``POST /api/julia/ferramentas/{nome}`` with the org's token. Never
        raises: any failure / timeout (8 s) returns ``{"erro": "indisponivel"}``."""
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
        #: Lais tools: orgs holding a token, canned answers by tool name (a
        #: dict, or a callable ``args -> dict``), the call log, a failure switch.
        self.lais_token_orgs: set[UUID] = set()
        self.lais_responses: dict[str, Any] = {}
        self.lais_calls: list[tuple[UUID, str, dict[str, Any]]] = []
        self.lais_fail = False

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


    def lais_tools_available(self, org_id: UUID) -> bool:
        return org_id in self.lais_token_orgs

    async def lais_ferramenta(self, org_id: UUID, nome: str, args: dict[str, Any]) -> dict[str, Any]:
        self.lais_calls.append((org_id, nome, dict(args)))
        if self.lais_fail or org_id not in self.lais_token_orgs:
            return dict(LAIS_TOOL_UNAVAILABLE)
        answer = self.lais_responses.get(nome, {"data": []})
        return dict(answer(args) if callable(answer) else answer)


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
        lais_token_resolver: Callable[[UUID], str | None] | None = None,
        lais_timeout: float = LAIS_TOOL_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._transport = transport
        self._lais_token_resolver = lais_token_resolver or resolve_lais_tools_token
        self._lais_timeout = lais_timeout

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


    def lais_tools_available(self, org_id: UUID) -> bool:
        return bool(self._lais_token_resolver(org_id))

    async def lais_ferramenta(self, org_id: UUID, nome: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            token = self._lais_token_resolver(org_id)
        except Exception:
            logger.exception("agents.lais_tool.token_lookup_failed org_id=%s tool=%s", org_id, nome)
            return dict(LAIS_TOOL_UNAVAILABLE)
        if not token:
            return dict(LAIS_TOOL_UNAVAILABLE)
        url = f"{self._base_url}/api/julia/ferramentas/{nome}"
        try:
            async with httpx.AsyncClient(timeout=self._lais_timeout, transport=self._transport) as client:
                resp = await client.post(url, json=args, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "agents.lais_tool.unavailable org_id=%s tool=%s error=%s", org_id, nome, type(exc).__name__
            )
            return dict(LAIS_TOOL_UNAVAILABLE)
        return body if isinstance(body, dict) else {"data": body}


def get_lais_tools_client(settings: Any = None) -> SocialWiringClient:
    """The client the Lais READ tools use: always Real (the token is per call,
    per org — an org with no token simply has no tools). Fake/Real selection for
    tests is by dependency override, never by this factory."""
    from noctusai_lib.config.product_urls import resolve_product_url

    return HttpSocialWiringClient(resolve_product_url("social-wiring"), "")


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
    "LAIS_TOOLS_TOKEN_KEY",
    "LAIS_TOOL_TIMEOUT_SECONDS",
    "LAIS_TOOL_UNAVAILABLE",
    "get_lais_tools_client",
    "resolve_lais_tools_token",
    "FakeSocialWiringClient",
    "HttpSocialWiringClient",
    "SocialWiringClient",
    "SocialWiringError",
    "SocialWiringUnreachable",
    "get_social_wiring_client",
]
