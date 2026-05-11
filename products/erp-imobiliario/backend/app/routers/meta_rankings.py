"""
Meta Rankings Router — live leaderboards (pontos / VGV / unificado).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Query

from app.dependencies import get_current_user, get_org_id, get_user_client
from app.responses import success_response
from app.services import meta_rankings_service as svc

router = APIRouter(prefix="/api/metas/rankings", tags=["Metas — Rankings"])


@router.get("")
async def rankings(
    equipe_id: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    auth = Depends(get_current_user)):
    """Returns {pontos: [...], vgv: [...], unificado: [...], config: {...}}.

    Filters: restrict to a team and/or a date window. Org is inferred from the caller.
    """
    user, token = auth
    db = get_user_client(token)
    return success_response(svc.compute_rankings(
        db,
        org_id=get_org_id(user),
        equipe_id=equipe_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
    ))
