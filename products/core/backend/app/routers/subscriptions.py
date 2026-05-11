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

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin, get_org_id
from app.schemas.subscriptions import SubscriptionCreate, SubscriptionUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/subscriptions", tags=["Subscriptions"])


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
    org_id = await get_org_id(user)
    db = get_admin_client()

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
    user, token = await get_current_admin(authorization)
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

    # Audit log, notification, and webhook (best-effort)
    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=user.id, org_id=body.org_id,
            action="create", resource_type="subscription",
            resource_id=result.data[0]["id"],
        )
    except Exception as exc:
        logger.warning("subscriptions: create audit log failed for sub_id=%s (%s); creation succeeded", result.data[0]["id"], exc)
    try:
        from app.services import notification_service
        await notification_service.notify_team(
            org_id=body.org_id,
            type="subscription_change",
            title="Assinatura criada",
            message="Uma nova assinatura foi ativada para sua organização.",
        )
    except Exception as exc:
        logger.warning("subscriptions: team notification on create failed for org=%s (%s); creation succeeded", body.org_id, exc)
    try:
        from app.services import webhook_delivery
        await webhook_delivery.dispatch(
            org_id=body.org_id,
            event_type="subscription.created",
            payload={"subscription_id": result.data[0]["id"], "plan_id": body.plan_id, "status": body.status},
        )
    except Exception as exc:
        logger.warning("subscriptions: webhook dispatch on create failed for org=%s (%s); creation succeeded", body.org_id, exc)

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

    # Audit log and webhook (best-effort)
    updated_record = result.data[0]
    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=None, org_id=updated_record.get("org_id"),
            action="update", resource_type="subscription",
            resource_id=subscription_id,
        )
    except Exception as exc:
        logger.warning("subscriptions: update audit log failed for sub_id=%s (%s); update succeeded", subscription_id, exc)
    try:
        from app.services import webhook_delivery
        org_id_val = updated_record.get("org_id")
        if org_id_val:
            await webhook_delivery.dispatch(
                org_id=org_id_val,
                event_type="subscription.updated",
                payload={"subscription_id": subscription_id, "status": updated_record.get("status")},
            )
    except Exception as exc:
        logger.warning("subscriptions: webhook dispatch on update failed for sub_id=%s (%s); update succeeded", subscription_id, exc)

    return {"data": updated_record}


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
