"""Investment portfolio router."""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from app.dependencies import get_current_user_org, get_user_client, first_or_none
from app.responses import success_response, ok_response
from app.schemas.carteira import CarteiraCreate, CarteiraUpdate, AlocacaoAlvoCreate
from app.services.carteira_service import CarteiraService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/carteiras", tags=["Carteiras"])


@router.get("")
async def listar_carteiras(auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = CarteiraService(db, org_id)
    data = await service.listar()
    return success_response(data, total=len(data))


@router.get("/{carteira_id}")
async def obter_carteira(carteira_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = CarteiraService(db, org_id)
    data = await service.obter(carteira_id)
    if not data:
        raise HTTPException(status_code=404, detail="Carteira nao encontrada")
    return success_response(data)


@router.get("/{carteira_id}/resumo")
async def resumo_carteira(carteira_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = CarteiraService(db, org_id)
    data = await service.resumo(carteira_id)
    if not data:
        raise HTTPException(status_code=404, detail="Carteira nao encontrada")
    return success_response(data)


@router.post("")
async def criar_carteira(body: CarteiraCreate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = CarteiraService(db, org_id)
    data = await service.criar(body.model_dump(exclude_none=True))
    if not data:
        raise HTTPException(status_code=500, detail="Erro ao criar carteira")
    return success_response(data)


@router.patch("/{carteira_id}")
async def atualizar_carteira(carteira_id: str, body: CarteiraUpdate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = CarteiraService(db, org_id)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    data = await service.atualizar(carteira_id, updates)
    if not data:
        raise HTTPException(status_code=404, detail="Carteira nao encontrada")
    return success_response(data)


@router.delete("/{carteira_id}")
async def excluir_carteira(carteira_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = CarteiraService(db, org_id)
    await service.excluir(carteira_id)
    return ok_response("Carteira excluida com sucesso")


@router.post("/{carteira_id}/alocacao")
async def definir_alocacao_alvo(carteira_id: str, body: AlocacaoAlvoCreate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)

    # Verify carteira belongs to org
    carteira = db.table("carteiras").select("id").eq("id", carteira_id).eq("org_id", org_id).execute()
    if not carteira.data:
        raise HTTPException(status_code=404, detail="Carteira nao encontrada")

    data = body.model_dump()
    data["carteira_id"] = carteira_id

    # Check for existing allocation for this asset class, update if exists
    existing = db.table("alocacao_alvo").select("id").eq("carteira_id", carteira_id).eq("classe_ativo", data.get("classe_ativo")).execute()
    if existing.data:
        result = db.table("alocacao_alvo").update(data).eq("id", existing.data[0]["id"]).execute()
    else:
        result = db.table("alocacao_alvo").insert(data).execute()
    row = first_or_none(result)
    return success_response(row)
