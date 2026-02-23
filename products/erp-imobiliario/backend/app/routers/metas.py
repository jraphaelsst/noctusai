"""
Metas CRUD Router — Goals/targets management.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from app.dependencies import get_current_user, get_user_client, get_admin_client, log_action

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metas", tags=["Metas"])


class MetaCreate(BaseModel):
    titulo: Optional[str] = None
    categoria: str
    tipo_meta: str
    quantidade_alvo: int
    data_referencia: str  # Server handles timezone
    corretor_id: Optional[str] = None
    config_id: Optional[str] = None


class MetaUpdate(BaseModel):
    titulo: Optional[str] = None
    quantidade_realizada: Optional[int] = None
    concluida: Optional[bool] = None
    data_conclusao: Optional[str] = None


@router.get("")
async def listar_metas(
    corretor_id: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    query = db.table("metas").select("*").order("data_referencia", desc=True)

    if corretor_id:
        query = query.eq("corretor_id", corretor_id)

    result = query.execute()
    return {"data": result.data or [], "total": len(result.data or [])}


@router.get("/hoje")
async def metas_hoje(authorization: Optional[str] = Header(None)):
    """Get current São Paulo date and today's metas."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Server-side date calculation (São Paulo timezone)
    admin = get_admin_client()
    date_result = admin.rpc("get_data_sp").execute()
    data_hoje = date_result.data if date_result.data else None

    query = db.table("metas").select("*").eq("corretor_id", user.id)
    if data_hoje:
        query = query.eq("data_referencia", data_hoje)

    result = query.execute()
    return {"data": result.data or [], "data_hoje": data_hoje}


@router.post("")
async def criar_meta(body: MetaCreate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data.get("corretor_id"):
        data["corretor_id"] = user.id

    result = db.table("metas").insert(data).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar meta")

    log_action(user.id, "criar", "meta", result.data["id"],
               f"Criou meta {body.categoria}")
    return {"data": result.data}


@router.patch("/{meta_id}")
async def atualizar_meta(meta_id: str, body: MetaUpdate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    result = db.table("metas").update(data).eq("id", meta_id).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Meta não encontrada")

    log_action(user.id, "editar", "meta", meta_id, f"Atualizou meta {meta_id}")
    return {"data": result.data}


@router.delete("/{meta_id}")
async def excluir_meta(meta_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    db.table("metas").delete().eq("id", meta_id).execute()
    log_action(user.id, "excluir", "meta", meta_id, f"Excluiu meta {meta_id}")
    return {"ok": True}
