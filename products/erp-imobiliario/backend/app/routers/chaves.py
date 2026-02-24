"""
Chaves (Key Control) API endpoints.

Manages property keys: registration, checkout, return, and history tracking.

-- CREATE TABLE chaves (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   imovel_id uuid NOT NULL,
--   codigo text NOT NULL,
--   descricao text,
--   status text NOT NULL DEFAULT 'disponivel' CHECK (status IN ('disponivel', 'emprestada', 'perdida')),
--   ultima_retirada_por uuid,
--   ultima_retirada_nome text,
--   ultima_retirada_em timestamptz,
--   ultima_devolucao_em timestamptz,
--   observacoes text,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE TABLE chaves_historico (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   chave_id uuid NOT NULL REFERENCES chaves(id),
--   acao text NOT NULL CHECK (acao IN ('retirada', 'devolucao')),
--   corretor_id uuid NOT NULL,
--   corretor_nome text NOT NULL,
--   motivo text,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_user_client, log_action
from app.responses import paginated_response, success_response, calculate_pagination
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chaves", tags=["Chaves"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChaveCreate(BaseModel):
    imovel_id: str
    codigo: str = Field(..., min_length=1, max_length=50)
    descricao: Optional[str] = Field(default=None, max_length=255)
    observacoes: Optional[str] = None


class ChaveUpdate(BaseModel):
    codigo: Optional[str] = Field(default=None, min_length=1, max_length=50)
    descricao: Optional[str] = Field(default=None, max_length=255)
    status: Optional[Literal["disponivel", "emprestada", "perdida"]] = None
    observacoes: Optional[str] = None


class RetiradaBody(BaseModel):
    corretor_nome: str = Field(..., min_length=1, max_length=150)
    motivo: Optional[str] = Field(default=None, max_length=500)


class DevolucaoBody(BaseModel):
    corretor_nome: str = Field(..., min_length=1, max_length=150)
    motivo: Optional[str] = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def listar_chaves(
    status: Optional[str] = Query(None, description="Filtrar por status: disponivel, emprestada, perdida"),
    imovel_id: Optional[str] = Query(None, description="Filtrar por imóvel"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(None),
):
    """Lista todas as chaves cadastradas, com filtros opcionais."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("chaves").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if imovel_id:
        count_query = count_query.eq("imovel_id", imovel_id)
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data query
    query = db.table("chaves").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    if imovel_id:
        query = query.eq("imovel_id", imovel_id)
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    return paginated_response(result.data or [], total, validated_page, validated_page_size)


@router.post("")
async def criar_chave(body: ChaveCreate, authorization: Optional[str] = Header(None)):
    """Registra uma nova chave de imóvel."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    data["status"] = "disponivel"

    result = db.table("chaves").insert(data).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao registrar chave")

    log_action(user.id, "criar", "chave", result.data["id"],
               f"Registrou chave {body.codigo} para imóvel {body.imovel_id}")
    return success_response(result.data)


@router.get("/{chave_id}")
async def obter_chave(chave_id: str, authorization: Optional[str] = Header(None)):
    """Obtém detalhes de uma chave com seu histórico."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("chaves").select("*").eq("id", chave_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Chave não encontrada")

    # Fetch history
    hist = db.table("chaves_historico").select("*").eq(
        "chave_id", chave_id
    ).order("created_at", desc=True).limit(50).execute()

    chave = result.data
    chave["historico"] = hist.data or []
    return success_response(chave)


@router.patch("/{chave_id}")
async def atualizar_chave(chave_id: str, body: ChaveUpdate, authorization: Optional[str] = Header(None)):
    """Atualiza informações de uma chave."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("chaves").update(data).eq("id", chave_id).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Chave não encontrada")

    log_action(user.id, "editar", "chave", chave_id, f"Atualizou chave {chave_id}")
    return success_response(result.data)


@router.post("/{chave_id}/retirada")
async def retirar_chave(chave_id: str, body: RetiradaBody, authorization: Optional[str] = Header(None)):
    """Registra a retirada (empréstimo) de uma chave."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Verify key exists and is available
    existing = db.table("chaves").select("*").eq("id", chave_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Chave não encontrada")
    if existing.data["status"] == "emprestada":
        raise HTTPException(status_code=409, detail="Chave já está emprestada")
    if existing.data["status"] == "perdida":
        raise HTTPException(status_code=409, detail="Chave marcada como perdida — não pode ser retirada")

    now = datetime.now(timezone.utc).isoformat()

    # Update key status
    update_data = {
        "status": "emprestada",
        "ultima_retirada_por": user.id,
        "ultima_retirada_nome": body.corretor_nome,
        "ultima_retirada_em": now,
    }
    result = db.table("chaves").update(update_data).eq("id", chave_id).select().single().execute()

    # Record history
    db.table("chaves_historico").insert({
        "chave_id": chave_id,
        "acao": "retirada",
        "corretor_id": user.id,
        "corretor_nome": body.corretor_nome,
        "motivo": body.motivo,
    }).execute()

    log_action(user.id, "retirada", "chave", chave_id,
               f"Retirou chave {chave_id} — {body.corretor_nome}")
    return success_response(result.data)


@router.post("/{chave_id}/devolucao")
async def devolver_chave(chave_id: str, body: DevolucaoBody, authorization: Optional[str] = Header(None)):
    """Registra a devolução de uma chave."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Verify key exists and is borrowed
    existing = db.table("chaves").select("*").eq("id", chave_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Chave não encontrada")
    if existing.data["status"] == "disponivel":
        raise HTTPException(status_code=409, detail="Chave já está disponível")

    now = datetime.now(timezone.utc).isoformat()

    # Update key status
    update_data = {
        "status": "disponivel",
        "ultima_devolucao_em": now,
    }
    result = db.table("chaves").update(update_data).eq("id", chave_id).select().single().execute()

    # Record history
    db.table("chaves_historico").insert({
        "chave_id": chave_id,
        "acao": "devolucao",
        "corretor_id": user.id,
        "corretor_nome": body.corretor_nome,
        "motivo": body.motivo,
    }).execute()

    log_action(user.id, "devolucao", "chave", chave_id,
               f"Devolveu chave {chave_id} — {body.corretor_nome}")
    return success_response(result.data)


@router.get("/{chave_id}/historico")
async def historico_chave(
    chave_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(None),
):
    """Retorna o histórico de retiradas/devoluções de uma chave."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    count_result = db.table("chaves_historico").select("id", count="exact").eq(
        "chave_id", chave_id
    ).execute()
    total = count_result.count if count_result.count is not None else 0

    result = db.table("chaves_historico").select("*").eq(
        "chave_id", chave_id
    ).order("created_at", desc=True).range(
        offset, offset + validated_page_size - 1
    ).execute()

    return paginated_response(result.data or [], total, validated_page, validated_page_size)
