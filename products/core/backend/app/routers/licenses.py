"""
Licenses Router — Grant/revoke organization access to products.

GET    /api/licenses              — List licenses for current org
GET    /api/licenses/all          — List ALL licenses (admin)
GET    /api/licenses/product/{id} — List licenses for a specific product (admin)
POST   /api/licenses              — Grant access (admin)
DELETE /api/licenses/{id}         — Revoke access (admin)
GET    /api/licenses/check/{slug} — Check if current org has access to product
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin, get_org_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/licenses", tags=["Licenses"])


class LicenseGrant(BaseModel):
    org_id: str
    product_id: str
    fim: Optional[str] = None  # ISO 8601 datetime, null = perpetual


@router.get("")
async def listar_licenses(authorization: Optional[str] = Header(None)):
    """List active licenses for the current user's organization."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    result = db.table("licenses").select("*, products(*)").eq("org_id", org_id).order("fim", nullsfirst=True).order("created_at", desc=True).execute()
    return {"data": result.data or []}


@router.get("/all")
async def listar_all_licenses(authorization: Optional[str] = Header(None)):
    """List ALL licenses with joined product/org data (platform admin only)."""
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("licenses").select("*, products(*), organizations(*)").order("fim", nullsfirst=True).order("created_at", desc=True).execute()
    return {"data": result.data or []}


@router.get("/product/{product_id}")
async def listar_licenses_por_produto(product_id: str, authorization: Optional[str] = Header(None)):
    """List licenses for a specific product (platform admin only)."""
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("licenses").select("*, products(*), organizations(*)").eq("product_id", product_id).order("fim", nullsfirst=True).order("created_at", desc=True).execute()
    return {"data": result.data or []}


@router.post("")
async def grant_license(body: LicenseGrant, authorization: Optional[str] = Header(None)):
    """Grant a product license to an organization (platform admin).

    Always inserts a new license record. Revoked/expired records are preserved
    as history. The partial unique index prevents duplicate active licenses.
    Requires migration 003_license_history.sql to have been applied.
    """
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    # Check for an existing ACTIVE license (prevent duplicates)
    existing = db.table("licenses").select("id").eq(
        "org_id", body.org_id
    ).eq("product_id", body.product_id).eq("status", "active").execute()

    if existing.data:
        raise HTTPException(status_code=409, detail="Esta organização já possui uma licença ativa para este produto")

    data = {
        "org_id": body.org_id,
        "product_id": body.product_id,
        "status": "active",
    }
    if body.fim:
        data["fim"] = body.fim
    result = db.table("licenses").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar licença")

    logger.info(f"License granted: org={body.org_id} product={body.product_id}")

    # Audit log, notification, and webhook (best-effort)
    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=user.id, org_id=body.org_id,
            action="grant", resource_type="license",
            resource_id=result.data[0]["id"],
        )
    except Exception:
        pass
    try:
        from app.services import notification_service
        await notification_service.notify_team(
            org_id=body.org_id,
            type="system",
            title="Licença concedida",
            message=f"Uma nova licença de produto foi ativada para sua organização.",
        )
    except Exception:
        pass
    try:
        from app.services import webhook_delivery
        await webhook_delivery.dispatch(
            org_id=body.org_id,
            event_type="license.granted",
            payload={"license_id": result.data[0]["id"], "product_id": body.product_id},
        )
    except Exception:
        pass

    return {"data": result.data[0]}


@router.delete("/{license_id}")
async def revoke_license(license_id: str, authorization: Optional[str] = Header(None)):
    """Revoke a license (set status to revoked)."""
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("licenses").update(
        {"status": "revoked", "fim": datetime.now(timezone.utc).isoformat()}
    ).eq("id", license_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Licença não encontrada")

    logger.info(f"License revoked: {license_id}")

    revoked_record = result.data[0]

    # Flush cached SSO sessions so users feel the revocation within the next
    # JWT refresh cycle, not at the end of the 5-min cache TTL.
    # compliance-audit-reconciliation Phase 6 (finding 9).
    try:
        from app.routers.sso import invalidate_sso_cache_for_org
        org_id_val = revoked_record.get("org_id")
        if org_id_val:
            invalidate_sso_cache_for_org(db, org_id_val)
    except Exception as exc:
        logger.warning("SSO cache invalidation after license revoke failed: %s", exc)

    # Audit log and webhook (best-effort)
    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=user.id, org_id=revoked_record.get("org_id"),
            action="revoke", resource_type="license", resource_id=license_id,
        )
    except Exception:
        pass
    try:
        from app.services import webhook_delivery
        org_id_val = revoked_record.get("org_id")
        if org_id_val:
            await webhook_delivery.dispatch(
                org_id=org_id_val,
                event_type="license.revoked",
                payload={"license_id": license_id},
            )
    except Exception:
        pass

    return {"data": revoked_record}


@router.get("/check/{product_slug}")
async def check_access(product_slug: str, authorization: Optional[str] = Header(None)):
    """Check if the current user's org has access to a product."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    # Find product by slug
    product = db.table("products").select("id").eq("slug", product_slug).single().execute()
    if not product.data:
        return {"has_access": False, "reason": "Produto não encontrado"}

    # Check license
    license_check = db.table("licenses").select("id, status").eq(
        "org_id", org_id
    ).eq("product_id", product.data["id"]).eq("status", "active").execute()

    has_access = bool(license_check.data)
    return {"has_access": has_access, "org_id": org_id, "product_slug": product_slug}
