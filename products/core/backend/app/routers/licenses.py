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
from typing import Optional
from fastapi import APIRouter, Header, HTTPException

from app.database import get_admin_client
from app.services import license_service
from app.dependencies import get_current_user, get_current_admin, get_org_id
from app.schemas.licenses import LicenseGrant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/licenses", tags=["Licenses"])


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

    Always inserts a new `source='manual'` record; revoked/expired records
    are preserved as history. The partial unique index prevents duplicate
    active licenses. Writes + side effects live in `license_service`.
    """
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    try:
        result = license_service.grant_license(
            db,
            org_id=body.org_id,
            product_id=body.product_id,
            source="manual",
            fim=body.fim,
        )
    except license_service.LicenseConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("licenses: grant failed for org=%s product=%s: %s", body.org_id, body.product_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao criar licença") from exc

    await license_service.announce_grant(actor_user_id=user.id, license_row=result.license)
    return {"data": result.license}


@router.delete("/{license_id}")
async def revoke_license(license_id: str, authorization: Optional[str] = Header(None)):
    """Revoke a license (set status to revoked). Admin action — any source."""
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    revoked_record = license_service.revoke_license(db, license_id)
    if revoked_record is None:
        raise HTTPException(status_code=404, detail="Licença não encontrada")

    await license_service.announce_revoke(actor_user_id=user.id, license_row=revoked_record)
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
