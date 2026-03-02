"""
Products Router — Product catalog for the NoctusAI marketplace.

GET    /api/products              — List all products (public catalog)
GET    /api/products/{id}         — Product details
POST   /api/products              — Create product (platform admin only)
PATCH  /api/products/{id}         — Update product (platform admin only)
DELETE /api/products/{id}         — Deactivate product (platform admin only)
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/products", tags=["Products"])


class ProductCreate(BaseModel):
    nome: str
    slug: str
    descricao: Optional[str] = None
    icone: Optional[str] = None
    url_base: str  # e.g. http://localhost:8080 or https://erp.noctus.ai
    cor: Optional[str] = "#6366f1"  # brand color


class ProductUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    icone: Optional[str] = None
    url_base: Optional[str] = None
    cor: Optional[str] = None
    ativo: Optional[bool] = None


@router.get("")
async def listar_products(authorization: Optional[str] = Header(None)):
    """List all products in the marketplace."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    result = db.table("products").select("*").eq("ativo", True).order("nome").execute()
    return {"data": result.data or []}


@router.get("/{product_id}")
async def get_product(product_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    result = db.table("products").select("*").eq("id", product_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return {"data": result.data}


@router.post("")
async def criar_product(body: ProductCreate, authorization: Optional[str] = Header(None)):
    """Create a new product (platform admin only)."""
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    # Check for duplicate slug
    existing = db.table("products").select("id").eq("slug", body.slug).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Já existe um produto com este slug")

    data = body.model_dump(exclude_none=True)
    data["ativo"] = True

    result = db.table("products").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar produto")

    logger.info(f"Product created: {body.nome}")
    return {"data": result.data[0]}


@router.patch("/{product_id}")
async def atualizar_product(
    product_id: str, body: ProductUpdate, authorization: Optional[str] = Header(None)
):
    """Update a product (platform admin only). Slug is immutable."""
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("products").update(data).eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    logger.info(f"Product updated: {product_id}")
    return {"data": result.data[0]}


@router.delete("/{product_id}")
async def desativar_product(product_id: str, authorization: Optional[str] = Header(None)):
    """Soft-delete a product by setting ativo = false (platform admin only)."""
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("products").update({"ativo": False}).eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    logger.info(f"Product deactivated: {product_id}")
    return {"data": result.data[0]}
