"""
Atividades Router — Client activity tracking.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from app.dependencies import get_current_user, get_user_client, log_action

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/atividades", tags=["Atividades"])


class AtividadeCreate(BaseModel):
    cliente_id: str
    tipo: str  # ligacao, visita, proposta, email, reuniao
    descricao: str
    data_execucao: Optional[str] = None


@router.get("")
async def listar_atividades(
    cliente_id: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    query = db.table("atividades").select(
        "*, usuario:profiles!atividades_usuario_id_fkey(id, nome, email)"
    ).order("data_execucao", desc=True)

    if cliente_id:
        query = query.eq("cliente_id", cliente_id)

    result = query.execute()
    return {"data": result.data or [], "total": len(result.data or [])}


@router.post("")
async def criar_atividade(body: AtividadeCreate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    data["usuario_id"] = user.id

    result = db.table("atividades").insert(data).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar atividade")

    log_action(user.id, "criar", "atividade", result.data["id"],
               f"Registrou atividade {body.tipo}",
               {"tipo": body.tipo, "cliente_id": body.cliente_id})
    return {"data": result.data}
