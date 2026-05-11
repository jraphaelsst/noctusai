"""
Análise de Crédito (Credit Analysis) API endpoints.

Manages credit checks for clients: initiation, results, and history.

-- CREATE TABLE analises_credito (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   cliente_id uuid,
--   cpf text NOT NULL,
--   nome text NOT NULL,
--   score int,
--   status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'aprovado', 'reprovado', 'em_analise')),
--   resultado jsonb NOT NULL DEFAULT '{}',
--   fonte text NOT NULL DEFAULT 'manual' CHECK (fonte IN ('serasa', 'boa_vista', 'manual')),
--   validade date,
--   consultado_por uuid NOT NULL,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
import re
from typing import Optional, Literal
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field, field_validator

from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import paginated_response, success_response, calculate_pagination
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analise-credito", tags=["Análise de Crédito"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ConsultaCreditoBody(BaseModel):
    cpf: str = Field(..., min_length=11, max_length=14, description="CPF com ou sem formatação")
    nome: str = Field(..., min_length=2, max_length=255)
    cliente_id: Optional[str] = None
    fonte: Literal["serasa", "boa_vista", "manual"] = "manual"
    # Fields used for manual analysis
    score: Optional[int] = Field(default=None, ge=0, le=1000)
    resultado: Optional[dict] = Field(default_factory=dict)
    observacoes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("cpf")
    @classmethod
    def validate_cpf(cls, v: str) -> str:
        cleaned = re.sub(r'\D', '', v)
        if len(cleaned) != 11:
            raise ValueError("CPF deve conter 11 dígitos")
        return cleaned


class AtualizarAnaliseBody(BaseModel):
    status: Optional[Literal["pendente", "aprovado", "reprovado", "em_analise"]] = None
    score: Optional[int] = Field(default=None, ge=0, le=1000)
    resultado: Optional[dict] = None
    validade: Optional[str] = Field(default=None, description="Data de validade (YYYY-MM-DD)")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/consultar")
async def consultar_credito(body: ConsultaCreditoBody, auth = Depends(get_current_user)):
    """Inicia uma consulta de crédito para uma pessoa (CPF)."""
    user, token = auth
    db = get_user_client(token)

    # Import the service for credit analysis
    from app.services.analise_credito_service import executar_analise

    # Execute analysis based on source
    analise_resultado = executar_analise(
        cpf=body.cpf,
        nome=body.nome,
        fonte=body.fonte,
        score_manual=body.score,
        resultado_manual=body.resultado,
    )

    # Determine status based on analysis result
    status = analise_resultado.get("status", "pendente")
    if body.fonte == "manual" and body.score is not None:
        if body.score >= 700:
            status = "aprovado"
        elif body.score >= 400:
            status = "em_analise"
        else:
            status = "reprovado"

    data = {
        "cpf": body.cpf,
        "nome": body.nome,
        "cliente_id": body.cliente_id,
        "fonte": body.fonte,
        "score": analise_resultado.get("score", body.score),
        "status": status,
        "resultado": analise_resultado.get("resultado", body.resultado or {}),
        "consultado_por": user.id,
        "validade": analise_resultado.get("validade"),
    }

    result = db.table("analises_credito").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao registrar análise de crédito")

    log_action(user.id, "consultar", "analise_credito", row["id"],
               f"Consultou crédito de {body.nome} (CPF: ***{body.cpf[-4:]}) via {body.fonte}")

    return success_response(row)


@router.get("/{analise_id}")
async def obter_analise(analise_id: str, auth = Depends(get_current_user)):
    """Retorna o resultado de uma análise de crédito específica."""
    user, token = auth
    db = get_user_client(token)

    result = db.table("analises_credito").select("*").eq("id", analise_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Análise de crédito não encontrada")

    return success_response(result.data)


@router.patch("/{analise_id}")
async def atualizar_analise(analise_id: str, body: AtualizarAnaliseBody, auth = Depends(get_current_user)):
    """Atualiza o status ou resultado de uma análise de crédito."""
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("analises_credito").update(data).eq("id", analise_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Análise de crédito não encontrada")

    log_action(user.id, "editar", "analise_credito", analise_id,
               f"Atualizou análise de crédito {analise_id}")
    return success_response(row)


@router.get("")
async def listar_analises(
    status: Optional[str] = Query(None, description="Filtrar por status"),
    fonte: Optional[str] = Query(None, description="Filtrar por fonte"),
    cpf: Optional[str] = Query(None, description="Filtrar por CPF"),
    cliente_id: Optional[str] = Query(None, description="Filtrar por cliente"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    auth = Depends(get_current_user)):
    """Lista análises de crédito com filtros opcionais."""
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("analises_credito").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if fonte:
        count_query = count_query.eq("fonte", fonte)
    if cpf:
        cleaned_cpf = re.sub(r'\D', '', cpf)
        count_query = count_query.eq("cpf", cleaned_cpf)
    if cliente_id:
        count_query = count_query.eq("cliente_id", cliente_id)

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data query
    query = db.table("analises_credito").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    if fonte:
        query = query.eq("fonte", fonte)
    if cpf:
        cleaned_cpf = re.sub(r'\D', '', cpf)
        query = query.eq("cpf", cleaned_cpf)
    if cliente_id:
        query = query.eq("cliente_id", cliente_id)

    query = query.range(offset, offset + validated_page_size - 1)
    result = query.execute()

    return paginated_response(result.data or [], total, validated_page, validated_page_size)
