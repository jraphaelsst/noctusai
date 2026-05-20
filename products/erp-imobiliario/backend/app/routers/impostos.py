"""
Impostos CRUD Router — IPTU and property tax management.

Manages tax records, payment tracking, installments, discounts,
and annual summaries per property.

-- CREATE TABLE impostos (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   imovel_id uuid NOT NULL,
--   tipo text NOT NULL CHECK (tipo IN ('iptu', 'itbi', 'txa_lixo', 'contribuicao_melhoria', 'outro')),
--   ano integer NOT NULL,
--   valor_total numeric NOT NULL,
--   valor_pago numeric NOT NULL DEFAULT 0,
--   num_parcelas integer NOT NULL DEFAULT 1,
--   parcela_atual integer NOT NULL DEFAULT 0,
--   desconto_cota_unica numeric NOT NULL DEFAULT 0,
--   data_vencimento date NOT NULL,
--   status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'parcial', 'pago', 'atrasado', 'isento')),
--   numero_guia text,
--   comprovante_url text,
--   observacoes text,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import Field
from app.dependencies import get_current_user, get_user_client, log_action, first_or_none, require_role

# erp-financial-surfaces-role-gate (2026-05-20): tax/fiscal data → accounting-tier roles.
_IMPOSTOS_ROLES = ("platform_admin", "owner", "admin", "contador")
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.impostos_service import ImpostosService
from app.config import settings
from noctusai_lib.api.crud_safety import delete_or_404
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/impostos", tags=["Impostos"])


# --- Pydantic models ---

class ImpostoCreate(StrictHttpModel):
    imovel_id: str = Field(..., description="ID do imóvel associado")
    tipo: Literal["iptu", "itbi", "txa_lixo", "contribuicao_melhoria", "outro"]
    ano: int = Field(..., ge=2000, le=2100, description="Ano de referência")
    valor_total: float = Field(..., gt=0, description="Valor total do imposto")
    valor_pago: float = Field(default=0, ge=0, description="Valor já pago")
    num_parcelas: int = Field(default=1, ge=1, le=12, description="Número de parcelas")
    parcela_atual: int = Field(default=0, ge=0, description="Parcela atual paga")
    desconto_cota_unica: float = Field(default=0, ge=0, le=100, description="Desconto cota única (%)")
    data_vencimento: str = Field(..., description="Data de vencimento (YYYY-MM-DD)")
    status: Optional[Literal["pendente", "parcial", "pago", "atrasado", "isento"]] = "pendente"
    numero_guia: Optional[str] = Field(default=None, max_length=100)
    comprovante_url: Optional[str] = None
    observacoes: Optional[str] = None


class ImpostoUpdate(StrictHttpModel):
    tipo: Optional[Literal["iptu", "itbi", "txa_lixo", "contribuicao_melhoria", "outro"]] = None
    ano: Optional[int] = Field(default=None, ge=2000, le=2100)
    valor_total: Optional[float] = Field(default=None, gt=0)
    valor_pago: Optional[float] = Field(default=None, ge=0)
    num_parcelas: Optional[int] = Field(default=None, ge=1, le=12)
    parcela_atual: Optional[int] = Field(default=None, ge=0)
    desconto_cota_unica: Optional[float] = Field(default=None, ge=0, le=100)
    data_vencimento: Optional[str] = None
    status: Optional[Literal["pendente", "parcial", "pago", "atrasado", "isento"]] = None
    numero_guia: Optional[str] = Field(default=None, max_length=100)
    comprovante_url: Optional[str] = None
    observacoes: Optional[str] = None


# --- Endpoints ---

@router.get("")
async def listar_impostos(
    imovel_id: Optional[str] = Query(None, description="Filtrar por imóvel"),
    ano: Optional[int] = Query(None, description="Filtrar por ano"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo de imposto"),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    auth_role = Depends(require_role(*_IMPOSTOS_ROLES))):
    """List tax records with filters and pagination."""
    user, token, _role = auth_role
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Build count query
    count_query = db.table("impostos").select("id", count="exact")
    if imovel_id:
        count_query = count_query.eq("imovel_id", imovel_id)
    if ano:
        count_query = count_query.eq("ano", ano)
    if tipo:
        count_query = count_query.eq("tipo", tipo)
    if status:
        count_query = count_query.eq("status", status)

    # Build data query
    query = db.table("impostos").select("*").order("data_vencimento", desc=True)
    if imovel_id:
        query = query.eq("imovel_id", imovel_id)
    if ano:
        query = query.eq("ano", ano)
    if tipo:
        query = query.eq("tipo", tipo)
    if status:
        query = query.eq("status", status)

    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/resumo")
async def resumo_impostos(
    ano: Optional[int] = Query(None, description="Ano de referência"),
    imovel_id: Optional[str] = Query(None, description="Filtrar por imóvel"),
    auth_role = Depends(require_role(*_IMPOSTOS_ROLES))):
    """Get annual tax summary: total due, paid, pending, overdue by year or property."""
    user, token, _role = auth_role
    db = get_user_client(token)
    # erp-financial-surfaces-role-gate: aggregate fiscal view → audit log.
    log_action(
        user.id, "ler", "impostos_resumo", None,
        f"Consultou resumo de impostos (ano={ano}, imovel_id={imovel_id})",
    )

    service = ImpostosService(db, user.id)

    # Mark overdue taxes first
    try:
        await service.check_vencidos()
    except Exception as e:
        logger.warning(f"Failed to mark overdue taxes: {e}")

    # Fetch impostos for summary
    query = db.table("impostos").select("*")
    if ano:
        query = query.eq("ano", ano)
    if imovel_id:
        query = query.eq("imovel_id", imovel_id)

    result = query.execute()
    impostos = result.data or []

    resumo = service.get_resumo(impostos)
    return success_response(resumo)


@router.get("/{imposto_id}")
async def obter_imposto(
    imposto_id: str,
    auth_role = Depends(require_role(*_IMPOSTOS_ROLES))):
    """Get a single tax record by ID."""
    user, token, _role = auth_role
    db = get_user_client(token)

    result = db.table("impostos").select("*").eq("id", imposto_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Imposto não encontrado")
    return success_response(result.data)


@router.post("")
async def criar_imposto(body: ImpostoCreate, auth = Depends(get_current_user)):
    """Create a new tax record."""
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)

    result = db.table("impostos").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar registro de imposto")

    log_action(user.id, "criar", "imposto", row["id"],
               f"Criou imposto {body.tipo} ano {body.ano}")

    return success_response(row)


@router.patch("/{imposto_id}")
async def atualizar_imposto(
    imposto_id: str,
    body: ImpostoUpdate,
    auth = Depends(get_current_user)):
    """Update an existing tax record (mark paid, add receipt, update installment)."""
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("impostos").update(data).eq("id", imposto_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Imposto não encontrado")

    log_action(user.id, "editar", "imposto", imposto_id,
               f"Editou imposto {imposto_id}")

    return success_response(row)


@router.delete("/{imposto_id}")
async def excluir_imposto(imposto_id: str, auth = Depends(get_current_user)):
    """Delete a tax record."""
    user, token = auth
    db = get_user_client(token)

    delete_or_404(db, "impostos", ("id", imposto_id), message = "Imposto não encontrado")

    log_action(user.id, "excluir", "imposto", imposto_id,
               f"Excluiu imposto {imposto_id}")

    return ok_response("Imposto excluído com sucesso")
