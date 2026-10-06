"""Trusted legacy-JWT bridge — ``AuthContext`` from ``public.noctus_users``.

``make_get_auth_context`` accepts a ``legacy_jwt_resolver`` that turns a raw
Supabase JWT into an :class:`AuthContext`. Three products each hand-rolled that
bridge and built ``AuthContext.org_id`` from ``user.user_metadata["org_id"]`` —
a value any authenticated user can rewrite for themselves through
``supabase.auth.updateUser({data})``. With a real second tenant that is a
cross-org hole: the context fed ``get_auth_context`` /
``get_current_user_org_unified`` / ``create_auth_router`` (service-role routes,
API-token minting, cookie sessions).

:func:`make_trusted_legacy_jwt_resolver` is the single seed implementation.
The org comes ONLY from ``public.noctus_users`` (the row every product's RLS
``current_org_id()`` reads); ``user_metadata`` is never consulted.

Failure semantics (the resolver may raise ``HTTPException`` — the dep does not
swallow it):

* invalid / unverifiable JWT        → ``None`` (dep answers 401)
* valid JWT, no ``noctus_users`` row → 403 (no org membership)
* customer ``org_role``             → 403 unless ``allow_customer=True``
* effective org without a license   → 403 ``org_sem_licenca``
* DB / transport error              → 503 (fail CLOSED, never a metadata fallback)

KB § PATTERNS/backend/backend.md § Auth — canonical pattern ·
KB § PATTERNS/backend/no-metadata-authz.md
"""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any, Awaitable, Callable
from uuid import UUID

from fastapi import HTTPException

from noctusai_lib.api.auth.mfa.aal import read_aal
from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.domain.licensing import enforce_license
from noctusai_lib.primitives.roles import is_customer_role

logger = logging.getLogger(__name__)

LegacyJwtResolverFn = Callable[[str], Awaitable["AuthContext | None"]]


def _to_uuid(raw: Any) -> UUID:
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        return _uuid.uuid5(_uuid.NAMESPACE_OID, str(raw))


def make_trusted_legacy_jwt_resolver(
    get_current_user_fn: Callable[..., Awaitable[Any]],
    get_core_client_fn: Callable[[], Any],
    *,
    allow_customer: bool = False,
) -> LegacyJwtResolverFn:
    """Build the ``legacy_jwt_resolver`` for ``make_get_auth_context``.

    Args:
        get_current_user_fn: The product's JWT-verifying ``get_current_user``
            (called with ``authorization="Bearer <token>"``); returns
            ``(user, token)`` or just ``user``.
        get_core_client_fn: Zero-arg callable returning the ``public``-schema
            service-role client (``DatabaseModule.get_core_client``) — a
            product-schema client 500s with PGRST205 on ``noctus_users``.
        allow_customer: ``False`` (default) refuses a customer ``org_role``
            (403), same rule as ``make_get_current_user_org``.
    """
    from noctusai_lib.api.auth import _resolve_trusted_membership

    async def _resolver(token: str) -> AuthContext | None:
        try:
            result = await get_current_user_fn(authorization=f"Bearer {token}")
        except Exception:
            # Bad / expired JWT — the dep produces its own 401.
            return None
        user = result[0] if isinstance(result, tuple) else result
        if user is None:
            return None

        user_id_raw = getattr(user, "id", None)
        # One identity end to end: `AuthContext.user_id` (and so every
        # downstream `resolve_org_role(ctx.user_id)`) is this coerced UUID, so
        # the trusted row is looked up by the SAME value. For a real Supabase
        # user id (always a UUID) it is the identity.
        user_id = _to_uuid(user_id_raw)
        try:
            membership = _resolve_trusted_membership(get_core_client_fn, str(user_id))
        except Exception:
            logger.error(
                "trusted_legacy_bridge_lookup_error user_id=%s — failing closed "
                "(NOT falling back to user_metadata)",
                user_id_raw,
                exc_info=True,
            )
            raise HTTPException(
                status_code=503, detail="Falha ao resolver organizacao do usuario"
            )

        org_raw = membership.get("org_id") if membership else None
        if not org_raw:
            if (getattr(user, "user_metadata", None) or {}).get("org_id"):
                logger.warning(
                    "trusted_legacy_bridge_no_row user_id=%s — user_metadata names "
                    "an org, IGNORED for authorization",
                    user_id_raw,
                )
            raise HTTPException(
                status_code=403, detail="Usuario sem organizacao associada"
            )
        if not allow_customer and is_customer_role(membership.get("org_role")):
            raise HTTPException(status_code=403, detail="Área restrita à equipe.")
        # Round-2 license gate on the EFFECTIVE org (acting ⇒ the target org).
        enforce_license(org_raw, membership.get("org_role"), allow_customer=allow_customer)

        return AuthContext(
            org_id=_to_uuid(org_raw),
            caller_kind="user",
            user_id=user_id,
            scopes=[],
            raw_token=token,  # JWT — preserves the bearer for legacy callers
            api_token_id=None,
            aal=read_aal(token, validated_user=user),
        )

    return _resolver


__all__ = ["make_trusted_legacy_jwt_resolver", "LegacyJwtResolverFn"]
