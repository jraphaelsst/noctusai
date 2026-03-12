"""
Manutencao CRUD Router — Maintenance & work orders management.

Manages work orders for property maintenance including preventive,
corrective, emergency, and renovation types with priority tracking,
cost management, and overdue detection.

-- CREATE TABLE ordens_servico (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   imovel_id uuid,
--   cliente_id uuid,
--   titulo text NOT NULL,
--   descricao text NOT NULL,
--   tipo text NOT NULL CHECK (tipo IN ('preventiva', 'corretiva', 'emergencial', 'reforma')),
--   prioridade text NOT NULL DEFAULT 'media' CHECK (prioridade IN ('baixa', 'media', 'alta', 'urgente')),
--   status text NOT NULL DEFAULT 'aberto' CHECK (status IN ('aberto', 'em_andamento', 'aguardando', 'concluido', 'cancelado')),
--   responsavel text,
--   fornecedor text,
--   custo_estimado numeric,
--   custo_real numeric,
--   data_abertura date NOT NULL,
--   data_previsao date,
--   data_conclusao date,
--   fotos text[] NOT NULL DEFAULT '{}',
--   observacoes text,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal, List
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.manutencao_service import ManutencaoService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/manutencao", tags=["Manutencao"])


# --- Pydantic models ---

class OrdemServicoCreate(BaseModel):
    imovel_id: Optional[str] = None
    cliente_id: Optional[str] = None
    titulo: str = Field(..., min_length=1, max_length=255)
    descricao: str = Field(..., min_length=1, max_length=2000)
    tipo: Literal["preventiva", "corretiva", "emergencial", "reforma"]
    prioridade: Optional[Literal["baixa", "media", "alta", "urgente"]] = "media"
    status: Optional[Literal["aberto", "em_andamento", "aguardando", "concluido", "cancelado"]] = "aberto"
    responsavel: Optional[str] = Field(default=None, max_length=255)
    fornecedor: Optional[str] = Field(default=None, max_length=255)
    custo_estimado: Optional[float] = Field(default=None, ge=0)
    custo_real: Optional[float] = Field(default=None, ge=0)
    data_abertura: str = Field(..., description="Data de abertura (YYYY-MM-DD)")
    data_previsao: Optional[str] = Field(default=None, description="Data de previsao (YYYY-MM-DD)")
    data_conclusao: Optional[str] = Field(default=None, description="Data de conclusao (YYYY-MM-DD)")
    fotos: Optional[List[str]] = Field(default_factory=list)
    observacoes: Optional[str] = None


class OrdemServicoUpdate(BaseModel):
    imovel_id: Optional[str] = None
    cliente_id: Optional[str] = None
    titulo: Optional[str] = Field(default=None, min_length=1, max_length=255)
    descricao: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    tipo: Optional[Literal["preventiva", "corretiva", "emergencial", "reforma"]] = None
    prioridade: Optional[Literal["baixa", "media", "alta", "urgente"]] = None
    status: Optional[Literal["aberto", "em_andamento", "aguardando", "concluido", "cancelado"]] = None
    responsavel: Optional[str] = Field(default=None, max_length=255)
    fornecedor: Optional[str] = Field(default=None, max_length=255)
    custo_estimado: Optional[float] = Field(default=None, ge=0)
    custo_real: Optional[float] = Field(default=None, ge=0)
    data_previsao: Optional[str] = None
    data_conclusao: Optional[str] = None
    fotos: Optional[List[str]] = None
    observacoes: Optional[str] = None


# --- Endpoints ---

@router.get("")
async def listar_ordens(
    status: Optional[str] = Query(None, description="Filtrar por status"),
    prioridade: Optional[str] = Query(None, description="Filtrar por prioridade"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo"),
    imovel_id: Optional[str] = Query(None, description="Filtrar por imovel"),
    cliente_id: Optional[str] = Query(None, description="Filtrar por cliente"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    authorization: Optional[str] = Header(None),
):
    """List work orders with filters and pagination."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Build count query
    count_query = db.table("ordens_servico").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if prioridade:
        count_query = count_query.eq("prioridade", prioridade)
    if tipo:
        count_query = count_query.eq("tipo", tipo)
    if imovel_id:
        count_query = count_query.eq("imovel_id", imovel_id)
    if cliente_id:
        count_query = count_query.eq("cliente_id", cliente_id)

    # Build data query
    query = db.table("ordens_servico").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    if prioridade:
        query = query.eq("prioridade", prioridade)
    if tipo:
        query = query.eq("tipo", tipo)
    if imovel_id:
        query = query.eq("imovel_id", imovel_id)
    if cliente_id:
        query = query.eq("cliente_id", cliente_id)

    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/resumo")
async def resumo_manutencao(
    authorization: Optional[str] = Header(None),
):
    """Get maintenance summary: counts by status, avg resolution time, overdue count, total cost."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    service = ManutencaoService(db, user.id)

    # Mark overdue orders first
    try:
        await service.mark_overdue()
    except Exception as e:
        logger.warning(f"Failed to mark overdue orders: {e}")

    # Fetch all ordens for summary calculation
    result = db.table("ordens_servico").select("*").execute()
    ordens = result.data or []

    resumo = service.get_resumo(ordens)
    return success_response(resumo)


@router.get("/{ordem_id}")
async def obter_ordem(ordem_id: str, authorization: Optional[str] = Header(None)):
    """Get a single work order by ID."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("ordens_servico").select("*").eq("id", ordem_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Ordem de servico nao encontrada")
    return success_response(result.data)


@router.post("")
async def criar_ordem(body: OrdemServicoCreate, authorization: Optional[str] = Header(None)):
    """Create a new work order."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)

    result = db.table("ordens_servico").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar ordem de servico")

    log_action(user.id, "criar", "ordem_servico", row["id"],
               f"Criou ordem de servico: {body.titulo}")

    return success_response(row)


@router.patch("/{ordem_id}")
async def atualizar_ordem(
    ordem_id: str,
    body: OrdemServicoUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update an existing work order."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("ordens_servico").update(data).eq("id", ordem_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Ordem de servico nao encontrada")

    log_action(user.id, "editar", "ordem_servico", ordem_id,
               f"Editou ordem de servico {ordem_id}")

    return success_response(row)


@router.delete("/{ordem_id}")
async def excluir_ordem(ordem_id: str, authorization: Optional[str] = Header(None)):
    """Delete a work order."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    check = db.table("ordens_servico").select("id").eq("id", ordem_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Ordem de servico não encontrada")

    db.table("ordens_servico").delete().eq("id", ordem_id).execute()

    log_action(user.id, "excluir", "ordem_servico", ordem_id,
               f"Excluiu ordem de servico {ordem_id}")

    return ok_response("Ordem de servico excluida com sucesso")
