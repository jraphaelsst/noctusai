"""
Regras Pontuação Router — CRUD + resolution for point scoring.

Scoring rules define how many points an event is worth, per (evento_tipo,
modalidade). The `/resolve` endpoint is the canonical lookup used by
the Phase 5 event triggers and by any agent wanting to preview their
score-contribution for a given event.

Admin-only writes enforced via RLS.
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
from app.services import regras_pontuacao_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metas/regras-pontuacao", tags=["Metas — Regras"])

EventoLiteral = Literal["captacao", "visita", "venda", "locacao", "reuniao"]
ModalidadeLiteral = Literal["padrao", "compartilhada", "exclusividade"]


# ── Schemas ──────────────────────────────────────────────────────────

class RegraUpsert(BaseModel):
    evento_tipo: EventoLiteral
    modalidade: ModalidadeLiteral = "padrao"
    pontos: float
    vigencia_periodo_id: Optional[str] = None
    descricao: Optional[str] = None
    org_scope: bool = True   # True → tenant rule (org_id = caller's); False → platform default (admin only)


class RegraUpdate(BaseModel):
    pontos: Optional[float] = None
    descricao: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("")
async def listar(
    evento_tipo: Optional[EventoLiteral] = None,
    periodo_id: Optional[str] = None,
    incluir_defaults: bool = True,
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    regras = svc.listar_regras(
        db,
        org_id=get_org_id(user),
        periodo_id=periodo_id,
        evento_tipo=evento_tipo,
        incluir_defaults=incluir_defaults,
    )
    return success_response(regras)


@router.get("/resolve")
async def resolve(
    evento_tipo: EventoLiteral = Query(...),
    modalidade: ModalidadeLiteral = Query("padrao"),
    periodo_id: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """Return the winning rule for the tuple — the same resolution triggers use."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    rule = svc.resolve_rule(
        db,
        org_id=get_org_id(user),
        periodo_id=periodo_id,
        evento_tipo=evento_tipo,
        modalidade=modalidade,
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Nenhuma regra encontrada para o par informado")
    return success_response(rule)


@router.post("", status_code=201)
async def upsert(body: RegraUpsert, authorization: Optional[str] = Header(None)):
    """Upsert a point rule. Omit `vigencia_periodo_id` for an org default."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    org_id = get_org_id(user, required=True) if body.org_scope else None
    try:
        regra = svc.upsert_regra(
            db,
            org_id=org_id,
            evento_tipo=body.evento_tipo,
            modalidade=body.modalidade,
            pontos=body.pontos,
            vigencia_periodo_id=body.vigencia_periodo_id,
            descricao=body.descricao,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Falha ao salvar regra")
        raise HTTPException(status_code=403, detail=str(e))
    log_action(user.id, "editar", "regra_pontuacao", regra["id"], body.model_dump())
    return success_response(regra)


@router.patch("/{regra_id}")
async def atualizar(
    regra_id: str,
    body: RegraUpdate,
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        regra = svc.atualizar_regra(db, regra_id, body.model_dump(exclude_none=True))
    except LookupError:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log_action(user.id, "editar", "regra_pontuacao", regra_id, body.model_dump(exclude_none=True))
    return success_response(regra)


@router.delete("/{regra_id}")
async def deletar(regra_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        svc.deletar_regra(db, regra_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    log_action(user.id, "desativar", "regra_pontuacao", regra_id, {})
    return success_response({"id": regra_id, "deleted": True})
