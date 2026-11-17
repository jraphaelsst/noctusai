"""Headlines e Roteiros (estruturas-contract.md section 6.9, tier ``org``).

``GET /headlines-roteiros`` -- the marca's saved headlines plus their roteiros (and roteiros without a headline),
with the Estruturas that served each. Read-only; a foreign / unknown ``marca_id`` is a 404.

NOTE: no ``from __future__ import annotations`` -- keeps FastAPI resolving annotations in this module's globals.
"""
import uuid
from typing import Literal, Optional

from fastapi import Depends, HTTPException, Query

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.services.headlines_roteiros_service import HeadlinesRoteirosError, HeadlinesRoteirosService

router = make_router(
    tier="org", guard=get_current_user_org, prefix="/api/media-creation/headlines-roteiros",
    tags=["Media Creation — Headlines e Roteiros"],
)


@router.get("")
async def listar_headlines_roteiros(
    marca_id: uuid.UUID,
    q: Optional[str] = Query(default=None, max_length=200),
    estrutura_id: Optional[uuid.UUID] = None,
    perfil_id: Optional[uuid.UUID] = None,
    roteiro_status: Optional[Literal["criando", "processando", "completo", "falha", "sem_roteiro"]] = None,
    aprovacao: Optional[Literal["pendente", "aprovado", "rejeitado"]] = None,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100_000),
    auth=Depends(get_current_user_org),
):
    user_id = str(getattr(auth[0], "id", "") or "")
    svc = HeadlinesRoteirosService(get_admin_client(), org_id=str(auth[2]), user_id=user_id)
    try:
        data = await run_blocking(
            svc.listar, str(marca_id), q=q, estrutura_id=str(estrutura_id) if estrutura_id else None,
            perfil_id=str(perfil_id) if perfil_id else None, roteiro_status=roteiro_status, aprovacao=aprovacao,
            limit=limit, offset=offset,
        )
    except HeadlinesRoteirosError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc  # detail-safe: HeadlinesRoteirosError.detail is a fixed pt-BR 404 message authored in our service, never exception text
    return success_response(data)
