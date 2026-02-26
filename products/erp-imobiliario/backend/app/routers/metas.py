"""
Metas CRUD Router — Goals/targets management.
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, get_admin_client, log_action
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metas", tags=["Metas"])


class MetaCreate(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=255)
    categoria: Literal[
        "captacao", "visitas", "contatos", "propostas", "fechamento",
        "captacao_imoveis", "captacao_compradores", "atualizacao_imoveis", "outro"
    ] = "captacao"
    tipo: Literal["diaria", "semanal", "mensal", "anual"]
    meta_pretendida: int = Field(..., ge=1, description="Quantidade alvo deve ser >= 1")
    data_prazo: str  # Server handles timezone
    usuario_id: Optional[str] = None


class MetaUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=255)
    meta_realizada: Optional[int] = Field(default=None, ge=0)
    status: Optional[Literal["aberta", "concluida", "atrasada", "no_prazo", "vence_amanha"]] = None
    detalhes: Optional[str] = None


@router.get("")
async def listar_metas(
    corretor_id: Optional[str] = Query(None),
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
    count_query = db.table("metas").select("id", count="exact")
    if corretor_id:
        count_query = count_query.eq("usuario_id", corretor_id)

    # Data query with pagination
    query = db.table("metas").select("*").order("data_prazo", desc=True)
    if corretor_id:
        query = query.eq("usuario_id", corretor_id)

    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(result.data or [])

    return paginated_response(result.data or [], total, validated_page, validated_page_size)


@router.get("/hoje")
async def metas_hoje(authorization: Optional[str] = Header(None)):
    """Get current São Paulo date and today's metas."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Server-side date calculation (São Paulo timezone)
    admin = get_admin_client()
    date_result = admin.rpc("get_data_sp").execute()
    data_hoje = date_result.data if date_result.data else None

    query = db.table("metas").select("*").eq("usuario_id", user.id)
    if data_hoje:
        query = query.eq("data_prazo", data_hoje)

    result = query.execute()
    return success_response({"metas": result.data or [], "data_hoje": data_hoje})


@router.post("")
async def criar_meta(body: MetaCreate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data.get("usuario_id"):
        data["usuario_id"] = user.id

    result = db.table("metas").insert(data).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar meta")

    log_action(user.id, "criar", "meta", result.data["id"],
               f"Criou meta {body.categoria}")
    return success_response(result.data)


@router.patch("/{meta_id}")
async def atualizar_meta(meta_id: str, body: MetaUpdate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    result = db.table("metas").update(data).eq("id", meta_id).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Meta não encontrada")

    log_action(user.id, "editar", "meta", meta_id, f"Atualizou meta {meta_id}")
    return success_response(result.data)


@router.delete("/{meta_id}")
async def excluir_meta(meta_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    db.table("metas").delete().eq("id", meta_id).execute()
    log_action(user.id, "excluir", "meta", meta_id, f"Excluiu meta {meta_id}")
    return ok_response("Meta excluída com sucesso")
