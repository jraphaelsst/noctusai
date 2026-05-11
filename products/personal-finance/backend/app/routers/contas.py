"""Accounts CRUD router."""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response, paginated_response, ok_response
from app.schemas.contas import ContaCreate, ContaUpdate
from app.services.contas_service import ContasService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/contas", tags=["Contas"])


@router.get("")
async def listar_contas(
    ativo: Optional[bool] = Query(None),
    auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = ContasService(db, org_id)
    data = await service.listar(ativo=ativo)
    return success_response(data, total=len(data))


@router.get("/saldos")
async def obter_saldos(auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = ContasService(db, org_id)
    data = await service.obter_saldos()
    return success_response(data)


@router.get("/{conta_id}")
async def obter_conta(conta_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = ContasService(db, org_id)
    data = await service.obter(conta_id)
    if not data:
        raise HTTPException(status_code=404, detail="Conta nao encontrada")
    return success_response(data)


@router.post("")
async def criar_conta(body: ContaCreate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = ContasService(db, org_id)
    data = await service.criar(body.model_dump(exclude_none=True))
    if not data:
        raise HTTPException(status_code=500, detail="Erro ao criar conta")
    return success_response(data)


@router.patch("/{conta_id}")
async def atualizar_conta(conta_id: str, body: ContaUpdate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = ContasService(db, org_id)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    data = await service.atualizar(conta_id, updates)
    if not data:
        raise HTTPException(status_code=404, detail="Conta nao encontrada")
    return success_response(data)


@router.delete("/{conta_id}")
async def excluir_conta(conta_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = ContasService(db, org_id)
    await service.excluir(conta_id)
    return ok_response("Conta excluida com sucesso")
