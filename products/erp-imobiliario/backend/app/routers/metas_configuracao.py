"""
Metas Configuração Router — per-org scoring settings.

GET returns the effective config (persisted row or virtual default).
POST/PUT upserts — one row per org.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import Field

from app.dependencies import (
    get_current_user,
    get_org_id,
    get_user_client,
    log_action,
)
from app.responses import success_response
from app.services import metas_configuracao_service as svc
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metas/configuracao", tags=["Metas — Configuração"])


class ConfigUpsert(StrictHttpModel):
    vgv_por_ponto: Optional[float] = Field(default=None, gt=0)
    peso_pontos: Optional[float] = Field(default=None, ge=0)
    peso_vgv: Optional[float] = Field(default=None, ge=0)
    metrica_ranking_padrao: Optional[Literal["pontos", "vgv", "unificado"]] = None


@router.get("")
async def obter(auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)
    org_id = get_org_id(user, required=True)
    return success_response(svc.obter_configuracao(db, org_id))


@router.put("")
async def upsert(body: ConfigUpsert, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)
    org_id = get_org_id(user, required=True)
    try:
        row = svc.upsert_configuracao(
            db,
            org_id=org_id,
            vgv_por_ponto=body.vgv_por_ponto,
            peso_pontos=body.peso_pontos,
            peso_vgv=body.peso_vgv,
            metrica_ranking_padrao=body.metrica_ranking_padrao,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Falha ao salvar configuração de metas")
        raise HTTPException(status_code=403, detail=str(e))
    log_action(user.id, "editar", "metas_configuracao", org_id, body.model_dump(exclude_none=True))
    return success_response(row)
