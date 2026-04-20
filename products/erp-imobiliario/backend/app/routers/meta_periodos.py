"""
Meta Períodos Router — CRUD + auto-generation for evaluation periods.

Periods form a parent-child tree: quinzenal → mensal → trimestral → anual.
Owner creates them one at a time, or uses the `/auto-generate` endpoint
to scaffold a whole trimestre in one shot (trimestral + 3 mensal + 6 quinzenal).

Admin-only writes enforced at the DB layer via RLS.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import (
    get_current_user,
    get_org_id,
    get_user_client,
    log_action,
)
from app.responses import success_response
from app.services import meta_periodos_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metas/periodos", tags=["Metas — Períodos"])

TipoLiteral = Literal["diaria", "semanal", "quinzenal", "mensal", "trimestral", "anual"]


# ── Schemas ──────────────────────────────────────────────────────────

class PeriodoCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=100)
    tipo: TipoLiteral
    data_inicio: str  # ISO date
    data_fim: str
    parent_periodo_id: Optional[str] = None


class PeriodoUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=100)
    tipo: Optional[TipoLiteral] = None
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    status: Optional[Literal["aberto", "em_avaliacao", "fechado"]] = None
    parent_periodo_id: Optional[str] = None


class AutoGenerateBody(BaseModel):
    year: int = Field(..., ge=2020, le=2100)
    quarter: int = Field(..., ge=1, le=4)


class PreviewBody(BaseModel):
    year: int = Field(..., ge=2020, le=2100)
    quarter: int = Field(..., ge=1, le=4)


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("")
async def listar(
    tipo: Optional[TipoLiteral] = None,
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    org_id = get_org_id(user)
    periodos = svc.listar_periodos(db, org_id=org_id, tipo=tipo)
    return success_response(periodos)


@router.post("", status_code=201)
async def criar(body: PeriodoCreate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    org_id = get_org_id(user, required=True)
    db = get_user_client(token)
    try:
        periodo = svc.criar_periodo(
            db,
            org_id=org_id,
            nome=body.nome,
            tipo=body.tipo,
            data_inicio=body.data_inicio,
            data_fim=body.data_fim,
            parent_periodo_id=body.parent_periodo_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Falha ao criar período")
        raise HTTPException(status_code=403, detail=str(e))
    log_action(user.id, "criar", "meta_periodo", periodo["id"], body.model_dump())
    return success_response(periodo)


@router.post("/preview")
async def preview_trimestre(body: PreviewBody, authorization: Optional[str] = Header(None)):
    """Return the structure that auto-generate would create — no DB writes."""
    await get_current_user(authorization)
    try:
        plan = svc.plan_trimestre_structure(body.year, body.quarter)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return success_response(plan)


@router.post("/auto-generate", status_code=201)
async def auto_generate(body: AutoGenerateBody, authorization: Optional[str] = Header(None)):
    """Create (or reuse) the trimestral + 3 mensal + 6 quinzenal chain for a quarter."""
    user, token = await get_current_user(authorization)
    org_id = get_org_id(user, required=True)
    db = get_user_client(token)
    try:
        chain = svc.gerar_trimestre(db, org_id=org_id, year=body.year, quarter=body.quarter)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Falha ao auto-gerar trimestre")
        raise HTTPException(status_code=403, detail=str(e))
    log_action(
        user.id, "criar", "meta_periodo_trimestre",
        chain["trimestre"]["id"],
        {"year": body.year, "quarter": body.quarter},
    )
    return success_response(chain)


@router.get("/{periodo_id}")
async def obter(periodo_id: str, authorization: Optional[str] = Header(None)):
    _, token = await get_current_user(authorization)
    db = get_user_client(token)
    periodo = svc.obter_periodo(db, periodo_id)
    if not periodo:
        raise HTTPException(status_code=404, detail="Período não encontrado")
    return success_response(periodo)


@router.patch("/{periodo_id}")
async def atualizar(
    periodo_id: str,
    body: PeriodoUpdate,
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        periodo = svc.atualizar_periodo(db, periodo_id, body.model_dump(exclude_none=True))
    except LookupError:
        raise HTTPException(status_code=404, detail="Período não encontrado")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log_action(user.id, "editar", "meta_periodo", periodo_id, body.model_dump(exclude_none=True))
    return success_response(periodo)


@router.delete("/{periodo_id}")
async def deletar(periodo_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        svc.deletar_periodo(db, periodo_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Período não encontrado")
    log_action(user.id, "desativar", "meta_periodo", periodo_id, {})
    return success_response({"id": periodo_id, "deleted": True})
