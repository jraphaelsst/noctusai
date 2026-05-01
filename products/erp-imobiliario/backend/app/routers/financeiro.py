"""
Financeiro CRUD Router — Financial transactions management.

Manages income/expense tracking, payment status, financial summaries,
and cash flow analysis.

-- CREATE TABLE lancamentos (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   tipo text NOT NULL CHECK (tipo IN ('receita', 'despesa')),
--   categoria text NOT NULL,
--   descricao text NOT NULL,
--   valor numeric NOT NULL,
--   data_vencimento date NOT NULL,
--   data_pagamento date,
--   status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'pago', 'atrasado', 'cancelado')),
--   forma_pagamento text,
--   imovel_id uuid,
--   cliente_id uuid,
--   comissao_id uuid,
--   recorrente boolean NOT NULL DEFAULT false,
--   observacoes text,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from datetime import datetime, timezone

from noctusai_lib.primitives.timeutil import now_utc
from dateutil.relativedelta import relativedelta
from typing import Optional, Literal
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.financeiro_service import FinanceiroService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/financeiro", tags=["Financeiro"])


# --- Pydantic models ---

class LancamentoCreate(BaseModel):
    tipo: Literal["receita", "despesa"]
    categoria: str = Field(..., min_length=1, max_length=100)
    descricao: str = Field(..., min_length=1, max_length=500)
    valor: float = Field(..., gt=0, description="Valor deve ser > 0")
    data_vencimento: str = Field(..., description="Data de vencimento (YYYY-MM-DD)")
    data_pagamento: Optional[str] = Field(default=None, description="Data de pagamento (YYYY-MM-DD)")
    status: Optional[Literal["pendente", "pago", "atrasado", "cancelado"]] = "pendente"
    forma_pagamento: Optional[str] = Field(default=None, max_length=50)
    imovel_id: Optional[str] = None
    cliente_id: Optional[str] = None
    comissao_id: Optional[str] = None
    recorrente: bool = False
    observacoes: Optional[str] = None


class LancamentoUpdate(BaseModel):
    tipo: Optional[Literal["receita", "despesa"]] = None
    categoria: Optional[str] = Field(default=None, min_length=1, max_length=100)
    descricao: Optional[str] = Field(default=None, min_length=1, max_length=500)
    valor: Optional[float] = Field(default=None, gt=0)
    data_vencimento: Optional[str] = None
    data_pagamento: Optional[str] = None
    status: Optional[Literal["pendente", "pago", "atrasado", "cancelado"]] = None
    forma_pagamento: Optional[str] = Field(default=None, max_length=50)
    imovel_id: Optional[str] = None
    cliente_id: Optional[str] = None
    comissao_id: Optional[str] = None
    recorrente: Optional[bool] = None
    observacoes: Optional[str] = None


# --- Endpoints ---

@router.get("")
async def listar_lancamentos(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo: receita ou despesa"),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    data_inicio: Optional[str] = Query(None, description="Data início (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoria"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    authorization: Optional[str] = Header(None),
):
    """List financial transactions with filters and pagination."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Build count query
    count_query = db.table("lancamentos").select("id", count="exact")
    if tipo:
        count_query = count_query.eq("tipo", tipo)
    if status:
        count_query = count_query.eq("status", status)
    if categoria:
        count_query = count_query.eq("categoria", categoria)
    if data_inicio:
        count_query = count_query.gte("data_vencimento", data_inicio)
    if data_fim:
        count_query = count_query.lte("data_vencimento", data_fim)

    # Build data query
    query = db.table("lancamentos").select("*").order("data_vencimento", desc=True)
    if tipo:
        query = query.eq("tipo", tipo)
    if status:
        query = query.eq("status", status)
    if categoria:
        query = query.eq("categoria", categoria)
    if data_inicio:
        query = query.gte("data_vencimento", data_inicio)
    if data_fim:
        query = query.lte("data_vencimento", data_fim)

    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/resumo")
async def resumo_financeiro(
    data_inicio: Optional[str] = Query(None, description="Data início (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
    authorization: Optional[str] = Header(None),
):
    """Get financial summary: total receitas, despesas, saldo, and overdue count."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    service = FinanceiroService(db, user.id)

    # Mark overdue transactions first
    try:
        await service.mark_overdue()
    except Exception as e:
        logger.warning(f"Failed to mark overdue: {e}")

    # Default to current year start if no data_inicio provided
    if not data_inicio:
        data_inicio = datetime.now(timezone.utc).strftime("%Y-01-01")

    # Fetch lancamentos (for summary calculation)
    query = db.table("lancamentos").select("*")
    query = query.gte("data_vencimento", data_inicio)
    if data_fim:
        query = query.lte("data_vencimento", data_fim)

    result = query.execute()
    lancamentos = result.data or []

    resumo = service.get_resumo(lancamentos)
    return success_response(resumo)


@router.get("/fluxo-caixa")
async def fluxo_caixa(
    meses: int = Query(12, ge=1, le=24, description="Número de meses"),
    authorization: Optional[str] = Header(None),
):
    """Get cash flow by month for the last N months."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    service = FinanceiroService(db, user.id)

    # Only fetch data from the relevant time window
    cutoff = (now_utc() - relativedelta(months=meses)).strftime("%Y-%m-%d")

    # Fetch lancamentos for cash flow within the time window
    result = db.table("lancamentos").select("*").gte("data_vencimento", cutoff).order("data_vencimento", desc=False).execute()
    lancamentos = result.data or []

    fluxo = service.get_fluxo_caixa(lancamentos)

    # Return only the last N months
    if len(fluxo) > meses:
        fluxo = fluxo[-meses:]

    return success_response(fluxo)


@router.get("/{lancamento_id}")
async def obter_lancamento(lancamento_id: str, authorization: Optional[str] = Header(None)):
    """Get a single financial transaction by ID."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("lancamentos").select("*").eq("id", lancamento_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    return success_response(result.data)


@router.post("")
async def criar_lancamento(body: LancamentoCreate, authorization: Optional[str] = Header(None)):
    """Create a new financial transaction."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)

    result = db.table("lancamentos").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar lançamento")

    log_action(user.id, "criar", "lancamento", row["id"],
               f"Criou lançamento {body.tipo}: {body.descricao}")

    return success_response(row)


@router.patch("/{lancamento_id}")
async def atualizar_lancamento(
    lancamento_id: str,
    body: LancamentoUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update an existing financial transaction."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("lancamentos").update(data).eq("id", lancamento_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")

    log_action(user.id, "editar", "lancamento", lancamento_id,
               f"Editou lançamento {lancamento_id}")

    return success_response(row)


@router.delete("/{lancamento_id}")
async def excluir_lancamento(lancamento_id: str, authorization: Optional[str] = Header(None)):
    """Delete a financial transaction."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    check = db.table("lancamentos").select("id").eq("id", lancamento_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")

    db.table("lancamentos").delete().eq("id", lancamento_id).execute()

    log_action(user.id, "excluir", "lancamento", lancamento_id,
               f"Excluiu lançamento {lancamento_id}")

    return ok_response("Lançamento excluído com sucesso")
