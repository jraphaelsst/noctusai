"""Core's ONE ``get_auth_context`` and the M2M token surface built on it.

One dependency resolves every kind of caller (cookie session -> ``noc_`` bearer, legacy ``pk_``
still accepted -> Supabase JWT -> 401). The transcription API, the seed token-management routes
and the audit middleware all use this single composition -- there is no second resolver.

``NOC-REMEDIATE[pk-prefix-cutoff]``: ``pk_`` tokens stay accepted (seed resolver) until every live
token has been reissued as ``noc_``; the cutoff ships last (Julia-line CONTRACT §D6).

Token MANAGEMENT (mint / rotate / revoke / list, ``/api/settings/api-tokens``) is restricted to
platform admins here: a core token carries platform scopes (``reminders:write``), which an ordinary
customer-org admin must never be able to grant themselves.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable, Optional

from fastapi import Depends, HTTPException, Request, Response
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.platform import resolve_platform_admin_role
from noctusai_lib.api.auth.session import (
    AuthContext,
    make_api_token_audit_writer,
    make_api_token_resolver,
    make_get_auth_context,
    make_trusted_legacy_jwt_resolver,
)
from noctusai_seed.auth_router import create_auth_router, get_session_store

from app import database
from app.config import settings
from app.dependencies import deps, get_current_user
from app.services import api_tokens
from app.services.trusted_auth import get_trusted_db

SESSION_COOKIE = "nai_session"


_admin_client_factory: Optional[Callable[[], Any]] = None


def configure_token_db(factory: Optional[Callable[[], Any]]) -> None:
    """DI seam for the token surface's DB client (tests pass a fake; ``None`` restores production)."""
    global _admin_client_factory
    _admin_client_factory = factory


def _admin() -> Any:
    """Service-role ``public`` client, resolved at call time (never bound at import)."""
    return (_admin_client_factory or database.get_admin_client)()


class _LazySessionStore:
    """Resolved on first use: the Redis store needs live settings."""

    async def create(self, **kwargs):
        return await get_session_store(settings).create(**kwargs)

    async def lookup(self, session_id):
        return await get_session_store(settings).lookup(session_id)

    async def refresh_ttl(self, session_id, ttl_seconds=86400):
        return await get_session_store(settings).refresh_ttl(session_id, ttl_seconds)

    async def delete(self, session_id):
        return await get_session_store(settings).delete(session_id)


class LazyApiTokenResolver:
    """``public.api_tokens`` resolver over the client of the moment (needs the live admin client, so
    never bound at import). The resolver is a thin stateless wrapper over the cached client, so it is
    rebuilt per call rather than held -- the DI seam (``configure_token_db``) then always applies.

    In a deploy context the seed factory refuses the Fake, so a missing service-role key is a loud
    error on the first request, never a resolver that silently 401s every token."""

    async def resolve(self, token_secret):
        return await make_api_token_resolver(_admin(), schema="public").resolve(token_secret)


class LazyAuditWriter:
    """``api_token_audit`` writer for ``ApiTokenAuditMiddleware`` (same per-call construction)."""

    async def record(self, **kwargs):
        return await make_api_token_audit_writer(_admin(), schema="public").record(**kwargs)


legacy_jwt_resolver = make_trusted_legacy_jwt_resolver(
    lambda authorization: get_current_user(authorization=authorization),
    lambda: deps.get_core_client(),
)

get_auth_context = make_get_auth_context(
    session_store=_LazySessionStore(),
    api_token_resolver=LazyApiTokenResolver(),
    legacy_jwt_resolver=legacy_jwt_resolver,
    session_cookie_name=SESSION_COOKIE,
)


async def get_token_admin_context(
    ctx: AuthContext = Depends(get_auth_context),
    db: Any = Depends(get_trusted_db),
    request: Request = None,
    response: Response = None,
) -> AuthContext:
    """``get_auth_context`` for the token-management routes: a human must also be a PLATFORM admin.

    A non-human caller passes straight through -- the seed routes refuse it themselves (403, humans
    only), so a token can never mint another token."""
    if ctx.caller_kind != "user":
        return ctx
    if await run_blocking(resolve_platform_admin_role, db, ctx.user_id) != "admin":
        raise HTTPException(
            status_code=403,
            detail={"detail": "Restrito a administradores da plataforma NoctusAI", "code": "platform_admin_required"},
        )
    return ctx


def build_tokens_router():
    """The seed token routes (mint/list/revoke/rotate/scopes), wired to core's policy."""
    # ``public`` is core's own schema, so ONE service-role client serves both api_tokens and noctus_users.
    token_deps = SimpleNamespace(get_admin_client=_admin, get_core_client=_admin)
    return create_auth_router(
        token_deps,
        settings,
        include_session_routes=False,  # core owns /api/auth/login|me|logout (routers/auth.py)
        get_auth_context=get_token_admin_context,
        scope_allow_list=api_tokens.CORE_TOKEN_SCOPES,
        mint_policy=api_tokens.make_mint_policy(_admin),
        service_account_check=api_tokens.make_service_account_check(_admin),
    )
