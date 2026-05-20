"""
Seguros (Insurance) Router — Manages insurance policies for properties.

-- CREATE TABLE seguros (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   imovel_id uuid NOT NULL,
--   cliente_id uuid,
--   seguradora text NOT NULL,
--   numero_apolice text,
--   tipo_cobertura text NOT NULL CHECK (tipo_cobertura IN ('incendio', 'completo', 'responsabilidade_civil', 'vida', 'fianca_locaticia', 'outro')),
--   valor_cobertura numeric NOT NULL,
--   valor_premio numeric NOT NULL,
--   data_inicio date NOT NULL,
--   data_vencimento date NOT NULL,
--   status text NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'vencido', 'cancelado', 'renovado')),
--   auto_renovar boolean NOT NULL DEFAULT false,
--   observacoes text,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import Field

from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.seguros_service import SegurosService
from app.config import settings
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/seguros", tags=["Seguros"])


# --------------- Schemas ---------------

class SeguroCreate(StrictHttpModel):
    imovel_id: str
    cliente_id: Optional[str] = None
    seguradora: str = Field(..., min_length=1, max_length=255, description="Nome da seguradora")
    numero_apolice: Optional[str] = Field(default=None, max_length=100)
    tipo_cobertura: Literal[
        "incendio", "completo", "responsabilidade_civil",
        "vida", "fianca_locaticia", "outro"
    ]
    valor_cobertura: float = Field(..., gt=0, description="Valor total da cobertura")
    valor_premio: float = Field(..., gt=0, description="Valor do prêmio do seguro")
    data_inicio: str = Field(..., description="Data de início da apólice (YYYY-MM-DD)")
    data_vencimento: str = Field(..., description="Data de vencimento da apólice (YYYY-MM-DD)")
    auto_renovar: bool = False
    observacoes: Optional[str] = None


class SeguroUpdate(StrictHttpModel):
    cliente_id: Optional[str] = None
    seguradora: Optional[str] = Field(default=None, min_length=1, max_length=255)
    numero_apolice: Optional[str] = Field(default=None, max_length=100)
    tipo_cobertura: Optional[Literal[
        "incendio", "completo", "responsabilidade_civil",
        "vida", "fianca_locaticia", "outro"
    ]] = None
    valor_cobertura: Optional[float] = Field(default=None, gt=0)
    valor_premio: Optional[float] = Field(default=None, gt=0)
    data_inicio: Optional[str] = None
    data_vencimento: Optional[str] = None
    status: Optional[Literal["ativo", "vencido", "cancelado", "renovado"]] = None
    auto_renovar: Optional[bool] = None
    observacoes: Optional[str] = None


# --------------- Endpoints ---------------

@router.get("")
async def listar_seguros(
    status: Optional[str] = Query(None, description="Filtrar por status"),
    imovel_id: Optional[str] = Query(None, description="Filtrar por imóvel"),
    tipo_cobertura: Optional[str] = Query(None, description="Filtrar por tipo de cobertura"),
    seguradora: Optional[str] = Query(None, description="Filtrar por seguradora"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    auth = Depends(get_current_user)):
    """List insurance policies with optional filters and pagination."""
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("seguros").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if imovel_id:
        count_query = count_query.eq("imovel_id", imovel_id)
    if tipo_cobertura:
        count_query = count_query.eq("tipo_cobertura", tipo_cobertura)
    if seguradora:
        count_query = count_query.ilike("seguradora", f"%{seguradora}%")
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data query
    query = db.table("seguros").select("*").order("data_vencimento", desc=False)
    if status:
        query = query.eq("status", status)
    if imovel_id:
        query = query.eq("imovel_id", imovel_id)
    if tipo_cobertura:
        query = query.eq("tipo_cobertura", tipo_cobertura)
    if seguradora:
        query = query.ilike("seguradora", f"%{seguradora}%")
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    # Attach summary
    service = SegurosService(db, user.id)
    resumo = service.get_resumo(data)

    return {
        **paginated_response(data, total, validated_page, validated_page_size),
        "resumo": resumo,
    }


@router.get("/vencimentos")
async def listar_vencimentos(
    dias: int = Query(30, ge=1, le=365, description="Dias à frente para verificar vencimentos"),
    auth = Depends(get_current_user)):
    """List policies expiring in the next N days."""
    user, token = auth
    db = get_user_client(token)

    service = SegurosService(db, user.id)
    vencimentos = service.get_vencimentos(dias)

    return success_response(vencimentos)


@router.get("/{seguro_id}")
async def obter_seguro(seguro_id: str, auth = Depends(get_current_user)):
    """Get a single insurance policy by ID."""
    user, token = auth
    db = get_user_client(token)

    result = db.table("seguros").select("*").eq("id", seguro_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Seguro não encontrado")

    return success_response(result.data)


@router.post("")
async def criar_seguro(body: SeguroCreate, auth = Depends(get_current_user)):
    """Create a new insurance policy."""
    user, token = auth
    db = get_user_client(token)

    # Validate dates
    from datetime import date
    try:
        dt_inicio = date.fromisoformat(body.data_inicio)
        dt_vencimento = date.fromisoformat(body.data_vencimento)
        if dt_vencimento <= dt_inicio:
            raise HTTPException(
                status_code=400,
                detail="Data de vencimento deve ser posterior à data de início",
            )
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use YYYY-MM-DD")

    data = body.model_dump(exclude_none=True)
    data["status"] = "ativo"

    result = db.table("seguros").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar seguro")

    log_action(
        user.id, "criar", "seguro", row["id"],
        f"Criou apólice de seguro {body.tipo_cobertura} para imóvel {body.imovel_id}"
    )

    return success_response(row)


@router.patch("/{seguro_id}")
async def atualizar_seguro(
    seguro_id: str,
    body: SeguroUpdate,
    auth = Depends(get_current_user)):
    """Update an insurance policy."""
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("seguros").update(data).eq(
        "id", seguro_id
    ).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Seguro não encontrado")

    log_action(
        user.id, "editar", "seguro", seguro_id,
        f"Atualizou seguro {seguro_id}"
    )

    return success_response(row)


@router.delete("/{seguro_id}")
async def excluir_seguro(seguro_id: str, auth = Depends(get_current_user)):
    """Delete an insurance policy."""
    user, token = auth
    db = get_user_client(token)

    delete_or_404(db, "seguros", ("id", seguro_id), message="Seguro não encontrado")

    log_action(
        user.id, "excluir", "seguro", seguro_id,
        f"Excluiu seguro {seguro_id}"
    )

    return ok_response("Seguro excluído com sucesso")
