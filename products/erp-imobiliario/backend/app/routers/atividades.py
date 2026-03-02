"""
Atividades Router — Client activity tracking.
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import paginated_response, success_response, calculate_pagination
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/atividades", tags=["Atividades"])


class AtividadeCreate(BaseModel):
    cliente_id: str
    tipo: Literal["ligacao", "visita", "proposta", "email", "reuniao"]
    descricao: str = Field(..., min_length=1, max_length=2000)
    data_execucao: Optional[str] = None


@router.get("")
async def listar_atividades(
    cliente_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Calculate pagination
    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("atividades").select("id", count="exact")
    if cliente_id:
        count_query = count_query.eq("cliente_id", cliente_id)

    # Data query with pagination
    query = db.table("atividades").select(
        "*, usuario:profiles!atividades_usuario_id_fkey(id, nome, email)"
    ).order("data_execucao", desc=True)

    if cliente_id:
        query = query.eq("cliente_id", cliente_id)

    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(result.data or [])

    return paginated_response(result.data or [], total, validated_page, validated_page_size)


@router.post("")
async def criar_atividade(body: AtividadeCreate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    data["usuario_id"] = user.id

    result = db.table("atividades").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar atividade")

    log_action(user.id, "criar", "atividade", row["id"],
               f"Registrou atividade {body.tipo}",
               {"tipo": body.tipo, "cliente_id": body.cliente_id})
    return success_response(row)
