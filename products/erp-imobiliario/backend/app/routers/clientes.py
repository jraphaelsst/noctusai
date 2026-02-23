"""
Clientes CRUD Router — Manages clients, archiving, and pipeline moves.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, EmailStr
from app.dependencies import get_current_user, get_user_client, get_admin_client, log_action
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clientes", tags=["Clientes"])


class ClienteCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    telefone: Optional[str] = Field(default=None, max_length=20)
    origem: Optional[str] = None
    interesse: Optional[str] = None
    observacoes: Optional[str] = None
    probabilidade: Optional[int] = Field(default=None, ge=0, le=100)
    valor_estimado: Optional[float] = Field(default=None, ge=0)


class ClienteUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    telefone: Optional[str] = Field(default=None, max_length=20)
    origem: Optional[str] = None
    interesse: Optional[str] = None
    observacoes: Optional[str] = None
    probabilidade: Optional[int] = Field(default=None, ge=0, le=100)
    valor_estimado: Optional[float] = Field(default=None, ge=0)
    etapa_atual: Optional[str] = None


class MoverEtapaRequest(BaseModel):
    para_etapa: str
    motivo: Optional[str] = None
    novo_indice: Optional[int] = None


@router.get("")
async def listar_clientes(
    busca: Optional[str] = Query(None),
    responsavel_id: Optional[str] = Query(None),
    origem: Optional[str] = Query(None),
    etapa: Optional[str] = Query(None),
    incluir_arquivados: bool = Query(False),
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

    # Build base query for counting
    count_query = db.table("clientes").select("id", count="exact")
    if not incluir_arquivados:
        count_query = count_query.eq("arquivado", False)
    if etapa:
        count_query = count_query.eq("etapa_atual", etapa)
    if origem and origem != "todas":
        count_query = count_query.eq("origem", origem)
    if responsavel_id and responsavel_id != "todos":
        count_query = count_query.eq("usuario_id", responsavel_id)

    # Build data query with pagination
    query = db.table("clientes").select(
        "*, usuario:profiles!clientes_usuario_id_fkey(id, nome, email)"
    ).order("created_at", desc=True)

    if not incluir_arquivados:
        query = query.eq("arquivado", False)
    if etapa:
        query = query.eq("etapa_atual", etapa)
    if origem and origem != "todas":
        query = query.eq("origem", origem)
    if responsavel_id and responsavel_id != "todos":
        query = query.eq("usuario_id", responsavel_id)

    # Apply pagination
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    # Get total count
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    # Server-side search (applied after fetching - for full-text search consider DB-level)
    if busca:
        q = busca.lower()
        data = [c for c in data if any(
            q in str(c.get(f, "") or "").lower()
            for f in ["nome", "email", "telefone", "interesse", "observacoes"]
        )]
        # When searching, we can't accurately paginate, return all matching from current page
        total = len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/{cliente_id}")
async def obter_cliente(cliente_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("clientes").select(
        "*, usuario:profiles!clientes_usuario_id_fkey(id, nome, email)"
    ).eq("id", cliente_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return success_response(result.data)


@router.post("")
async def criar_cliente(body: ClienteCreate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    data["usuario_id"] = user.id

    result = db.table("clientes").insert(data).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar cliente")

    log_action(user.id, "criar", "cliente", result.data["id"],
               f"Criou cliente {body.nome}")
    return success_response(result.data)


@router.patch("/{cliente_id}")
async def atualizar_cliente(cliente_id: str, body: ClienteUpdate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("clientes").update(data).eq("id", cliente_id).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    log_action(user.id, "editar", "cliente", cliente_id, f"Editou cliente {cliente_id}")
    return success_response(result.data)


@router.delete("/{cliente_id}")
async def excluir_cliente(cliente_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    db.table("clientes").delete().eq("id", cliente_id).execute()
    log_action(user.id, "excluir", "cliente", cliente_id, f"Excluiu cliente {cliente_id}")
    return ok_response("Cliente excluído com sucesso")


@router.post("/{cliente_id}/arquivar")
async def toggle_arquivar(cliente_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Get current state
    current = db.table("clientes").select("arquivado, nome").eq("id", cliente_id).single().execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    novo_estado = not current.data["arquivado"]
    result = db.table("clientes").update({"arquivado": novo_estado}).eq("id", cliente_id).select().single().execute()

    acao = "arquivar" if novo_estado else "desarquivar"
    log_action(user.id, acao, "cliente", cliente_id,
               f"{'Arquivou' if novo_estado else 'Desarquivou'} cliente {current.data['nome']}")
    return success_response(result.data)


@router.post("/{cliente_id}/mover-etapa")
async def mover_etapa(cliente_id: str, body: MoverEtapaRequest, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    valid_etapas = {"qualificacao", "visitas", "proposta", "negociacao", "fechado"}
    if body.para_etapa not in valid_etapas:
        raise HTTPException(status_code=400, detail=f"Etapa inválida. Use: {valid_etapas}")

    update_data = {"etapa_atual": body.para_etapa}
    if body.novo_indice is not None:
        update_data["kanban_pos"] = body.novo_indice

    result = db.table("clientes").update(update_data).eq("id", cliente_id).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    log_action(user.id, "mover", "cliente", cliente_id,
               f"Moveu cliente para etapa {body.para_etapa}",
               {"para_etapa": body.para_etapa, "motivo": body.motivo})
    return success_response(result.data)
