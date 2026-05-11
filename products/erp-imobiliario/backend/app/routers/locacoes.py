"""
Locacoes (Rental/Lease) Router — Manages lease contracts, rent adjustments, and renewals.

-- CREATE TABLE contratos_locacao (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   imovel_id uuid NOT NULL,
--   locatario_id uuid NOT NULL,
--   proprietario_id uuid,
--   valor_aluguel numeric NOT NULL,
--   dia_vencimento int NOT NULL DEFAULT 10,
--   data_inicio date NOT NULL,
--   data_fim date NOT NULL,
--   indice_reajuste text NOT NULL DEFAULT 'IGPM' CHECK (indice_reajuste IN ('IGPM', 'IPCA', 'INPC', 'fixo')),
--   percentual_reajuste numeric,
--   status text NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'encerrado', 'renovado', 'inadimplente')),
--   taxa_administracao numeric NOT NULL DEFAULT 10.0,
--   valor_caucao numeric,
--   observacoes text,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import Field

from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings
from app.services.locacoes_service import calculate_reajuste
from noctusai_lib.api.crud_safety import delete_or_404
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/locacoes", tags=["Locações"])


# --------------- Schemas ---------------

class ContratoCreate(StrictHttpModel):
    imovel_id: str
    locatario_id: str
    proprietario_id: Optional[str] = None
    valor_aluguel: float = Field(..., gt=0, description="Valor do aluguel mensal")
    dia_vencimento: int = Field(default=10, ge=1, le=31)
    data_inicio: str = Field(..., description="Data de início (YYYY-MM-DD)")
    data_fim: str = Field(..., description="Data de término (YYYY-MM-DD)")
    indice_reajuste: Literal["IGPM", "IPCA", "INPC", "fixo"] = "IGPM"
    percentual_reajuste: Optional[float] = Field(default=None, ge=0, le=100)
    taxa_administracao: float = Field(default=10.0, ge=0, le=100)
    valor_caucao: Optional[float] = Field(default=None, ge=0)
    observacoes: Optional[str] = None


class ContratoUpdate(StrictHttpModel):
    valor_aluguel: Optional[float] = Field(default=None, gt=0)
    dia_vencimento: Optional[int] = Field(default=None, ge=1, le=31)
    data_fim: Optional[str] = None
    indice_reajuste: Optional[Literal["IGPM", "IPCA", "INPC", "fixo"]] = None
    percentual_reajuste: Optional[float] = Field(default=None, ge=0, le=100)
    status: Optional[Literal["ativo", "encerrado", "renovado", "inadimplente"]] = None
    taxa_administracao: Optional[float] = Field(default=None, ge=0, le=100)
    valor_caucao: Optional[float] = Field(default=None, ge=0)
    observacoes: Optional[str] = None


class ReajusteRequest(StrictHttpModel):
    percentual: Optional[float] = Field(default=None, ge=0, le=100, description="Override do percentual")
    aplicar: bool = Field(default=False, description="Se True, aplica o reajuste; se False, apenas calcula preview")


class RenovarRequest(StrictHttpModel):
    nova_data_fim: str = Field(..., description="Nova data de término (YYYY-MM-DD)")
    novo_valor: Optional[float] = Field(default=None, gt=0, description="Novo valor; se omitido, mantém atual")


# --------------- Endpoints ---------------

@router.get("")
async def listar_contratos(
    status: Optional[str] = Query(None, description="Filtrar por status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    auth = Depends(get_current_user)):
    """List lease contracts with optional status filter."""
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("contratos_locacao").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data query
    query = db.table("contratos_locacao").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    return paginated_response(result.data or [], total, validated_page, validated_page_size)


@router.post("")
async def criar_contrato(body: ContratoCreate, auth = Depends(get_current_user)):
    """Create a new lease contract."""
    user, token = auth
    db = get_user_client(token)

    # Validate dates
    try:
        dt_inicio = date.fromisoformat(body.data_inicio)
        dt_fim = date.fromisoformat(body.data_fim)
        if dt_fim <= dt_inicio:
            raise HTTPException(status_code=400, detail="Data de término deve ser posterior à data de início")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use YYYY-MM-DD")

    data = body.model_dump(exclude_none=True)

    result = db.table("contratos_locacao").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar contrato de locação")

    log_action(user.id, "criar", "contrato_locacao", row["id"],
               f"Criou contrato de locação para imóvel {body.imovel_id}")

    return success_response(row)


@router.get("/{contrato_id}")
async def obter_contrato(contrato_id: str, auth = Depends(get_current_user)):
    """Get a single lease contract by ID."""
    user, token = auth
    db = get_user_client(token)

    result = db.table("contratos_locacao").select("*").eq(
        "id", contrato_id
    ).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    return success_response(result.data)


@router.patch("/{contrato_id}")
async def atualizar_contrato(
    contrato_id: str,
    body: ContratoUpdate,
    auth = Depends(get_current_user)):
    """Update a lease contract."""
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("contratos_locacao").update(data).eq(
        "id", contrato_id
    ).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    log_action(user.id, "editar", "contrato_locacao", contrato_id,
               f"Atualizou contrato {contrato_id}")
    return success_response(row)


@router.delete("/{contrato_id}")
async def excluir_contrato(contrato_id: str, auth = Depends(get_current_user)):
    """Delete a lease contract."""
    user, token = auth
    db = get_user_client(token)

    delete_or_404(db, "contratos_locacao", ("id", contrato_id), message = "Contrato de locação não encontrado")
    log_action(user.id, "excluir", "contrato_locacao", contrato_id,
               f"Excluiu contrato {contrato_id}")
    return ok_response("Contrato de locação excluído com sucesso")


@router.post("/{contrato_id}/reajuste")
async def aplicar_reajuste(
    contrato_id: str,
    body: ReajusteRequest,
    auth = Depends(get_current_user)):
    """
    Calculate or apply a rent adjustment.

    If `aplicar` is False (default), returns a preview.
    If `aplicar` is True, updates the contract's valor_aluguel.
    """
    user, token = auth
    db = get_user_client(token)

    contrato_res = db.table("contratos_locacao").select("*").eq(
        "id", contrato_id
    ).single().execute()
    if not contrato_res.data:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    contrato = contrato_res.data
    resultado = calculate_reajuste(
        valor_atual=float(contrato["valor_aluguel"]),
        indice=contrato["indice_reajuste"],
        percentual=body.percentual,
    )

    if body.aplicar:
        db.table("contratos_locacao").update({
            "valor_aluguel": resultado["valor_novo"],
        }).eq("id", contrato_id).execute()

        log_action(user.id, "reajuste", "contrato_locacao", contrato_id,
                   f"Reajustou aluguel de {resultado['valor_anterior']} para {resultado['valor_novo']}",
                   resultado)
        resultado["aplicado"] = True
    else:
        resultado["aplicado"] = False

    return success_response(resultado)


@router.post("/{contrato_id}/renovar")
async def renovar_contrato(
    contrato_id: str,
    body: RenovarRequest,
    auth = Depends(get_current_user)):
    """
    Renew a lease contract.

    Sets the current contract's status to 'renovado' and creates a new
    contract with the extended end date.
    """
    user, token = auth
    db = get_user_client(token)

    contrato_res = db.table("contratos_locacao").select("*").eq(
        "id", contrato_id
    ).single().execute()
    if not contrato_res.data:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    contrato = contrato_res.data

    # Validate new end date
    try:
        nova_data_fim = date.fromisoformat(body.nova_data_fim)
        data_fim_atual = date.fromisoformat(str(contrato["data_fim"])[:10])
        if nova_data_fim <= data_fim_atual:
            raise HTTPException(
                status_code=400,
                detail="Nova data de término deve ser posterior à data atual do contrato",
            )
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use YYYY-MM-DD")

    # Mark current contract as renovado
    db.table("contratos_locacao").update({"status": "renovado"}).eq(
        "id", contrato_id
    ).execute()

    # Create renewed contract
    novo_valor = body.novo_valor if body.novo_valor else float(contrato["valor_aluguel"])
    new_data = {
        "imovel_id": contrato["imovel_id"],
        "locatario_id": contrato["locatario_id"],
        "proprietario_id": contrato.get("proprietario_id"),
        "valor_aluguel": novo_valor,
        "dia_vencimento": contrato["dia_vencimento"],
        "data_inicio": str(contrato["data_fim"])[:10],  # starts where old ends
        "data_fim": body.nova_data_fim,
        "indice_reajuste": contrato["indice_reajuste"],
        "percentual_reajuste": contrato.get("percentual_reajuste"),
        "taxa_administracao": contrato.get("taxa_administracao", 10.0),
        "valor_caucao": contrato.get("valor_caucao"),
        "status": "ativo",
        "observacoes": f"Renovação do contrato {contrato_id}",
    }
    # Remove None values
    new_data = {k: v for k, v in new_data.items() if v is not None}

    novo_result = db.table("contratos_locacao").insert(new_data).execute()
    novo_row = first_or_none(novo_result)
    if not novo_row:
        raise HTTPException(status_code=500, detail="Erro ao criar contrato renovado")

    log_action(user.id, "renovar", "contrato_locacao", contrato_id,
               f"Renovou contrato {contrato_id} → {novo_row['id']}",
               {"contrato_anterior_id": contrato_id, "novo_contrato_id": novo_row["id"]})

    return success_response({
        "contrato_anterior": contrato,
        "contrato_novo": novo_row,
    })
