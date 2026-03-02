"""Recurring transactions & bills router."""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response, ok_response
from app.schemas.relatorios import RecorrenteCreate, RecorrenteUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recorrentes", tags=["Recorrentes"])


@router.get("")
async def listar_recorrentes(
    ativo: Optional[bool] = Query(None),
    authorization: Optional[str] = Header(None),
):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    query = db.table("recorrentes").select("*, conta:contas(id,nome), categoria:categorias(id,nome,icone,cor)").eq("org_id", org_id).order("proxima_data")
    if ativo is not None:
        query = query.eq("ativo", ativo)
    result = query.execute()
    return success_response(result.data or [], total=len(result.data or []))


@router.get("/proximas")
async def proximas_contas(
    dias: int = Query(7, ge=1, le=90),
    authorization: Optional[str] = Header(None),
):
    """Get upcoming bills within the next N days."""
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    from datetime import date, timedelta
    hoje = date.today().isoformat()
    limite = (date.today() + timedelta(days=dias)).isoformat()
    result = db.table("recorrentes").select("*, conta:contas(id,nome), categoria:categorias(id,nome,icone,cor)").eq("org_id", org_id).eq("ativo", True).gte("proxima_data", hoje).lte("proxima_data", limite).order("proxima_data").execute()
    return success_response(result.data or [])


@router.get("/{recorrente_id}")
async def obter_recorrente(recorrente_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    result = db.table("recorrentes").select("*, conta:contas(id,nome), categoria:categorias(id,nome,icone,cor)").eq("id", recorrente_id).eq("org_id", org_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Recorrente nao encontrado")
    return success_response(result.data)


@router.post("")
async def criar_recorrente(body: RecorrenteCreate, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    data = body.model_dump(exclude_none=True)
    data["org_id"] = org_id
    result = db.table("recorrentes").insert(data).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar recorrente")
    return success_response(result.data)


@router.patch("/{recorrente_id}")
async def atualizar_recorrente(recorrente_id: str, body: RecorrenteUpdate, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    result = db.table("recorrentes").update(updates).eq("id", recorrente_id).eq("org_id", org_id).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Recorrente nao encontrado")
    return success_response(result.data)


@router.delete("/{recorrente_id}")
async def excluir_recorrente(recorrente_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    result = db.table("recorrentes").delete().eq("id", recorrente_id).eq("org_id", org_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Recorrente nao encontrado")
    return ok_response("Recorrente excluido com sucesso")
