"""
Equipes Router — Teams and membership for the Metas domain.

Teams (DRAGÃO, LEÃO, ÁGUIA + future) are CRUDed by the org owner (admin
role). Leaders (coordenador + papel='lider') are read-only on the team
resource but can view their own team's members. Agents (corretor) can
read the team they belong to.

See METAS-PLAN.md §5 for the permission matrix.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import (
    get_admin_client,
    get_current_user,
    get_org_id,
    get_user_client,
    log_action,
)
from app.responses import ok_response, success_response
from app.services import equipes_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metas/equipes", tags=["Metas — Equipes"])


# ── Schemas ──────────────────────────────────────────────────────────

class EquipeCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=100)
    cor: Optional[str] = Field(default=None, max_length=20)
    icone: Optional[str] = Field(default=None, max_length=50)
    lider_id: Optional[str] = None


class EquipeUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=100)
    cor: Optional[str] = Field(default=None, max_length=20)
    icone: Optional[str] = Field(default=None, max_length=50)
    lider_id: Optional[str] = None
    ativo: Optional[bool] = None


class MembroAdd(BaseModel):
    user_id: str
    papel: Literal["lider", "corretor"] = "corretor"


class MembroUpdate(BaseModel):
    papel: Literal["lider", "corretor"]


# ── Team endpoints ───────────────────────────────────────────────────

@router.get("")
async def listar(
    ativas_apenas: bool = True,
    authorization: Optional[str] = Header(None),
):
    """List teams visible to the caller (RLS filters automatically)."""
    _, token = await get_current_user(authorization)
    db = get_user_client(token)
    equipes = equipes_service.listar_equipes(db, ativas_apenas=ativas_apenas)
    return success_response(equipes)


@router.post("", status_code=201)
async def criar(body: EquipeCreate, authorization: Optional[str] = Header(None)):
    """Create a team. RLS enforces admin-only at the DB layer."""
    user, token = await get_current_user(authorization)
    org_id = get_org_id(user, required=True)
    # Uses the caller's token so RLS enforces admin role — non-admins are rejected by policy.
    db = get_user_client(token)
    try:
        equipe = equipes_service.criar_equipe(
            db,
            org_id=org_id,
            nome=body.nome,
            cor=body.cor,
            icone=body.icone,
            lider_id=body.lider_id,
        )
    except Exception as e:
        logger.exception("Falha ao criar equipe")
        raise HTTPException(status_code=403, detail=str(e))

    log_action(user.id, "criar", "equipe", equipe["id"], {"nome": body.nome})
    return success_response(equipe)


@router.get("/{equipe_id}")
async def obter(equipe_id: str, authorization: Optional[str] = Header(None)):
    _, token = await get_current_user(authorization)
    db = get_user_client(token)
    equipe = equipes_service.obter_equipe(db, equipe_id)
    if not equipe:
        raise HTTPException(status_code=404, detail="Equipe não encontrada")
    return success_response(equipe)


@router.patch("/{equipe_id}")
async def atualizar(
    equipe_id: str,
    body: EquipeUpdate,
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        equipe = equipes_service.atualizar_equipe(db, equipe_id, body.model_dump(exclude_none=True))
    except LookupError:
        raise HTTPException(status_code=404, detail="Equipe não encontrada")
    except Exception as e:
        logger.exception("Falha ao atualizar equipe")
        raise HTTPException(status_code=403, detail=str(e))
    log_action(user.id, "editar", "equipe", equipe_id, body.model_dump(exclude_none=True))
    return success_response(equipe)


@router.delete("/{equipe_id}")
async def desativar(equipe_id: str, authorization: Optional[str] = Header(None)):
    """Soft-disband the team — preserves history of past events. RLS enforces admin-only."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        equipe = equipes_service.disband_equipe(db, equipe_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Equipe não encontrada")
    log_action(user.id, "desativar", "equipe", equipe_id, {})
    return success_response(equipe)


# ── Membership endpoints ─────────────────────────────────────────────

@router.get("/{equipe_id}/membros")
async def listar_membros(
    equipe_id: str,
    incluir_historico: bool = False,
    authorization: Optional[str] = Header(None),
):
    _, token = await get_current_user(authorization)
    db = get_user_client(token)
    membros = equipes_service.listar_membros(db, equipe_id, incluir_historico=incluir_historico)
    return success_response(membros)


@router.post("/{equipe_id}/membros", status_code=201)
async def adicionar_membro(
    equipe_id: str,
    body: MembroAdd,
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        membro = equipes_service.adicionar_membro(
            db, equipe_id=equipe_id, user_id=body.user_id, papel=body.papel
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Falha ao adicionar membro")
        raise HTTPException(status_code=403, detail=str(e))
    log_action(user.id, "criar", "equipe_membro", membro["id"], body.model_dump())
    return success_response(membro)


@router.patch("/{equipe_id}/membros/{membro_id}")
async def atualizar_membro(
    equipe_id: str,
    membro_id: str,
    body: MembroUpdate,
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        membro = equipes_service.atualizar_papel_membro(db, membro_id=membro_id, papel=body.papel)
    except LookupError:
        raise HTTPException(status_code=404, detail="Membro não encontrado")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log_action(user.id, "editar", "equipe_membro", membro_id, body.model_dump())
    return success_response(membro)


@router.delete("/{equipe_id}/membros/{membro_id}")
async def remover_membro(
    equipe_id: str,
    membro_id: str,
    authorization: Optional[str] = Header(None),
):
    """Soft-remove: sets left_at, preserving history. RLS enforces admin-only."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    try:
        membro = equipes_service.remover_membro(db, membro_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Membro não encontrado")
    log_action(user.id, "desativar", "equipe_membro", membro_id, {})
    return success_response(membro)
