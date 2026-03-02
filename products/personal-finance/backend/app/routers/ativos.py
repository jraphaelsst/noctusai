"""Holdings (stocks, ETFs, etc.) router."""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response, ok_response
from app.schemas.ativos import AtivoCreate, AtivoUpdate
from app.services.ativos_service import AtivosService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ativos", tags=["Ativos"])


@router.get("")
async def listar_ativos(
    carteira_id: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = AtivosService(db, org_id)
    data = await service.listar(carteira_id=carteira_id)
    return success_response(data, total=len(data))


@router.get("/por-carteira/{carteira_id}")
async def ativos_por_carteira(carteira_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = AtivosService(db, org_id)
    data = await service.listar(carteira_id=carteira_id)
    return success_response(data, total=len(data))


@router.get("/{ativo_id}")
async def obter_ativo(ativo_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = AtivosService(db, org_id)
    data = await service.obter(ativo_id)
    if not data:
        raise HTTPException(status_code=404, detail="Ativo nao encontrado")
    return success_response(data)


@router.post("")
async def criar_ativo(body: AtivoCreate, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = AtivosService(db, org_id)
    data = await service.criar(body.model_dump(exclude_none=True))
    if not data:
        raise HTTPException(status_code=500, detail="Erro ao criar ativo")
    return success_response(data)


@router.patch("/{ativo_id}")
async def atualizar_ativo(ativo_id: str, body: AtivoUpdate, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = AtivosService(db, org_id)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    data = await service.atualizar(ativo_id, updates)
    if not data:
        raise HTTPException(status_code=404, detail="Ativo nao encontrado")
    return success_response(data)


@router.delete("/{ativo_id}")
async def excluir_ativo(ativo_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = AtivosService(db, org_id)
    await service.excluir(ativo_id)
    return ok_response("Ativo excluido com sucesso")
