"""
Metas Equipe Router — team-level VGV quota allocation.

POST upserts a (periodo, equipe, categoria) meta with cascade validation
(team allocations can't exceed the company meta). GET /resumo exposes the
allocation state per team so the leader UI can show saldo/estouro.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_user_client, log_action
from app.responses import success_response
from app.services import metas_equipe_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metas/equipes-quotas", tags=["Metas — Quotas Equipe"])


class MetaEquipeUpsert(BaseModel):
    periodo_id: str
    equipe_id: str
    valor_meta: float = Field(..., ge=0)
    categoria: str = "vgv"
    enforce_cascade: bool = True


@router.get("")
async def listar(
    periodo_id: Optional[str] = None,
    equipe_id: Optional[str] = None,
    categoria: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    _, token = await get_current_user(authorization)
    db = get_user_client(token)
    return success_response(svc.listar_metas_equipe(db, periodo_id=periodo_id, equipe_id=equipe_id, categoria=categoria))


@router.post("", status_code=201)
async def upsert(body: MetaEquipeUpsert, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        meta = svc.upsert_meta_equipe(
            db,
            periodo_id=body.periodo_id,
            equipe_id=body.equipe_id,
            valor_meta=body.valor_meta,
            categoria=body.categoria,
            definida_por=user.id,
            enforce_cascade=body.enforce_cascade,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Falha ao salvar meta de equipe")
        raise HTTPException(status_code=403, detail=str(e))
    log_action(user.id, "editar", "meta_equipe", meta["id"], body.model_dump())
    return success_response(meta)


@router.get("/resumo")
async def resumo(
    equipe_id: str = Query(...),
    periodo_id: str = Query(...),
    categoria: str = Query("vgv"),
    authorization: Optional[str] = Header(None),
):
    _, token = await get_current_user(authorization)
    db = get_user_client(token)
    return success_response(svc.resumo_cascata_equipe(
        db, equipe_id=equipe_id, periodo_id=periodo_id, categoria=categoria
    ))


@router.delete("/{meta_id}")
async def deletar(meta_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        svc.deletar_meta_equipe(db, meta_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Meta de equipe não encontrada")
    log_action(user.id, "desativar", "meta_equipe", meta_id, {})
    return success_response({"id": meta_id, "deleted": True})
