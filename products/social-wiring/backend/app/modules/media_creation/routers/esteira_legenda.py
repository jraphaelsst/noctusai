"""Esteira — AI caption for a post (esteira-contract.md section 5.3).

``POST /api/media-creation/esteira/posts/{post_id}/legenda/gerar`` returns
``{legenda, hashtags[], primeiro_comentario}`` WITHOUT saving it; the user edits and PATCHes the post.
Auth ``get_current_user_org`` (org-scoped: a foreign post is a 404), ``DEFAULT_AI_RL``.
"""
# NOTE: no `from __future__ import annotations` here -- slowapi's @limiter.limit wrapper
# makes FastAPI resolve string annotations in slowapi's globals.
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.routers.roteiros import get_roteiro_settings
from app.modules.media_creation.services.legenda_service import (
    IaCheck,
    LegendaError,
    LegendaLlm,
    LegendaService,
    get_legenda_ia_check,
    get_legenda_llm,
)
from app.rate_limit import limiter

router = APIRouter(prefix="/api/media-creation/esteira/posts", tags=["Media Creation — Esteira"])


@router.post("/{post_id}/legenda/gerar")
@limiter.limit(DEFAULT_AI_RL)
async def gerar_legenda(
    request: Request,
    post_id: uuid.UUID,
    auth=Depends(get_current_user_org),
    cfg=Depends(get_roteiro_settings),
    llm: LegendaLlm = Depends(get_legenda_llm),
    ia_check: IaCheck = Depends(get_legenda_ia_check),
):
    user, _, org_id = auth
    svc = LegendaService(get_admin_client(), org_id, str(user.id), cfg=cfg, llm=llm, ia_check=ia_check)
    try:
        resultado = await svc.gerar(str(post_id))
        return success_response(resultado)
    except LegendaError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail, headers=exc.headers) from exc
