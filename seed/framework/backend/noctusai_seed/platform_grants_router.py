"""Platform-grant RECEIVER router factory (product side of a grant).

    PUT    /api/platform/grants/{issuer}   {credential, agent_id?, metadata?} -> 204
    DELETE /api/platform/grants/{issuer}                                      -> 204

The control plane (``agents``) delivers through
``noctusai_lib.api.auth.grants.GrantDelivery`` with a one-shot delivery token.

Security shape:

* The **org comes from the authenticated delivery token** (``ctx.org_id``),
  never the body — the body model forbids extra fields, so a smuggled
  ``org_id`` is a 422.
* No/invalid token -> strict **401** (from the product's ``get_auth_context``).
* A token without scope ``platform:grant-receive``, not minted by the
  configured ``issuer``, or a path ``{issuer}`` other than the configured one
  -> **403**. A user session is refused too (403, ``product_required``).
* Storage is the product's concern: the router hands a :class:`GrantReceived`
  to the product-supplied ``on_grant`` sink (sync or async) and never logs or
  echoes the credential.

Decoupling: imports nothing from ``app.*``; every product concern is a kwarg
(Class-B DI seam). See ``KB § PATTERNS/backend/platform-grants.md``.
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session.token_policy import GRANT_RECEIVE_SCOPE
from noctusai_lib.api.auth.session.types import AuthContext

logger = logging.getLogger(__name__)

__all__ = [
    "GrantReceived",
    "GrantRevoked",
    "create_platform_grants_router",
]

_Maybe = Union[None, Awaitable[None]]


@dataclass(frozen=True)
class GrantReceived:
    """What the product's sink stores. ``credential`` is a secret — encrypt it."""

    org_id: UUID
    issuer: str
    credential: str
    agent_id: Optional[str]
    metadata: dict[str, Any]
    delivery_token_id: Optional[UUID]


@dataclass(frozen=True)
class GrantRevoked:
    org_id: UUID
    issuer: str


class _GrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: str = Field(min_length=8, max_length=4096)
    agent_id: Optional[str] = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


async def _call(fn: Callable[[Any], _Maybe], arg: Any) -> None:
    if inspect.iscoroutinefunction(fn):
        await fn(arg)
        return
    result = await run_blocking(lambda: fn(arg))
    if inspect.isawaitable(result):
        await result


def create_platform_grants_router(
    *,
    get_auth_context: Callable[..., Any],
    on_grant: Callable[[GrantReceived], _Maybe],
    on_revoke: Callable[[GrantRevoked], _Maybe],
    issuer: str = "agents",
    scope: str = GRANT_RECEIVE_SCOPE,
) -> APIRouter:
    """Build the receiver router.

    Args:
        get_auth_context: the product's ``make_get_auth_context(...)`` dep
            (401 on a missing/invalid credential).
        on_grant: product sink storing the credential (``GrantReceived``).
        on_revoke: product sink dropping it (``GrantRevoked``).
        issuer: the only control plane accepted (default ``"agents"``).
        scope: the scope the delivery token must carry.
    """
    router = APIRouter(prefix="/api/platform/grants", tags=["platform-grants"])

    def _authorize(ctx: AuthContext, path_issuer: str) -> None:
        if ctx.caller_kind != "product":
            raise HTTPException(status_code=403, detail="product_required")
        if scope not in ctx.scopes:
            raise HTTPException(status_code=403, detail="scope_missing")
        if ctx.issuer != issuer or path_issuer != issuer:
            raise HTTPException(status_code=403, detail="issuer_not_allowed")

    @router.put("/{path_issuer}", status_code=204)
    async def receive_grant(
        path_issuer: str,
        body: _GrantBody,
        ctx: AuthContext = Depends(get_auth_context),
    ) -> Response:
        _authorize(ctx, path_issuer)
        try:
            await _call(
                on_grant,
                GrantReceived(
                    org_id=ctx.org_id,
                    issuer=issuer,
                    credential=body.credential,
                    agent_id=body.agent_id,
                    metadata=dict(body.metadata),
                    delivery_token_id=ctx.api_token_id,
                ),
            )
        except Exception:
            logger.exception("platform_grant_store_failed org=%s issuer=%s", ctx.org_id, issuer)
            raise HTTPException(status_code=500, detail="grant_store_failed")
        return Response(status_code=204)

    @router.delete("/{path_issuer}", status_code=204)
    async def revoke_grant(
        path_issuer: str,
        ctx: AuthContext = Depends(get_auth_context),
    ) -> Response:
        _authorize(ctx, path_issuer)
        try:
            await _call(on_revoke, GrantRevoked(org_id=ctx.org_id, issuer=issuer))
        except Exception:
            logger.exception("platform_grant_revoke_failed org=%s issuer=%s", ctx.org_id, issuer)
            raise HTTPException(status_code=500, detail="grant_revoke_failed")
        return Response(status_code=204)

    return router
