"""Esteira -- the card's origin (estruturas-contract.md section 6.8, tier ``org``).

``GET /esteira/posts/{post_id}/origem``: headline, roteiro, Estruturas, formato, caption origin and the source
conversation of a card. A foreign / unknown post is a 404. Its own router so ``esteira_service`` / ``routers/esteira``
stay untouched by the read side.

NOTE: no ``from __future__ import annotations`` -- keeps FastAPI resolving annotations in this module's globals.
"""
import uuid

from fastapi import Depends, HTTPException

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.services.esteira_origem_service import EsteiraOrigemService
from app.modules.media_creation.services.headlines_roteiros_service import HeadlinesRoteirosError

router = make_router(
    tier="org", guard=get_current_user_org, prefix="/api/media-creation/esteira/posts",
    tags=["Media Creation — Esteira"],
)


@router.get("/{post_id}/origem")
async def origem_do_card(post_id: uuid.UUID, auth=Depends(get_current_user_org)):
    user_id = str(getattr(auth[0], "id", "") or "")
    svc = EsteiraOrigemService(get_admin_client(), org_id=str(auth[2]), user_id=user_id)
    try:
        data = await run_blocking(svc.origem, str(post_id))
    except HeadlinesRoteirosError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc  # detail-safe: HeadlinesRoteirosError.detail is a fixed pt-BR 404 message authored in our service, never exception text
    return success_response(data)
