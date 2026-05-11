"""Transactions CRUD router with filtering and categorization."""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response, paginated_response, ok_response, calculate_pagination
from app.schemas.transacoes import TransacaoCreate, TransacaoUpdate
from app.services.transacoes_service import TransacoesService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/transacoes", tags=["Transacoes"])


@router.get("")
async def listar_transacoes(
    conta_id: Optional[str] = Query(None),
    categoria_id: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    busca: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = TransacoesService(db, org_id)

    validated_page, validated_page_size, offset = calculate_pagination(page, page_size, settings.max_page_size)

    data, total = await service.listar(
        conta_id=conta_id, categoria_id=categoria_id, tipo=tipo,
        data_inicio=data_inicio, data_fim=data_fim, busca=busca,
        offset=offset, limit=validated_page_size,
    )
    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/por-categoria")
async def transacoes_por_categoria(
    data_inicio: str = Query(...),
    data_fim: str = Query(...),
    auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = TransacoesService(db, org_id)
    data = await service.por_categoria(data_inicio, data_fim)
    return success_response(data)


@router.get("/{transacao_id}")
async def obter_transacao(transacao_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = TransacoesService(db, org_id)
    data = await service.obter(transacao_id)
    if not data:
        raise HTTPException(status_code=404, detail="Transacao nao encontrada")
    return success_response(data)


@router.post("")
async def criar_transacao(body: TransacaoCreate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = TransacoesService(db, org_id)
    data = await service.criar(body.model_dump(exclude_none=True))
    if not data:
        raise HTTPException(status_code=500, detail="Erro ao criar transacao")
    return success_response(data)


@router.patch("/{transacao_id}")
async def atualizar_transacao(transacao_id: str, body: TransacaoUpdate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = TransacoesService(db, org_id)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    data = await service.atualizar(transacao_id, updates)
    if not data:
        raise HTTPException(status_code=404, detail="Transacao nao encontrada")
    return success_response(data)


@router.delete("/{transacao_id}")
async def excluir_transacao(transacao_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = TransacoesService(db, org_id)
    await service.excluir(transacao_id)
    return ok_response("Transacao excluida com sucesso")
