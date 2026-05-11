"""
Propostas CRUD Router — Proposal and negotiation workflow management.

Manages real estate proposals with status transitions, counter-proposals,
history tracking, and statistics.

-- CREATE TABLE propostas (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   imovel_id uuid NOT NULL,
--   cliente_id uuid NOT NULL,
--   corretor_id uuid NOT NULL,
--   valor_proposta numeric NOT NULL,
--   valor_contraproposta numeric,
--   status text NOT NULL DEFAULT 'enviada' CHECK (status IN ('enviada', 'em_analise', 'contraproposta', 'aceita', 'recusada', 'expirada')),
--   condicoes_pagamento text,
--   prazo_validade date,
--   observacoes text,
--   historico jsonb NOT NULL DEFAULT '[]',
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.propostas_service import PropostasService
from app.config import settings
from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/propostas", tags=["Propostas"])


# --- Pydantic models ---

class PropostaCreate(BaseModel):
    imovel_id: str
    cliente_id: str
    valor_proposta: float = Field(..., gt=0, description="Valor da proposta deve ser > 0")
    condicoes_pagamento: Optional[str] = Field(default=None, max_length=1000)
    prazo_validade: Optional[str] = Field(default=None, description="Prazo de validade (YYYY-MM-DD)")
    observacoes: Optional[str] = Field(default=None, max_length=2000)


class PropostaUpdate(BaseModel):
    status: Optional[Literal["enviada", "em_analise", "contraproposta", "aceita", "recusada", "expirada"]] = None
    valor_proposta: Optional[float] = Field(default=None, gt=0)
    valor_contraproposta: Optional[float] = Field(default=None, gt=0)
    condicoes_pagamento: Optional[str] = Field(default=None, max_length=1000)
    prazo_validade: Optional[str] = None
    observacoes: Optional[str] = Field(default=None, max_length=2000)


class ContrapropostaCreate(BaseModel):
    valor_contraproposta: float = Field(..., gt=0, description="Valor da contraproposta deve ser > 0")
    condicoes_pagamento: Optional[str] = Field(default=None, max_length=1000)
    observacoes: Optional[str] = Field(default=None, max_length=2000)


# --- Endpoints ---

@router.get("")
async def listar_propostas(
    status: Optional[str] = Query(None, description="Filtrar por status"),
    imovel_id: Optional[str] = Query(None, description="Filtrar por imóvel"),
    cliente_id: Optional[str] = Query(None, description="Filtrar por cliente"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    auth = Depends(get_current_user)):
    """List proposals with filters and pagination."""
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Build count query
    count_query = db.table("propostas").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if imovel_id:
        count_query = count_query.eq("imovel_id", imovel_id)
    if cliente_id:
        count_query = count_query.eq("cliente_id", cliente_id)

    # Build data query
    query = db.table("propostas").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
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


@router.get("/stats")
async def stats_propostas(auth = Depends(get_current_user)):
    """Get proposal statistics by status."""
    user, token = auth
    db = get_user_client(token)

    service = PropostasService(db, user.id)

    result = db.table("propostas").select("status").execute()
    propostas = result.data or []

    stats = service.get_stats(propostas)
    return success_response(stats)


@router.get("/{proposta_id}")
async def obter_proposta(proposta_id: str, auth = Depends(get_current_user)):
    """Get a single proposal by ID."""
    user, token = auth
    db = get_user_client(token)

    result = db.table("propostas").select("*").eq("id", proposta_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
    return success_response(result.data)


@router.post("")
async def criar_proposta(body: PropostaCreate, auth = Depends(get_current_user)):
    """Create a new proposal."""
    user, token = auth
    db = get_user_client(token)

    service = PropostasService(db, user.id)

    data = body.model_dump(exclude_none=True)
    data["corretor_id"] = user.id
    data["status"] = "enviada"

    # Initialize history with creation event
    history_entry = service.build_history_entry(
        action="Proposta criada",
        details={"valor": body.valor_proposta},
        user_id=user.id,
    )
    data["historico"] = [history_entry]

    result = db.table("propostas").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar proposta")

    log_action(user.id, "criar", "proposta", row["id"],
               f"Criou proposta para imóvel {body.imovel_id}, valor {body.valor_proposta}")

    return success_response(row)


@router.patch("/{proposta_id}")
async def atualizar_proposta(
    proposta_id: str,
    body: PropostaUpdate,
    auth = Depends(get_current_user)):
    """Update a proposal. Validates status transitions."""
    user, token = auth
    db = get_user_client(token)

    service = PropostasService(db, user.id)

    # Fetch current proposal
    current = db.table("propostas").select("*").eq("id", proposta_id).single().execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Validate status transition if status is changing
    if "status" in update_data:
        current_status = current.data["status"]
        new_status = update_data["status"]
        if not service.validate_status_transition(current_status, new_status):
            valid = service.get_valid_transitions(current_status)
            raise HTTPException(
                status_code=400,
                detail=f"Transição de status inválida: {current_status} -> {new_status}. "
                       f"Transições válidas: {', '.join(valid) if valid else 'nenhuma (estado terminal)'}"
            )

        # Add history entry for status change
        history = current.data.get("historico", [])
        entry = service.build_history_entry(
            action=f"Status alterado: {current_status} -> {new_status}",
            user_id=user.id,
        )
        history.append(entry)
        update_data["historico"] = history

    result = db.table("propostas").update(update_data).eq("id", proposta_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao atualizar proposta")

    log_action(user.id, "editar", "proposta", proposta_id,
               f"Editou proposta {proposta_id}")

    return success_response(row)


@router.post("/{proposta_id}/contraproposta")
async def criar_contraproposta(
    proposta_id: str,
    body: ContrapropostaCreate,
    auth = Depends(get_current_user)):
    """Submit a counter-proposal for an existing proposal."""
    user, token = auth
    db = get_user_client(token)

    service = PropostasService(db, user.id)

    # Fetch current proposal
    current = db.table("propostas").select("*").eq("id", proposta_id).single().execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")

    current_status = current.data["status"]
    if not service.validate_status_transition(current_status, "contraproposta"):
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível fazer contraproposta no status atual: {current_status}"
        )

    # Build history entry
    history = current.data.get("historico", [])
    entry = service.build_history_entry(
        action="Contraproposta enviada",
        details={
            "valor_contraproposta": body.valor_contraproposta,
            "valor_original": current.data["valor_proposta"],
        },
        user_id=user.id,
    )
    history.append(entry)

    update_data = {
        "status": "contraproposta",
        "valor_contraproposta": body.valor_contraproposta,
        "historico": history,
    }
    if body.condicoes_pagamento:
        update_data["condicoes_pagamento"] = body.condicoes_pagamento
    if body.observacoes:
        update_data["observacoes"] = body.observacoes

    result = db.table("propostas").update(update_data).eq("id", proposta_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao registrar contraproposta")

    log_action(user.id, "contraproposta", "proposta", proposta_id,
               f"Contraproposta de {body.valor_contraproposta} para proposta {proposta_id}")

    return success_response(row)


@router.delete("/{proposta_id}")
async def excluir_proposta(proposta_id: str, auth = Depends(get_current_user)):
    """Delete a proposal."""
    user, token = auth
    db = get_user_client(token)

    delete_or_404(db, "propostas", ("id", proposta_id), message = "Proposta não encontrada")

    log_action(user.id, "excluir", "proposta", proposta_id,
               f"Excluiu proposta {proposta_id}")

    return ok_response("Proposta excluída com sucesso")
