"""
Subscriptions Router — Manage organization subscriptions to plans.

GET    /api/subscriptions           — List all subscriptions (admin only)
GET    /api/subscriptions/me        — Current user's org subscription
GET    /api/subscriptions/org/{id}  — Get org's subscription
POST   /api/subscriptions           — Create/assign subscription (admin only)
PATCH  /api/subscriptions/{id}      — Update subscription (admin only)
DELETE /api/subscriptions/{id}      — Cancel subscription (admin only)

-- Supabase SQL to create the subscriptions table:
--
-- CREATE TABLE subscriptions (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL REFERENCES organizations(id),
--   plan_id uuid NOT NULL REFERENCES plans(id),
--   status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'canceled', 'expired', 'trial')),
--   started_at timestamptz NOT NULL DEFAULT now(),
--   expires_at timestamptz,
--   canceled_at timestamptz,
--   stripe_subscription_id text,
--   stripe_customer_id text,
--   metadata jsonb NOT NULL DEFAULT '{}',
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
--
-- ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "subscriptions_read_own" ON subscriptions FOR SELECT TO authenticated
--   USING (org_id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid()));
-- CREATE POLICY "subscriptions_admin_all" ON subscriptions FOR ALL USING (
--   auth.uid() IN (SELECT id FROM noctus_users WHERE role = 'admin')
-- );
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/subscriptions", tags=["Subscriptions"])


class SubscriptionCreate(BaseModel):
    org_id: str
    plan_id: str
    status: str = Field(default="active", pattern="^(active|canceled|expired|trial)$")
    expires_at: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class SubscriptionUpdate(BaseModel):
    plan_id: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(active|canceled|expired|trial)$")
    expires_at: Optional[str] = None
    canceled_at: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    metadata: Optional[dict] = None


@router.get("")
async def listar_subscriptions(authorization: Optional[str] = Header(None)):
    """List all subscriptions (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("subscriptions").select(
        "*, organizations(id, nome, slug), plans(id, name, slug)"
    ).order("created_at", desc=True).execute()
    return {"data": result.data or []}


@router.get("/me")
async def get_my_subscription(authorization: Optional[str] = Header(None)):
    """Get the current user's organization subscription."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    org_id = profile.data["org_id"]
    result = db.table("subscriptions").select(
        "*, plans(*)"
    ).eq("org_id", org_id).eq("status", "active").execute()

    subscription = result.data[0] if result.data else None
    return {"data": subscription}


@router.get("/org/{org_id}")
async def get_org_subscription(org_id: str, authorization: Optional[str] = Header(None)):
    """Get a specific org's subscription (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("subscriptions").select(
        "*, plans(*)"
    ).eq("org_id", org_id).order("created_at", desc=True).execute()
    return {"data": result.data or []}


@router.post("")
async def criar_subscription(body: SubscriptionCreate, authorization: Optional[str] = Header(None)):
    """Create/assign a subscription to an org (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    # Verify org exists
    org = db.table("organizations").select("id").eq("id", body.org_id).single().execute()
    if not org.data:
        raise HTTPException(status_code=404, detail="Organização não encontrada")

    # Verify plan exists
    plan = db.table("plans").select("id").eq("id", body.plan_id).single().execute()
    if not plan.data:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    data = body.model_dump(exclude_none=True)
    result = db.table("subscriptions").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar assinatura")

    logger.info(f"Subscription created: org={body.org_id} plan={body.plan_id}")
    return {"data": result.data[0]}


@router.patch("/{subscription_id}")
async def atualizar_subscription(
    subscription_id: str, body: SubscriptionUpdate,
    authorization: Optional[str] = Header(None)
):
    """Update a subscription (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("subscriptions").update(data).eq("id", subscription_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada")

    logger.info(f"Subscription updated: {subscription_id}")
    return {"data": result.data[0]}


@router.delete("/{subscription_id}")
async def cancelar_subscription(subscription_id: str, authorization: Optional[str] = Header(None)):
    """Cancel a subscription (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("subscriptions").update({
        "status": "canceled",
    }).eq("id", subscription_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada")

    logger.info(f"Subscription canceled: {subscription_id}")
    return {"data": result.data[0]}
