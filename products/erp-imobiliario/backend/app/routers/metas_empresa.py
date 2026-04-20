"""
Metas Empresa Router — CRUD + cascade summary for company-level VGV targets.

Owner sets `metas_empresa.valor_meta` per period. This router also exposes
`/resumo` so the owner UI can show how much of the company target has
been allocated to teams and how much is unassigned.

Admin-only writes enforced at the DB layer via RLS.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import (
    get_current_user,
    get_user_client,
    log_action,
)
from app.responses import success_response
from app.services import metas_empresa_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metas/empresa", tags=["Metas — Empresa"])


# ── Schemas ──────────────────────────────────────────────────────────

class MetaEmpresaUpsert(BaseModel):
    periodo_id: str
    valor_meta: float = Field(..., ge=0)
    categoria: str = "vgv"
    observacoes: Optional[str] = None


class MetaEmpresaUpdate(BaseModel):
    valor_meta: Optional[float] = Field(default=None, ge=0)
    observacoes: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("")
async def listar(
    periodo_id: Optional[str] = None,
    categoria: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    _, token = await get_current_user(authorization)
    db = get_user_client(token)
    metas = svc.listar_metas_empresa(db, periodo_id=periodo_id, categoria=categoria)
    return success_response(metas)


@router.post("", status_code=201)
async def upsert(body: MetaEmpresaUpsert, authorization: Optional[str] = Header(None)):
    """Insert or update the company meta for (periodo, categoria). One row per pair."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        meta = svc.upsert_meta_empresa(
            db,
            periodo_id=body.periodo_id,
            valor_meta=body.valor_meta,
            categoria=body.categoria,
            definida_por=user.id,
            observacoes=body.observacoes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Falha ao salvar meta de empresa")
        raise HTTPException(status_code=403, detail=str(e))
    log_action(user.id, "editar", "meta_empresa", meta["id"], body.model_dump())
    return success_response(meta)


@router.get("/resumo")
async def resumo(
    periodo_id: str = Query(...),
    categoria: str = Query("vgv"),
    authorization: Optional[str] = Header(None),
):
    """Cascade summary: meta_empresa vs sum(metas_equipe). Drives the owner allocation UI."""
    _, token = await get_current_user(authorization)
    db = get_user_client(token)
    return success_response(svc.resumo_cascata(db, periodo_id=periodo_id, categoria=categoria))


@router.get("/{meta_id}")
async def obter(meta_id: str, authorization: Optional[str] = Header(None)):
    _, token = await get_current_user(authorization)
    db = get_user_client(token)
    meta = svc.obter_meta_empresa(db, meta_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Meta de empresa não encontrada")
    return success_response(meta)


@router.patch("/{meta_id}")
async def atualizar(
    meta_id: str,
    body: MetaEmpresaUpdate,
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        meta = svc.atualizar_meta_empresa(db, meta_id, body.model_dump(exclude_none=True))
    except LookupError:
        raise HTTPException(status_code=404, detail="Meta de empresa não encontrada")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log_action(user.id, "editar", "meta_empresa", meta_id, body.model_dump(exclude_none=True))
    return success_response(meta)


@router.delete("/{meta_id}")
async def deletar(meta_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        svc.deletar_meta_empresa(db, meta_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Meta de empresa não encontrada")
    log_action(user.id, "desativar", "meta_empresa", meta_id, {})
    return success_response({"id": meta_id, "deleted": True})
