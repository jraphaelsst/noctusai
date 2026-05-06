"""
Plans Router — Subscription plan definitions for NoctusAI.

GET    /api/plans          — List active plans (authenticated)
GET    /api/plans/{id}     — Plan details (authenticated)
POST   /api/plans          — Create plan (admin only)
PATCH  /api/plans/{id}     — Update plan (admin only)
DELETE /api/plans/{id}     — Soft delete plan (admin only)

Schema is defined in products/core/backend/migrations/001_noctusai_core.sql.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/plans", tags=["Plans"])


class PlanCreate(BaseModel):
    nome: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=50)
    descricao: Optional[str] = None
    price_monthly: float = Field(default=0, ge=0)
    price_yearly: float = Field(default=0, ge=0)
    max_users: int = Field(default=-1)
    max_products: int = Field(default=-1)
    features: dict = Field(default_factory=dict)
    is_custom: bool = False
    stripe_price_id_monthly: Optional[str] = None
    stripe_price_id_yearly: Optional[str] = None


class PlanUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=100)
    descricao: Optional[str] = None
    price_monthly: Optional[float] = Field(default=None, ge=0)
    price_yearly: Optional[float] = Field(default=None, ge=0)
    max_users: Optional[int] = None
    max_products: Optional[int] = None
    features: Optional[dict] = None
    is_custom: Optional[bool] = None
    stripe_price_id_monthly: Optional[str] = None
    stripe_price_id_yearly: Optional[str] = None


@router.get("")
async def listar_plans(authorization: Optional[str] = Header(None)):
    """List all active plans."""
    await get_current_user(authorization)
    db = get_admin_client()

    result = db.table("plans").select("*").eq("ativo", True).order("price_monthly").execute()
    return {"data": result.data or []}


@router.get("/{plan_id}")
async def get_plan(plan_id: str, authorization: Optional[str] = Header(None)):
    """Get plan details."""
    await get_current_user(authorization)
    db = get_admin_client()

    result = db.table("plans").select("*").eq("id", plan_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    return {"data": result.data}


@router.post("")
async def criar_plan(body: PlanCreate, authorization: Optional[str] = Header(None)):
    """Create a new plan (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    # Check for duplicate slug
    existing = db.table("plans").select("id").eq("slug", body.slug).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Já existe um plano com este slug")

    data = body.model_dump(exclude_none=True)
    data["ativo"] = True

    result = db.table("plans").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar plano")

    logger.info(f"Plan created: {body.nome}")
    return {"data": result.data[0]}


@router.patch("/{plan_id}")
async def atualizar_plan(plan_id: str, body: PlanUpdate, authorization: Optional[str] = Header(None)):
    """Update a plan (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("plans").update(data).eq("id", plan_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    logger.info(f"Plan updated: {plan_id}")
    return {"data": result.data[0]}


@router.delete("/{plan_id}")
async def deletar_plan(plan_id: str, authorization: Optional[str] = Header(None)):
    """Soft delete a plan (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("plans").update({"ativo": False}).eq("id", plan_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    logger.info(f"Plan deactivated: {plan_id}")
    return {"data": result.data[0]}
