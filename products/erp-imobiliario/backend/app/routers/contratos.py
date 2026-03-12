"""
Contratos de Venda CRUD Router — Sale and rental contract management.

Manages contracts lifecycle, installment generation, payment tracking,
and overdue detection.

-- CREATE TABLE contratos (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   tipo text NOT NULL CHECK (tipo IN ('venda', 'locacao')),
--   status text NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'ativo', 'concluido', 'cancelado', 'distratado')),
--   cliente_id uuid NOT NULL,
--   imovel_id uuid NOT NULL,
--   proposta_id uuid,
--   valor_total numeric NOT NULL,
--   valor_entrada numeric NOT NULL DEFAULT 0,
--   num_parcelas integer NOT NULL DEFAULT 1,
--   data_inicio date NOT NULL,
--   data_fim date,
--   data_assinatura date,
--   observacoes text,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE TABLE parcelas_contrato (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   contrato_id uuid NOT NULL REFERENCES contratos(id),
--   numero integer NOT NULL,
--   valor numeric NOT NULL,
--   data_vencimento date NOT NULL,
--   data_pagamento date,
--   status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'pago', 'atrasado', 'cancelado')),
--   forma_pagamento text,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.contratos_service import ContratosService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/contratos", tags=["Contratos"])


# --- Pydantic models ---

class ContratoCreate(BaseModel):
    tipo: Literal["venda", "locacao"]
    status: Optional[Literal["rascunho", "ativo", "concluido", "cancelado", "distratado"]] = "rascunho"
    cliente_id: str = Field(..., description="ID do cliente")
    imovel_id: str = Field(..., description="ID do imóvel")
    proposta_id: Optional[str] = None
    valor_total: float = Field(..., gt=0, description="Valor total do contrato")
    valor_entrada: float = Field(default=0, ge=0, description="Valor de entrada")
    num_parcelas: int = Field(default=1, ge=1, description="Número de parcelas")
    data_inicio: str = Field(..., description="Data de início (YYYY-MM-DD)")
    data_fim: Optional[str] = Field(default=None, description="Data de fim (YYYY-MM-DD)")
    data_assinatura: Optional[str] = Field(default=None, description="Data de assinatura (YYYY-MM-DD)")
    observacoes: Optional[str] = None


class ContratoUpdate(BaseModel):
    tipo: Optional[Literal["venda", "locacao"]] = None
    status: Optional[Literal["rascunho", "ativo", "concluido", "cancelado", "distratado"]] = None
    cliente_id: Optional[str] = None
    imovel_id: Optional[str] = None
    proposta_id: Optional[str] = None
    valor_total: Optional[float] = Field(default=None, gt=0)
    valor_entrada: Optional[float] = Field(default=None, ge=0)
    num_parcelas: Optional[int] = Field(default=None, ge=1)
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    data_assinatura: Optional[str] = None
    observacoes: Optional[str] = None


class ParcelaUpdate(BaseModel):
    status: Optional[Literal["pendente", "pago", "atrasado", "cancelado"]] = None
    data_pagamento: Optional[str] = Field(default=None, description="Data de pagamento (YYYY-MM-DD)")
    forma_pagamento: Optional[str] = Field(default=None, max_length=50)


class GerarParcelasRequest(BaseModel):
    valor_entrada: float = Field(default=0, ge=0, description="Valor de entrada")
    num_parcelas: int = Field(..., ge=1, description="Número de parcelas")


# --- Endpoints ---

@router.get("")
async def listar_contratos(
    status: Optional[str] = Query(None, description="Filtrar por status"),
    cliente_id: Optional[str] = Query(None, description="Filtrar por cliente"),
    imovel_id: Optional[str] = Query(None, description="Filtrar por imóvel"),
    data_inicio: Optional[str] = Query(None, description="Data início (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    authorization: Optional[str] = Header(None),
):
    """List contracts with filters and pagination."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Build count query
    count_query = db.table("contratos").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if cliente_id:
        count_query = count_query.eq("cliente_id", cliente_id)
    if imovel_id:
        count_query = count_query.eq("imovel_id", imovel_id)
    if data_inicio:
        count_query = count_query.gte("data_inicio", data_inicio)
    if data_fim:
        count_query = count_query.lte("data_inicio", data_fim)

    # Build data query
    query = db.table("contratos").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    if cliente_id:
        query = query.eq("cliente_id", cliente_id)
    if imovel_id:
        query = query.eq("imovel_id", imovel_id)
    if data_inicio:
        query = query.gte("data_inicio", data_inicio)
    if data_fim:
        query = query.lte("data_inicio", data_fim)

    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/resumo")
async def resumo_contratos(
    authorization: Optional[str] = Header(None),
):
    """Get contract summary: total by status, valor total, inadimplencia count."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    service = ContratosService(db, user.id)

    # Mark overdue parcelas first
    try:
        await service.mark_overdue()
    except Exception as e:
        logger.warning(f"Failed to mark overdue parcelas: {e}")

    # Fetch all contratos for summary
    result = db.table("contratos").select("*").execute()
    contratos = result.data or []

    # Fetch all parcelas for inadimplencia check
    parcelas_result = db.table("parcelas_contrato").select("*").execute()
    parcelas = parcelas_result.data or []

    resumo = service.get_resumo(contratos)
    resumo["inadimplencia"] = service.check_inadimplencia(parcelas)

    return success_response(resumo)


@router.get("/{contrato_id}")
async def obter_contrato(contrato_id: str, authorization: Optional[str] = Header(None)):
    """Get a single contract by ID."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("contratos").select("*").eq("id", contrato_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    return success_response(result.data)


@router.post("")
async def criar_contrato(body: ContratoCreate, authorization: Optional[str] = Header(None)):
    """Create a new contract."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)

    result = db.table("contratos").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar contrato")

    log_action(user.id, "criar", "contrato", row["id"],
               f"Criou contrato {body.tipo} para cliente {body.cliente_id}")

    return success_response(row)


@router.patch("/{contrato_id}")
async def atualizar_contrato(
    contrato_id: str,
    body: ContratoUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update an existing contract."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("contratos").update(data).eq("id", contrato_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    log_action(user.id, "editar", "contrato", contrato_id,
               f"Editou contrato {contrato_id}")

    return success_response(row)


@router.delete("/{contrato_id}")
async def excluir_contrato(contrato_id: str, authorization: Optional[str] = Header(None)):
    """Delete a contract."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    check = db.table("contratos").select("id").eq("id", contrato_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    db.table("contratos").delete().eq("id", contrato_id).execute()

    log_action(user.id, "excluir", "contrato", contrato_id,
               f"Excluiu contrato {contrato_id}")

    return ok_response("Contrato excluído com sucesso")


@router.get("/{contrato_id}/parcelas")
async def listar_parcelas(
    contrato_id: str,
    authorization: Optional[str] = Header(None),
):
    """List installments for a contract."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("parcelas_contrato").select("*").eq(
        "contrato_id", contrato_id
    ).order("numero", desc=False).execute()

    data = result.data or []
    return success_response(data)


@router.post("/{contrato_id}/parcelas")
async def gerar_parcelas(
    contrato_id: str,
    body: GerarParcelasRequest,
    authorization: Optional[str] = Header(None),
):
    """Generate installment schedule for a contract."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Fetch the contract to get valor_total and data_inicio
    contrato_result = db.table("contratos").select("*").eq("id", contrato_id).single().execute()
    if not contrato_result.data:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    contrato = contrato_result.data
    service = ContratosService(db, user.id)

    parcelas = await service.gerar_parcelas(
        contrato_id=contrato_id,
        valor_total=float(contrato["valor_total"]),
        valor_entrada=body.valor_entrada,
        num_parcelas=body.num_parcelas,
        data_inicio=contrato["data_inicio"],
    )

    # Update contract with entrada and parcelas info
    db.table("contratos").update({
        "valor_entrada": body.valor_entrada,
        "num_parcelas": body.num_parcelas,
    }).eq("id", contrato_id).execute()

    log_action(user.id, "criar", "parcelas", contrato_id,
               f"Gerou {body.num_parcelas} parcelas para contrato {contrato_id}")

    return success_response(parcelas)


@router.patch("/parcelas/{parcela_id}")
async def atualizar_parcela(
    parcela_id: str,
    body: ParcelaUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update an installment (mark as paid, change status, etc.)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("parcelas_contrato").update(data).eq(
        "id", parcela_id
    ).execute()
    row = first_or_none(result)

    if not row:
        raise HTTPException(status_code=404, detail="Parcela não encontrada")

    log_action(user.id, "editar", "parcela", parcela_id,
               f"Editou parcela {parcela_id}")

    return success_response(row)
