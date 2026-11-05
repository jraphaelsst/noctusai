"""``DELETE /api/channels/ferramentas-token`` -- drop the org's stored Lais tools token.

The tools token (scope ``social-wiring:lais-tools``) is no longer HANDED OVER here: since the Julia-line project
(CONTRACT D2/D5) agents mints it and keeps its secret itself as part of a platform grant
(``app.grants`` / ``/api/studio/plataforma/grants``), so the former ``PUT`` paste intake is gone (404). Only the
idempotent ``DELETE`` stays, for a product that wants to clear its stored token. Auth is the org's channel token (same
gate as ``/turns``: product token, scope ``agents:channel-turn``, issuer ``social-wiring``) -- ``org_id`` comes ONLY
from the token.

Storage (written by the grant service): the per-org encrypted store (``noctusai_lib.security.api_keys`` over
``agents.credentials``, Fernet) under ``social_wiring_lais_tools_token``, read back by
:func:`app.clients.social_wiring.resolve_julia_tools_token` -- this org's rows only. Never returned, never logged.
"""
# NOTE: deliberately NO `from __future__ import annotations` (FastAPI body types).

import logging
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from noctusai_lib.security.api_keys import EncryptionNotConfigured, delete_api_key

from app.clients.social_wiring import JULIA_TOOLS_TOKEN_KEY
from app.credentials.org_keys import build_llm_key_store
from app.dependencies import require_channel_turn
from app.routers.channels_router import _ChannelRoute, _err
from app.routers.studio_agents_router import get_studio_definition_store_dep
from app.stores.errors import NotFound
from noctusai_lib.api.auth.session import AuthContext

logger = logging.getLogger(__name__)

__all__ = ["router", "get_julia_tools_token_store_dep"]

router = APIRouter(prefix="/api/channels", tags=["channels"], route_class=_ChannelRoute)


def get_julia_tools_token_store_dep() -> Any:
    """The encrypted per-org store. A missing/invalid ``ENCRYPTION_KEY`` is a
    503 (the value is never stored in the clear)."""
    try:
        return build_llm_key_store()
    except EncryptionNotConfigured as exc:
        logger.error("agents.julia_tools_token.encryption_not_configured: %s", exc)
        raise _err(503, "encryption_not_configured", "Armazenamento seguro indisponível.") from exc


@router.delete("/ferramentas-token", status_code=status.HTTP_204_NO_CONTENT)
def delete_tools_token(
    ctx: AuthContext = Depends(require_channel_turn),
    store: Any = Depends(get_julia_tools_token_store_dep),
    studio_store: Any = Depends(get_studio_definition_store_dep),
) -> Response:
    """Idempotent: 204 whether or not a token was stored. The stored secret is JULIA's: only the token of the agent that
    secret belongs to (the grant registry's agent for this issuer) may clear it -- another agent's personal token is
    403 ``agent_not_allowed``."""
    from app.grants.registry import GRANT_PRODUCTS

    try:
        agent = studio_store.get_agent_by_id(ctx.principal_agent_id)
    except NotFound as exc:  # the token names no agent we can verify
        logger.warning("agents.julia_tools_token.delete_refused org_id=%s cause=%s", ctx.org_id, type(exc).__name__)
        raise _err(403, "agent_not_allowed", "O token não pertence a este agente.") from exc
    spec = next((p for p in GRANT_PRODUCTS.values() if p.channel_issuer == ctx.issuer), None)
    if (
        spec is None or agent.org_id != ctx.org_id or agent.key not in spec.agent_keys
        or spec.tools_secret_name != JULIA_TOOLS_TOKEN_KEY
    ):
        raise _err(403, "agent_not_allowed", "O token não pertence a este agente.")
    removed = delete_api_key(store, str(ctx.org_id), JULIA_TOOLS_TOKEN_KEY)
    logger.info("agents.julia_tools_token.deleted org_id=%s existed=%s", ctx.org_id, removed)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
