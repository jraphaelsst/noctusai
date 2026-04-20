"""
Meta Fechamentos Router — period close + history retrieval.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.dependencies import get_current_user, get_user_client, log_action
from app.responses import success_response
from app.services import meta_fechamentos_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metas/fechamentos", tags=["Metas — Fechamentos"])


class CloseBody(BaseModel):
    periodo_id: str


@router.get("")
async def listar(
    periodo_id: Optional[str] = None,
    corretor_id: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    _, token = await get_current_user(authorization)
    db = get_user_client(token)
    return success_response(svc.listar_fechamentos(db, periodo_id=periodo_id, corretor_id=corretor_id))


@router.post("/fechar", status_code=201)
async def fechar_periodo(body: CloseBody, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        result = svc.close_periodo(db, periodo_id=body.periodo_id, fechado_por=user.id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Período não encontrado")
    except Exception as e:
        logger.exception("Falha ao fechar período")
        raise HTTPException(status_code=403, detail=str(e))
    log_action(user.id, "criar", "meta_fechamento", body.periodo_id, {"reused": result.get("reused")})
    return success_response(result)


@router.get("/trimestre/{trimestre_id}")
async def aggregate_trimestre(trimestre_id: str, authorization: Optional[str] = Header(None)):
    _, token = await get_current_user(authorization)
    db = get_user_client(token)
    return success_response(svc.aggregate_trimestre(db, trimestre_id=trimestre_id))
