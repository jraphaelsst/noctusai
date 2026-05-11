"""Categories CRUD router with hierarchy support."""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response, ok_response
from app.schemas.categorias import CategoriaCreate, CategoriaUpdate
from app.services.categorias_service import CategoriasService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/categorias", tags=["Categorias"])


@router.get("")
async def listar_categorias(
    tipo: Optional[str] = Query(None),
    auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = CategoriasService(db, org_id)
    data = await service.listar(tipo=tipo)
    return success_response(data, total=len(data))


@router.get("/arvore")
async def categorias_arvore(
    tipo: Optional[str] = Query(None),
    auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = CategoriasService(db, org_id)
    data = await service.arvore(tipo=tipo)
    return success_response(data)


@router.get("/{categoria_id}")
async def obter_categoria(categoria_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = CategoriasService(db, org_id)
    data = await service.obter(categoria_id)
    if not data:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")
    return success_response(data)


@router.post("")
async def criar_categoria(body: CategoriaCreate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = CategoriasService(db, org_id)
    data = await service.criar(body.model_dump(exclude_none=True))
    if not data:
        raise HTTPException(status_code=500, detail="Erro ao criar categoria")
    return success_response(data)


@router.patch("/{categoria_id}")
async def atualizar_categoria(categoria_id: str, body: CategoriaUpdate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = CategoriasService(db, org_id)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    data = await service.atualizar(categoria_id, updates)
    if not data:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")
    return success_response(data)


@router.delete("/{categoria_id}")
async def excluir_categoria(categoria_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = CategoriasService(db, org_id)
    await service.excluir(categoria_id)
    return ok_response("Categoria excluida com sucesso")
