"""Investment operations (buy/sell/dividend) router."""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response, paginated_response, ok_response, calculate_pagination
from app.schemas.ativos import OperacaoCreate
from app.services.ativos_service import AtivosService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/operacoes", tags=["Operacoes"])


@router.get("")
async def listar_operacoes(
    carteira_id: Optional[str] = Query(None),
    ativo_id: Optional[str] = Query(None),
    ticker: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(None),
):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(page, page_size, settings.max_page_size)

    query = db.table("operacoes").select("*").eq("org_id", org_id).order("data", desc=True)
    count_query = db.table("operacoes").select("id", count="exact").eq("org_id", org_id)

    if carteira_id:
        query = query.eq("carteira_id", carteira_id)
        count_query = count_query.eq("carteira_id", carteira_id)
    if ativo_id:
        query = query.eq("ativo_id", ativo_id)
        count_query = count_query.eq("ativo_id", ativo_id)
    if ticker:
        query = query.eq("ticker", ticker)
        count_query = count_query.eq("ticker", ticker)

    query = query.range(offset, offset + validated_page_size - 1)
    result = query.execute()
    data = result.data or []

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/por-ativo/{ativo_id}")
async def operacoes_por_ativo(
    ativo_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(None),
):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(page, page_size, settings.max_page_size)

    query = db.table("operacoes").select("*").eq("ativo_id", ativo_id).eq("org_id", org_id).order("data", desc=True)
    query = query.range(offset, offset + validated_page_size - 1)
    result = query.execute()
    data = result.data or []

    count_result = db.table("operacoes").select("id", count="exact").eq("ativo_id", ativo_id).eq("org_id", org_id).execute()
    total = count_result.count if count_result.count is not None else len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/{operacao_id}")
async def obter_operacao(operacao_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    result = db.table("operacoes").select("*").eq("id", operacao_id).eq("org_id", org_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Operacao nao encontrada")
    return success_response(result.data)


@router.post("")
async def criar_operacao(body: OperacaoCreate, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = AtivosService(db, org_id)
    op_data = body.model_dump(exclude_none=True)
    op_data["org_id"] = org_id
    data = await service.registrar_operacao(op_data)
    if not data:
        raise HTTPException(status_code=500, detail="Erro ao registrar operacao")
    return success_response(data)


@router.delete("/{operacao_id}")
async def excluir_operacao(operacao_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = AtivosService(db, org_id)

    # Fetch operation before deleting to recalculate holding
    op_result = db.table("operacoes").select("*").eq("id", operacao_id).eq("org_id", org_id).execute()
    if not op_result.data:
        raise HTTPException(status_code=404, detail="Operacao nao encontrada")
    op = op_result.data[0]

    db.table("operacoes").delete().eq("id", operacao_id).eq("org_id", org_id).execute()

    # Recalculate holding from remaining operations if there's an ativo_id
    if op.get("ativo_id"):
        await service._recalcular_ativo_completo(op["ativo_id"])

    return ok_response("Operacao excluida com sucesso")
