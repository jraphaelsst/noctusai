"""Recurring transactions & bills router."""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response, ok_response
from app.schemas.recorrentes import RecorrenteCreate, RecorrenteUpdate
from app.services.recorrentes_service import RecorrentesService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recorrentes", tags=["Recorrentes"])


@router.get("")
async def listar_recorrentes(
    ativo: Optional[bool] = Query(None),
    auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = RecorrentesService(db, org_id)
    data = await service.listar(ativo=ativo)
    return success_response(data, total=len(data))


@router.post("/executar")
async def executar_pendentes(auth: tuple = Depends(get_current_user_org)):
    """Execute all pending automatic recurring transactions."""
    user, token, org_id = auth
    db = get_user_client(token)
    service = RecorrentesService(db, org_id)
    data = await service.executar_pendentes()
    return success_response(data)


@router.get("/proximas")
async def proximas_contas(
    dias: int = Query(7, ge=1, le=90),
    auth: tuple = Depends(get_current_user_org)):
    """Get upcoming bills within the next N days."""
    user, token, org_id = auth
    db = get_user_client(token)
    service = RecorrentesService(db, org_id)
    data = await service.proximas(dias)
    return success_response(data)


@router.post("/{recorrente_id}/executar")
async def executar_unico(recorrente_id: str, auth: tuple = Depends(get_current_user_org)):
    """Manually execute a single recurring entry once."""
    user, token, org_id = auth
    db = get_user_client(token)
    service = RecorrentesService(db, org_id)
    data = await service.executar_unico(recorrente_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Recorrente nao encontrado")
    return success_response(data)


@router.get("/{recorrente_id}")
async def obter_recorrente(recorrente_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = RecorrentesService(db, org_id)
    data = await service.obter(recorrente_id)
    if not data:
        raise HTTPException(status_code=404, detail="Recorrente nao encontrado")
    return success_response(data)


@router.post("")
async def criar_recorrente(body: RecorrenteCreate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = RecorrentesService(db, org_id)
    data = await service.criar(body.model_dump(exclude_none=True))
    if not data:
        raise HTTPException(status_code=500, detail="Erro ao criar recorrente")
    return success_response(data)


@router.patch("/{recorrente_id}")
async def atualizar_recorrente(recorrente_id: str, body: RecorrenteUpdate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    service = RecorrentesService(db, org_id)
    data = await service.atualizar(recorrente_id, updates)
    if not data:
        raise HTTPException(status_code=404, detail="Recorrente nao encontrado")
    return success_response(data)


@router.delete("/{recorrente_id}")
async def excluir_recorrente(recorrente_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = RecorrentesService(db, org_id)
    await service.excluir(recorrente_id)
    return ok_response("Recorrente excluido com sucesso")
