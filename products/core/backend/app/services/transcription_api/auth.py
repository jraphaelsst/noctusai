"""Auth for the transcription API (CONTRACT §1) — seed session dependency.

Two caller kinds through ONE dependency (``make_get_auth_context``): a
``pk_*`` product token resolved against ``public.api_tokens`` (needs scope
``transcription:write`` to submit/cancel, ``transcription:read`` to read) or a
normal platform session (Bearer JWT / session cookie), same quotas.

A missing/invalid credential stays the seed's strict 401. A refused scope or
role is mapped to the API's ``{codigo: escopo_insuficiente}`` 403.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from fastapi import HTTPException, Request, Response
from noctusai_lib.api.auth.platform import require_platform_admin
from noctusai_lib.api.auth.session import (
    AuthContext,
    SupabaseApiTokenResolver,
    make_get_auth_context,
    make_trusted_legacy_jwt_resolver,
    require_scopes,
)
from noctusai_lib.primitives.roles import ORG_ROLES

from app.services.transcription_api.errors import TranscricaoErro

SCOPE_WRITE = "transcription:write"
SCOPE_READ = "transcription:read"

#: Seed 403 codes that all mean "this credential may not do this".
_SCOPE_REFUSALS = frozenset(
    {"scope_missing", "role_missing", "platform_admin_required", "product_required", "user_required"}
)

Guard = Callable[..., Awaitable[AuthContext]]


class TranscricaoAuth:
    """Resolves the caller and applies the per-operation guard."""

    def __init__(
        self,
        *,
        get_auth_context: Callable[..., Awaitable[AuthContext]],
        require_write: Guard,
        require_read: Guard,
        require_admin: Guard,
    ) -> None:
        self._get_auth_context = get_auth_context
        self._guards = {"write": require_write, "read": require_read, "admin": require_admin}

    async def authenticate(
        self, kind: str, request: Request, response: Response,
        authorization: Optional[str], session_cookie: Optional[str],
    ) -> AuthContext:
        # 401 comes straight from the seed dependency (strict, never remapped).
        ctx = await self._get_auth_context(
            request=request, authorization=authorization, session_cookie=session_cookie
        )
        try:
            return await self._guards[kind](ctx, request, response)
        except HTTPException as exc:
            detail = exc.detail
            if exc.status_code == 403 and isinstance(detail, dict) and detail.get("code") in _SCOPE_REFUSALS:
                raise TranscricaoErro("escopo_insuficiente") from exc
            raise


def build_auth(
    *,
    session_store: Any,
    api_token_resolver: Any,
    legacy_jwt_resolver: Any,
    get_core_client: Callable[[], Any],
    session_cookie_name: str = "nai_session",
) -> TranscricaoAuth:
    """Compose the seed pieces. Production passes the Supabase/Redis adapters;
    tests pass the seed Fakes — the composition is identical."""
    get_auth_context = make_get_auth_context(
        session_store=session_store,
        api_token_resolver=api_token_resolver,
        legacy_jwt_resolver=legacy_jwt_resolver,
        session_cookie_name=session_cookie_name,
    )
    roles = frozenset(ORG_ROLES)

    def scoped(scope: str) -> Guard:
        return require_scopes(
            scope, user_roles=roles, get_auth_context=get_auth_context, get_core_client=get_core_client
        )

    return TranscricaoAuth(
        get_auth_context=get_auth_context,
        require_write=scoped(SCOPE_WRITE),
        require_read=scoped(SCOPE_READ),
        require_admin=require_platform_admin(
            get_auth_context=get_auth_context, get_core_client=get_core_client
        ),
    )


def build_default_auth() -> TranscricaoAuth:
    """Production composition for core: ``public.api_tokens`` resolver, the
    seed process-local session store, trusted legacy-JWT bridge."""
    from noctusai_seed.auth_router import get_session_store

    from app.config import settings
    from app.dependencies import deps, get_current_user

    class _LazySessionStore:
        """Resolved on first use: the Redis store needs live settings."""

        async def lookup(self, session_id):
            return await get_session_store(settings).lookup(session_id)

    class _LazyTokenResolver:
        _real: Optional[SupabaseApiTokenResolver] = None

        async def resolve(self, token_secret):
            if self._real is None:
                self._real = SupabaseApiTokenResolver(deps.get_admin_client(), schema="public")
            return await self._real.resolve(token_secret)

    return build_auth(
        session_store=_LazySessionStore(),
        api_token_resolver=_LazyTokenResolver(),
        legacy_jwt_resolver=make_trusted_legacy_jwt_resolver(
            lambda authorization: get_current_user(authorization=authorization),
            lambda: deps.get_core_client(),
        ),
        get_core_client=lambda: deps.get_core_client(),
    )
