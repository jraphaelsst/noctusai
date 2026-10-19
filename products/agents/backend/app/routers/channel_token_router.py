"""``/api/agents/{agent_key}/channel-token`` — mint / revoke the channel token
(Lais contract §4, §10.1 M1, §10.2 "§4 reuses existing minting").

The token social-wiring holds to drive ``julia`` over the channel turn API.
It REUSES the platform's one minting path — the seed ``ProductTokenAdmin.mint``
(the same row builder as ``POST /api/settings/api-tokens``; only a SHA-256 of
the secret is stored, the raw ``pk_*`` is returned exactly once) — with:

* ``principal_agent_id`` = the agent's own id (the channel route refuses a token
  bound to any other agent);
* ``issuer`` = the transport (``social-wiring``) — set here, server-side, never
  from request input beyond a one-value Literal; the channel routes read it back
  off the STORED row;
* scopes from the server-side registry (:data:`CHANNEL_TOKEN_SCOPES`) — a
  request cannot widen them;
* TTL ``settings.channel_token_ttl_days`` (30);
* admin only (``require_admin``: a human org owner/admin, never a token).

Rotation is OVERLAPPING by construction: minting never revokes an older token,
so the admin pastes the new one into social-wiring, then revokes the old one
(``DELETE`` below, or the seed api-tokens admin). Every mint and revoke is
audit-logged (``app.channels.token_audit``).
"""
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.channels.token_audit import TokenAudit
from app.config import settings
from app.dependencies import (
    CHANNEL_ALLOWED_ISSUERS,
    CHANNEL_TOKEN_SCOPES,
    MINTABLE_TOKEN_SCOPES,
    SCOPE_CHANNEL_STATUS,
    SCOPE_CHANNEL_TURN,
    get_product_token_admin_dep,
    get_token_audit_dep,
    require_admin,
)
from app.routers.channels_router import CHANNEL_STUDIO_RUNTIME
from app.routers.studio_agents_router import get_studio_definition_store_dep
from app.schemas.channels import ChannelTokenCreateRequest, ChannelTokenOut
from app.stores.errors import NotFound
from app.studio.julia import JULIA_KEY, canonical_channel_agent_key, ensure_julia
from noctusai_lib.api.auth.session import AuthContext, ProductTokenAdmin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["channels"])

#: The product schema the token lives in (agents' own `api_tokens`, 007).
_TOKEN_SCHEMA = "agents"
_SCOPES = [SCOPE_CHANNEL_TURN, SCOPE_CHANNEL_STATUS]


def _err(status_code: int, code: str, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"detail": detail, "code": code})


def _channel_agent(studio_store, ctx: AuthContext, agent_key: str):
    agent_key = canonical_channel_agent_key(agent_key)
    if agent_key == JULIA_KEY:
        # First use for this org: seed the draft agent so there is something to bind to.
        ensure_julia(ctx.org_id, studio_store=studio_store, created_by=ctx.user_id)
    try:
        agent = studio_store.get_agent(ctx.org_id, agent_key)
    except NotFound as exc:
        raise _err(404, "agent_not_found", "Agente não encontrado.") from exc
    if agent.definition_mode != "studio" or agent.runtime != CHANNEL_STUDIO_RUNTIME:
        raise _err(404, "agent_not_found", "Agente não encontrado.")
    return agent


@router.post("/{agent_key}/channel-token", response_model=ChannelTokenOut, status_code=status.HTTP_201_CREATED)
async def mint_channel_token(
    agent_key: str,
    payload: ChannelTokenCreateRequest,
    response: Response,
    ctx: AuthContext = Depends(require_admin),
    studio_store=Depends(get_studio_definition_store_dep),
    token_admin: ProductTokenAdmin = Depends(get_product_token_admin_dep),
    audit: TokenAudit = Depends(get_token_audit_dep),
) -> ChannelTokenOut:
    agent = _channel_agent(studio_store, ctx, agent_key)
    # Registry check by construction: the scopes are this module's constant, and
    # the issuer a one-value Literal — assert they stay inside the server-side sets.
    assert set(_SCOPES) <= MINTABLE_TOKEN_SCOPES and set(_SCOPES) == CHANNEL_TOKEN_SCOPES
    assert payload.product in CHANNEL_ALLOWED_ISSUERS
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.channel_token_ttl_days)
    try:
        minted = token_admin.mint(
            _TOKEN_SCHEMA,
            org_id=ctx.org_id,
            label=f"canal {payload.product} · {agent_key}: {payload.label}",
            scopes=list(_SCOPES),
            expires_at=expires_at,
            principal_agent_id=agent.id,
            issuer=payload.product,
            minted_by=ctx.user_id,
        )
    except Exception as exc:
        logger.error("agents.channel_token.mint_failed org_id=%s error=%s", ctx.org_id, type(exc).__name__)
        raise _err(502, "mint_failed", "Falha ao emitir o token.") from exc
    try:
        audit.record(
            api_token_id=minted.info.id, org_id=ctx.org_id, action="MINT",
            agent_key=agent_key, actor_user_id=ctx.user_id, status=201,
        )
    except Exception as exc:
        # An unaudited token must not exist: revoke it and fail the call.
        logger.error("agents.channel_token.audit_failed org_id=%s error=%s", ctx.org_id, type(exc).__name__)
        token_admin.revoke(_TOKEN_SCHEMA, minted.info.id, org_id=ctx.org_id)
        raise _err(502, "audit_failed", "Falha ao registrar a emissão do token.") from exc
    response.headers["Cache-Control"] = "no-store"
    return ChannelTokenOut(
        id=minted.info.id,
        token=minted.secret,
        prefix=minted.info.prefix,
        expires_at=expires_at,
        scopes=list(_SCOPES),
    )


@router.delete("/{agent_key}/channel-token/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_channel_token(
    agent_key: str,
    token_id: UUID,
    ctx: AuthContext = Depends(require_admin),
    studio_store=Depends(get_studio_definition_store_dep),
    token_admin: ProductTokenAdmin = Depends(get_product_token_admin_dep),
    audit: TokenAudit = Depends(get_token_audit_dep),
) -> Response:
    """Revoke one channel token of THIS org (the org filter is the boundary:
    another org's token id revokes nothing → 404). Audit-logged."""
    _channel_agent(studio_store, ctx, agent_key)
    try:
        revoked = token_admin.revoke(_TOKEN_SCHEMA, token_id, org_id=ctx.org_id)
    except Exception as exc:
        logger.error("agents.channel_token.revoke_failed org_id=%s error=%s", ctx.org_id, type(exc).__name__)
        raise _err(502, "revoke_failed", "Falha ao revogar o token.") from exc
    if not revoked:
        raise _err(404, "token_not_found", "Token não encontrado.")
    audit.record(
        api_token_id=token_id, org_id=ctx.org_id, action="REVOKE",
        agent_key=agent_key, actor_user_id=ctx.user_id, status=204,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
