"""
Integracao Bancaria Router — Bank integration, statement import, reconciliation, and CNAB remittance.

Manages bank statement imports, automatic and manual reconciliation of
movimentacoes against lancamentos, and generation of CNAB 240/400 remittance files.

-- CREATE TABLE extratos_bancarios (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   banco text NOT NULL,
--   agencia text,
--   conta text,
--   data_importacao timestamptz NOT NULL DEFAULT now(),
--   arquivo_nome text NOT NULL,
--   periodo_inicio date,
--   periodo_fim date,
--   total_registros integer NOT NULL DEFAULT 0,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE TABLE movimentacoes_bancarias (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   extrato_id uuid NOT NULL REFERENCES extratos_bancarios(id),
--   data date NOT NULL,
--   descricao text NOT NULL,
--   valor numeric NOT NULL,
--   tipo text NOT NULL CHECK (tipo IN ('credito', 'debito')),
--   conciliado boolean NOT NULL DEFAULT false,
--   lancamento_id uuid,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE TABLE remessas (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   tipo text NOT NULL CHECK (tipo IN ('cnab240', 'cnab400')),
--   banco text NOT NULL,
--   arquivo_nome text,
--   total_titulos integer NOT NULL DEFAULT 0,
--   valor_total numeric NOT NULL DEFAULT 0,
--   status text NOT NULL DEFAULT 'gerado' CHECK (status IN ('gerado', 'enviado', 'processado', 'erro')),
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal, List
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.banco_service import BancoService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/banco", tags=["Banco"])


# ---------- Schemas ----------

class MovimentacaoImport(BaseModel):
    data: str = Field(..., description="Data da movimentacao (YYYY-MM-DD)")
    descricao: str = Field(..., min_length=1, max_length=500)
    valor: float = Field(..., gt=0, description="Valor da movimentacao")
    tipo: Literal["credito", "debito"]


class ImportarExtratoRequest(BaseModel):
    banco: str = Field(..., min_length=1, max_length=100, description="Nome ou codigo do banco")
    agencia: Optional[str] = Field(default=None, max_length=20)
    conta: Optional[str] = Field(default=None, max_length=30)
    movimentacoes: List[MovimentacaoImport] = Field(..., min_length=1, description="Lista de movimentacoes do extrato")


class ConciliarRequest(BaseModel):
    movimentacao_id: str = Field(..., description="ID da movimentacao bancaria")
    lancamento_id: str = Field(..., description="ID do lancamento financeiro correspondente")


class TituloRemessa(BaseModel):
    valor: float = Field(..., gt=0, description="Valor do titulo")
    vencimento: str = Field(..., description="Data de vencimento (YYYY-MM-DD)")
    sacado_nome: str = Field(..., min_length=1, max_length=255, description="Nome do sacado")
    sacado_cpf: str = Field(..., min_length=11, max_length=14, description="CPF/CNPJ do sacado")


class GerarRemessaRequest(BaseModel):
    tipo: Literal["cnab240", "cnab400"]
    banco: str = Field(..., min_length=1, max_length=100)
    titulos: List[TituloRemessa] = Field(..., min_length=1, description="Lista de titulos para a remessa")


# ---------- Endpoints ----------

@router.post("/importar")
async def importar_extrato(body: ImportarExtratoRequest, auth = Depends(get_current_user)):
    """Import a bank statement with its movimentacoes."""
    user, token = auth
    db = get_user_client(token)

    service = BancoService(db, user.id)

    # Determine periodo from movimentacoes
    datas = [m.data for m in body.movimentacoes]
    arquivo_nome = f"extrato_{body.banco}_{min(datas)}_{max(datas)}.csv"

    movimentacoes_data = [m.model_dump() for m in body.movimentacoes]

    try:
        resultado = service.importar_extrato(
            banco=body.banco,
            agencia=body.agencia,
            conta=body.conta,
            movimentacoes=movimentacoes_data,
            arquivo_nome=arquivo_nome,
        )
    except Exception as e:
        logger.error(f"Erro ao importar extrato: {e}")
        raise HTTPException(status_code=500, detail="Erro ao importar extrato bancario")

    log_action(
        user.id, "criar", "extrato_bancario", resultado["extrato_id"],
        f"Importou extrato {body.banco} com {len(body.movimentacoes)} movimentacoes"
    )

    return success_response(resultado)


@router.get("/extratos")
async def listar_extratos(
    banco: Optional[str] = Query(None, description="Filtrar por banco"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    auth = Depends(get_current_user)):
    """List imported bank statements with pagination."""
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("extratos_bancarios").select("id", count="exact")
    if banco:
        count_query = count_query.eq("banco", banco)
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data query
    query = db.table("extratos_bancarios").select("*").order("data_importacao", desc=True)
    if banco:
        query = query.eq("banco", banco)
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/conciliacao")
async def listar_pendentes_conciliacao(
    extrato_id: Optional[str] = Query(None, description="Filtrar por extrato"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    auth = Depends(get_current_user)):
    """Get movimentacoes pending reconciliation (conciliado=false)."""
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("movimentacoes_bancarias").select("id", count="exact").eq("conciliado", False)
    if extrato_id:
        count_query = count_query.eq("extrato_id", extrato_id)
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data query
    query = (
        db.table("movimentacoes_bancarias")
        .select("*")
        .eq("conciliado", False)
        .order("data", desc=True)
    )
    if extrato_id:
        query = query.eq("extrato_id", extrato_id)
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    return paginated_response(data, total, validated_page, validated_page_size)


@router.post("/conciliar")
async def conciliar_movimentacao(body: ConciliarRequest, auth = Depends(get_current_user)):
    """Manually reconcile a bank movimentacao with a lancamento financeiro."""
    user, token = auth
    db = get_user_client(token)

    service = BancoService(db, user.id)

    try:
        resultado = service.conciliar(body.movimentacao_id, body.lancamento_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao conciliar movimentacao: {e}")
        raise HTTPException(status_code=500, detail="Erro ao conciliar movimentacao")

    log_action(
        user.id, "editar", "movimentacao_bancaria", body.movimentacao_id,
        f"Conciliou movimentacao {body.movimentacao_id} com lancamento {body.lancamento_id}"
    )

    return success_response(resultado)


@router.post("/gerar-remessa")
async def gerar_remessa(body: GerarRemessaRequest, auth = Depends(get_current_user)):
    """Generate a CNAB remittance file (240 or 400 format)."""
    user, token = auth
    db = get_user_client(token)

    service = BancoService(db, user.id)

    titulos_data = [t.model_dump() for t in body.titulos]

    try:
        resultado = service.gerar_remessa(
            tipo=body.tipo,
            banco=body.banco,
            titulos=titulos_data,
        )
    except Exception as e:
        logger.error(f"Erro ao gerar remessa: {e}")
        raise HTTPException(status_code=500, detail="Erro ao gerar arquivo de remessa")

    log_action(
        user.id, "criar", "remessa", resultado["remessa_id"],
        f"Gerou remessa {body.tipo} banco {body.banco} com {len(body.titulos)} titulos"
    )

    return success_response(resultado)


@router.get("/retorno/{remessa_id}")
async def obter_retorno_remessa(remessa_id: str, auth = Depends(get_current_user)):
    """Get remittance status and return information."""
    user, token = auth
    db = get_user_client(token)

    result = db.table("remessas").select("*").eq("id", remessa_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Remessa nao encontrada")

    return success_response(result.data)
