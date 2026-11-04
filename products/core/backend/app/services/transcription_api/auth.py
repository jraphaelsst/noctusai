"""Auth for the transcription API (CONTRACT §1) — seed session dependency.

Two caller kinds through ONE dependency (``make_get_auth_context``): a
``noc_*`` (legacy ``pk_*``) product token resolved against ``public.api_tokens`` (needs scope
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
    make_get_auth_context,
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
    session_store: Any = None,
    api_token_resolver: Any = None,
    legacy_jwt_resolver: Any = None,
    get_core_client: Callable[[], Any],
    session_cookie_name: str = "nai_session",
    get_auth_context: Optional[Callable[..., Awaitable[AuthContext]]] = None,
) -> TranscricaoAuth:
    """Compose the guards over ONE auth-context dependency.

    Production passes core's shared ``app.auth_context.get_auth_context`` (``build_default_auth``);
    tests pass the seed Fakes and a dependency is composed from them -- the composition is identical."""
    if get_auth_context is None:
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
    """Production composition for core: the shared ``app.auth_context.get_auth_context``
    (``public.api_tokens`` resolver, process session store, trusted legacy-JWT bridge)."""
    from app.auth_context import get_auth_context
    from app.dependencies import deps

    return build_auth(get_auth_context=get_auth_context, get_core_client=lambda: deps.get_core_client())
