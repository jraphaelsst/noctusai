"""Financial goals router."""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response, ok_response
from app.schemas.metas import MetaCreate, MetaUpdate, ContribuicaoCreate
from app.services.metas_service import MetasService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metas", tags=["Metas"])


@router.get("")
async def listar_metas(
    status: Optional[str] = Query(None),
    auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = MetasService(db, org_id)
    data = await service.listar(status=status)
    return success_response(data, total=len(data))


@router.get("/{meta_id}")
async def obter_meta(meta_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = MetasService(db, org_id)
    data = await service.obter(meta_id)
    if not data:
        raise HTTPException(status_code=404, detail="Meta nao encontrada")
    return success_response(data)


@router.get("/{meta_id}/progresso")
async def obter_progresso(meta_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = MetasService(db, org_id)
    data = await service.obter_progresso(meta_id)
    if not data:
        raise HTTPException(status_code=404, detail="Meta nao encontrada")
    return success_response(data)


@router.post("")
async def criar_meta(body: MetaCreate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = MetasService(db, org_id)
    data = await service.criar(body.model_dump(exclude_none=True))
    if not data:
        raise HTTPException(status_code=500, detail="Erro ao criar meta")
    return success_response(data)


@router.patch("/{meta_id}")
async def atualizar_meta(meta_id: str, body: MetaUpdate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = MetasService(db, org_id)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    data = await service.atualizar(meta_id, updates)
    if not data:
        raise HTTPException(status_code=404, detail="Meta nao encontrada")
    return success_response(data)


@router.delete("/{meta_id}")
async def excluir_meta(meta_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = MetasService(db, org_id)
    await service.excluir(meta_id)
    return ok_response("Meta excluida com sucesso")


@router.post("/{meta_id}/contribuicao")
async def adicionar_contribuicao(meta_id: str, body: ContribuicaoCreate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = MetasService(db, org_id)
    data = await service.adicionar_contribuicao(meta_id, body.model_dump(exclude_none=True))
    if not data:
        raise HTTPException(status_code=500, detail="Erro ao adicionar contribuicao")
    return success_response(data)
