"""Budget management router."""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response, ok_response
from app.schemas.orcamentos import OrcamentoCreate, OrcamentoUpdate, OrcamentoItemCreate, OrcamentoItemUpdate
from app.services.orcamentos_service import OrcamentosService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/orcamentos", tags=["Orcamentos"])


@router.get("")
async def listar_orcamentos(authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = OrcamentosService(db, org_id)
    data = await service.listar()
    return success_response(data, total=len(data))


@router.get("/{orcamento_id}")
async def obter_orcamento(orcamento_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = OrcamentosService(db, org_id)
    data = await service.obter(orcamento_id)
    if not data:
        raise HTTPException(status_code=404, detail="Orcamento nao encontrado")
    return success_response(data)


@router.get("/{orcamento_id}/progresso")
async def obter_progresso(
    orcamento_id: str,
    periodo_mes: str = Query(...),
    authorization: Optional[str] = Header(None),
):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = OrcamentosService(db, org_id)
    data = await service.obter_progresso(orcamento_id, periodo_mes)
    return success_response(data)


@router.get("/{orcamento_id}/itens")
async def listar_itens(
    orcamento_id: str,
    periodo_mes: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = OrcamentosService(db, org_id)
    data = await service.listar_itens(orcamento_id, periodo_mes)
    return success_response(data, total=len(data))


@router.post("")
async def criar_orcamento(body: OrcamentoCreate, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = OrcamentosService(db, org_id)
    itens = [i.model_dump() for i in body.itens] if body.itens else None
    data_dict = body.model_dump(exclude_none=True)
    data_dict.pop("itens", None)
    data = await service.criar(data_dict, itens)
    if not data:
        raise HTTPException(status_code=500, detail="Erro ao criar orcamento")
    return success_response(data)


@router.patch("/{orcamento_id}")
async def atualizar_orcamento(orcamento_id: str, body: OrcamentoUpdate, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = OrcamentosService(db, org_id)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    data = await service.atualizar(orcamento_id, updates)
    if not data:
        raise HTTPException(status_code=404, detail="Orcamento nao encontrado")
    return success_response(data)


@router.delete("/{orcamento_id}")
async def excluir_orcamento(orcamento_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = OrcamentosService(db, org_id)
    await service.excluir(orcamento_id)
    return ok_response("Orcamento excluido com sucesso")


@router.post("/{orcamento_id}/itens")
async def criar_item(orcamento_id: str, body: OrcamentoItemCreate, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = OrcamentosService(db, org_id)
    item_data = body.model_dump()
    item_data["orcamento_id"] = orcamento_id
    data = await service.criar_item(item_data)
    return success_response(data)


@router.patch("/itens/{item_id}")
async def atualizar_item(item_id: str, body: OrcamentoItemUpdate, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = OrcamentosService(db, org_id)
    updates = body.model_dump(exclude_none=True)
    data = await service.atualizar_item(item_id, updates)
    if not data:
        raise HTTPException(status_code=404, detail="Item nao encontrado")
    return success_response(data)


@router.delete("/itens/{item_id}")
async def excluir_item(item_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = OrcamentosService(db, org_id)
    await service.excluir_item(item_id)
    return ok_response("Item excluido com sucesso")
