"""Recurring transactions & bills router."""
import logging
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from noctusai_lib.api.crud_safety import delete_or_404
from app.dependencies import get_current_user_org, get_user_client, first_or_none
from app.responses import success_response, ok_response
from app.schemas.recorrentes import RecorrenteCreate, RecorrenteUpdate
from app.services.recorrentes_service import RecorrentesService

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


@router.post("/executar")
async def executar_pendentes(authorization: Optional[str] = Header(None)):
    """Execute all pending automatic recurring transactions."""
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = RecorrentesService(db, org_id)
    data = await service.executar_pendentes()
    return success_response(data)


@router.get("/proximas")
async def proximas_contas(
    dias: int = Query(7, ge=1, le=90),
    authorization: Optional[str] = Header(None),
):
    """Get upcoming bills within the next N days."""
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    hoje = date.today().isoformat()
    limite = (date.today() + timedelta(days=dias)).isoformat()
    result = db.table("recorrentes").select("*, conta:contas(id,nome), categoria:categorias(id,nome,icone,cor)").eq("org_id", org_id).eq("ativo", True).gte("proxima_data", hoje).lte("proxima_data", limite).order("proxima_data").execute()
    return success_response(result.data or [])


@router.post("/{recorrente_id}/executar")
async def executar_unico(recorrente_id: str, authorization: Optional[str] = Header(None)):
    """Manually execute a single recurring entry once."""
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = RecorrentesService(db, org_id)
    data = await service.executar_unico(recorrente_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Recorrente nao encontrado")
    return success_response(data)


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
    result = db.table("recorrentes").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar recorrente")
    return success_response(row)


@router.patch("/{recorrente_id}")
async def atualizar_recorrente(recorrente_id: str, body: RecorrenteUpdate, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    result = db.table("recorrentes").update(updates).eq("id", recorrente_id).eq("org_id", org_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Recorrente nao encontrado")
    return success_response(row)


@router.delete("/{recorrente_id}")
async def excluir_recorrente(recorrente_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    delete_or_404(
        db,
        "recorrentes",
        ("id", recorrente_id),
        ("org_id", org_id),
        message="Recorrente nao encontrado",
    )
    return ok_response("Recorrente excluido com sucesso")
