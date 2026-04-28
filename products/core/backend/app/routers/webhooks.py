"""
Webhooks Router — Manage webhook endpoints and view delivery logs.

GET    /api/webhooks                   — List webhook endpoints for current org
POST   /api/webhooks                   — Create a new webhook endpoint
PATCH  /api/webhooks/{id}              — Update a webhook endpoint
DELETE /api/webhooks/{id}              — Delete a webhook endpoint
GET    /api/webhooks/{id}/deliveries   — List delivery log for an endpoint

-- Supabase SQL for webhook tables:
--
-- CREATE TABLE webhook_endpoints (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL REFERENCES organizations(id),
--   url text NOT NULL,
--   secret text NOT NULL,
--   events text[] NOT NULL DEFAULT '{}',
--   is_active boolean NOT NULL DEFAULT true,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE TABLE webhook_deliveries (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   endpoint_id uuid NOT NULL REFERENCES webhook_endpoints(id),
--   event_type text NOT NULL,
--   payload jsonb NOT NULL,
--   response_status int,
--   response_body text,
--   attempts int NOT NULL DEFAULT 0,
--   status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed')),
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import secrets
import logging
from typing import Optional, List
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin, get_org_id
from app.services import webhook_delivery, webhook_retention_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


class WebhookCreate(BaseModel):
    url: str = Field(..., max_length=500)
    events: List[str] = Field(default_factory=list)
    is_active: bool = True


class WebhookUpdate(BaseModel):
    url: Optional[str] = Field(default=None, max_length=500)
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None


def _generate_webhook_secret() -> str:
    """Generate a secure webhook signing secret."""
    return f"whsec_{secrets.token_urlsafe(32)}"


@router.get("")
async def listar_webhooks(authorization: Optional[str] = Header(None)):
    """List webhook endpoints for the current user's organization."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    result = db.table("webhook_endpoints").select("*").eq(
        "org_id", org_id
    ).order("created_at", desc=True).execute()

    return {"data": result.data or []}


@router.post("")
async def criar_webhook(body: WebhookCreate, authorization: Optional[str] = Header(None)):
    """Create a new webhook endpoint. Returns the signing secret ONCE."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    webhook_secret = _generate_webhook_secret()

    data = {
        "org_id": org_id,
        "url": body.url,
        "secret": webhook_secret,
        "events": body.events,
        "is_active": body.is_active,
    }

    result = db.table("webhook_endpoints").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar webhook endpoint")

    logger.info(f"Webhook endpoint created: org={org_id} url={body.url}")

    # Include the secret in the response (only returned once)
    response_data = result.data[0].copy()
    response_data["signing_secret"] = webhook_secret
    return {"data": response_data}


@router.patch("/{webhook_id}")
async def atualizar_webhook(
    webhook_id: str,
    body: WebhookUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update a webhook endpoint."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Only update webhooks belonging to the user's org
    result = db.table("webhook_endpoints").update(update_data).eq(
        "id", webhook_id
    ).eq("org_id", org_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Webhook endpoint não encontrado")

    logger.info(f"Webhook endpoint updated: {webhook_id}")
    return {"data": result.data[0]}


@router.delete("/{webhook_id}")
async def deletar_webhook(webhook_id: str, authorization: Optional[str] = Header(None)):
    """Delete a webhook endpoint."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    # Only delete webhooks belonging to the user's org
    result = db.table("webhook_endpoints").delete().eq(
        "id", webhook_id
    ).eq("org_id", org_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Webhook endpoint não encontrado")

    logger.info(f"Webhook endpoint deleted: {webhook_id}")
    return {"data": {"deleted": True, "id": webhook_id}}


@router.get("/{webhook_id}/deliveries")
async def listar_deliveries(
    webhook_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    authorization: Optional[str] = Header(None),
):
    """List delivery log for a webhook endpoint."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    # Verify the endpoint belongs to the user's org
    endpoint = db.table("webhook_endpoints").select("id").eq(
        "id", webhook_id
    ).eq("org_id", org_id).execute()

    if not endpoint.data:
        raise HTTPException(status_code=404, detail="Webhook endpoint não encontrado")

    offset = (page - 1) * page_size

    # Get total count
    count_result = db.table("webhook_deliveries").select(
        "id", count="exact"
    ).eq("endpoint_id", webhook_id).execute()
    total = count_result.count if count_result.count is not None else len(count_result.data or [])

    # Get paginated deliveries
    result = db.table("webhook_deliveries").select("*").eq(
        "endpoint_id", webhook_id
    ).order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    return {
        "data": result.data or [],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/deliveries/{delivery_id}/retry")
async def retry_webhook_delivery(
    delivery_id: str,
    authorization: Optional[str] = Header(None),
):
    """Retry a failed webhook delivery. Admin-only."""
    await get_current_admin(authorization)

    try:
        result = await webhook_delivery.retry_delivery(delivery_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    logger.info(f"Webhook delivery retried: {delivery_id}")
    return {"data": result}


@router.post("/deliveries/purge-expired")
async def purge_expired_webhook_deliveries(
    authorization: Optional[str] = Header(None),
):
    """Purge webhook deliveries past their retention window (platform_admin).

    compliance-audit-reconciliation Phase 6 (finding 8 — LGPD minimization).
    Rows default to 30-day retention per service-level policy. Meant to be
    superseded by a scheduler (`core-scheduler-for-retention`). Idempotent.
    """
    await get_current_admin(authorization)
    db = get_admin_client()
    result = webhook_retention_service.run_retention_sweep(db)
    return {"data": result}
