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
) -> Response:
    """Idempotent: 204 whether or not a token was stored."""
    removed = delete_api_key(store, str(ctx.org_id), JULIA_TOOLS_TOKEN_KEY)
    logger.info("agents.julia_tools_token.deleted org_id=%s existed=%s", ctx.org_id, removed)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
