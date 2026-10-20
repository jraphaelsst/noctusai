"""``PUT|DELETE /api/channels/ferramentas-token`` — the Lais tools-token intake
(build contract §2.1(f)).

social-wiring mints a product token for agents (scope ``social-wiring:lais-tools``)
so the Lais READ tools can call back; this is how it hands the value over without
a second paste by the owner. Auth is the org's channel token (same gate as
``/turns``: product token, scope ``agents:channel-turn``, issuer
``social-wiring``) — ``org_id`` comes ONLY from the token.

Storage: the SAME per-org encrypted writer the api-keys router uses
(``noctusai_lib.security.api_keys.put_api_key`` over ``agents.credentials``,
Fernet), under the name ``social_wiring_lais_tools_token``. It is read back by
:func:`app.clients.social_wiring.resolve_julia_tools_token` — this org's rows
only, never a process-wide fallback. The value is write-only: never returned,
never logged.
"""
# NOTE: deliberately NO `from __future__ import annotations` (FastAPI body types).

import logging
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from noctusai_lib.security.api_keys import EncryptionNotConfigured, delete_api_key, put_api_key

from app.clients.social_wiring import JULIA_TOOLS_TOKEN_KEY
from app.credentials.org_keys import build_llm_key_store
from app.dependencies import require_channel_turn
from app.routers.channels_router import _ChannelRoute, _err
from app.schemas.channels import ChannelToolsTokenRequest
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


@router.put("/ferramentas-token", status_code=status.HTTP_204_NO_CONTENT)
async def put_tools_token(
    payload: ChannelToolsTokenRequest,
    ctx: AuthContext = Depends(require_channel_turn),
    store: Any = Depends(get_julia_tools_token_store_dep),
) -> Response:
    put_api_key(store, str(ctx.org_id), JULIA_TOOLS_TOKEN_KEY, payload.token)
    logger.info("agents.julia_tools_token.stored org_id=%s", ctx.org_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/ferramentas-token", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tools_token(
    ctx: AuthContext = Depends(require_channel_turn),
    store: Any = Depends(get_julia_tools_token_store_dep),
) -> Response:
    """Idempotent: 204 whether or not a token was stored."""
    removed = delete_api_key(store, str(ctx.org_id), JULIA_TOOLS_TOKEN_KEY)
    logger.info("agents.julia_tools_token.deleted org_id=%s existed=%s", ctx.org_id, removed)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
