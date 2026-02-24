"""
Comissoes CRUD Router — Commission management for real estate sales.

-- CREATE TABLE comissoes (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   venda_id uuid,
--   imovel_id uuid,
--   valor_venda numeric NOT NULL,
--   percentual_comissao numeric NOT NULL DEFAULT 6.0,
--   valor_comissao numeric NOT NULL,
--   status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'aprovada', 'paga', 'cancelada')),
--   data_venda date,
--   data_pagamento date,
--   observacoes text,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE TABLE comissoes_splits (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   comissao_id uuid NOT NULL REFERENCES comissoes(id) ON DELETE CASCADE,
--   corretor_id uuid NOT NULL,
--   corretor_nome text NOT NULL,
--   percentual numeric NOT NULL,
--   valor numeric NOT NULL,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal, List
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings
from app.services.comissoes_service import ComissoesService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/comissoes", tags=["Comissoes"])


# ---------- Schemas ----------

class SplitInput(BaseModel):
    corretor_id: str
    corretor_nome: str = Field(..., min_length=1, max_length=255)
    percentual: float = Field(..., gt=0, le=100)


class ComissaoCreate(BaseModel):
    venda_id: Optional[str] = None
    imovel_id: Optional[str] = None
    valor_venda: float = Field(..., gt=0, description="Valor da venda")
    percentual_comissao: float = Field(default=6.0, gt=0, le=100, description="Percentual de comissao")
    data_venda: Optional[str] = None
    observacoes: Optional[str] = None
    splits: Optional[List[SplitInput]] = None


class ComissaoStatusUpdate(BaseModel):
    status: Literal["pendente", "aprovada", "paga", "cancelada"]
    data_pagamento: Optional[str] = None
    observacoes: Optional[str] = None


# ---------- Endpoints ----------

@router.get("/resumo")
async def resumo_comissoes(
    authorization: Optional[str] = Header(None),
):
    """Get commission summary: totals by status and per agent."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Total by status
    all_comissoes = db.table("comissoes").select("valor_comissao, status").execute()
    comissoes_data = all_comissoes.data or []

    totals = {
        "total_pendente": 0.0,
        "total_aprovada": 0.0,
        "total_paga": 0.0,
        "total_cancelada": 0.0,
        "total_geral": 0.0,
        "quantidade": len(comissoes_data),
    }

    for c in comissoes_data:
        valor = c.get("valor_comissao", 0)
        status = c.get("status", "pendente")
        totals["total_geral"] += valor
        key = f"total_{status}"
        if key in totals:
            totals[key] += valor

    # Round
    for key in totals:
        if isinstance(totals[key], float):
            totals[key] = round(totals[key], 2)

    # Agent summary
    service = ComissoesService(db, user.id)
    por_corretor = service.get_agent_summary(db)

    return success_response({
        "totais": totals,
        "por_corretor": por_corretor,
    })


@router.get("")
async def listar_comissoes(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    authorization: Optional[str] = Header(None),
):
    """List commissions with optional status filter and pagination."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("comissoes").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data query
    query = db.table("comissoes").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    # Fetch splits for each commission
    comissao_ids = [c["id"] for c in data]
    if comissao_ids:
        splits_result = db.table("comissoes_splits").select("*").in_(
            "comissao_id", comissao_ids
        ).execute()
        splits_by_comissao = {}
        for s in (splits_result.data or []):
            cid = s["comissao_id"]
            if cid not in splits_by_comissao:
                splits_by_comissao[cid] = []
            splits_by_comissao[cid].append(s)

        for c in data:
            c["splits"] = splits_by_comissao.get(c["id"], [])

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/{comissao_id}")
async def obter_comissao(comissao_id: str, authorization: Optional[str] = Header(None)):
    """Get a single commission with its splits."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("comissoes").select("*").eq("id", comissao_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Comissao nao encontrada")

    comissao = result.data

    # Fetch splits
    splits_result = db.table("comissoes_splits").select("*").eq(
        "comissao_id", comissao_id
    ).execute()
    comissao["splits"] = splits_result.data or []

    return success_response(comissao)


@router.post("")
async def criar_comissao(body: ComissaoCreate, authorization: Optional[str] = Header(None)):
    """Create a new commission with optional splits."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Calculate commission value
    valor_comissao = ComissoesService.calculate_commission(
        body.valor_venda, body.percentual_comissao
    )

    # Validate splits if provided
    splits_validated = []
    if body.splits:
        try:
            splits_validated = ComissoesService.calculate_splits(
                valor_comissao, [s.model_dump() for s in body.splits]
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Create commission
    comissao_data = {
        "valor_venda": body.valor_venda,
        "percentual_comissao": body.percentual_comissao,
        "valor_comissao": valor_comissao,
        "status": "pendente",
    }
    if body.venda_id:
        comissao_data["venda_id"] = body.venda_id
    if body.imovel_id:
        comissao_data["imovel_id"] = body.imovel_id
    if body.data_venda:
        comissao_data["data_venda"] = body.data_venda
    if body.observacoes:
        comissao_data["observacoes"] = body.observacoes

    result = db.table("comissoes").insert(comissao_data).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar comissao")

    comissao = result.data

    # Create splits
    if splits_validated:
        for split in splits_validated:
            split["comissao_id"] = comissao["id"]
        db.table("comissoes_splits").insert(splits_validated).execute()

        # Re-fetch splits
        splits_result = db.table("comissoes_splits").select("*").eq(
            "comissao_id", comissao["id"]
        ).execute()
        comissao["splits"] = splits_result.data or []
    else:
        comissao["splits"] = []

    log_action(
        user.id, "criar", "comissao", comissao["id"],
        f"Criou comissao de R$ {valor_comissao:.2f}"
    )

    return success_response(comissao)


@router.patch("/{comissao_id}")
async def atualizar_comissao(
    comissao_id: str,
    body: ComissaoStatusUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update commission status (and optionally payment date/notes)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    update_data = {"status": body.status}
    if body.data_pagamento:
        update_data["data_pagamento"] = body.data_pagamento
    if body.observacoes is not None:
        update_data["observacoes"] = body.observacoes

    result = db.table("comissoes").update(update_data).eq(
        "id", comissao_id
    ).select().single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Comissao nao encontrada ou sem permissao")

    log_action(
        user.id, "editar", "comissao", comissao_id,
        f"Atualizou status da comissao para {body.status}"
    )

    return success_response(result.data)


@router.delete("/{comissao_id}")
async def excluir_comissao(comissao_id: str, authorization: Optional[str] = Header(None)):
    """Delete a commission and its splits (cascade)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Verify it exists
    existing = db.table("comissoes").select("id").eq("id", comissao_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Comissao nao encontrada")

    db.table("comissoes").delete().eq("id", comissao_id).execute()

    log_action(
        user.id, "excluir", "comissao", comissao_id,
        f"Excluiu comissao {comissao_id}"
    )

    return ok_response("Comissao excluida com sucesso")
