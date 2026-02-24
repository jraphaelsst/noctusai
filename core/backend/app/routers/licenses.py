"""
Licenses Router — Grant/revoke organization access to products.

GET    /api/licenses              — List licenses for current org
POST   /api/licenses              — Grant access (admin)
DELETE /api/licenses/{id}         — Revoke access (admin)
GET    /api/licenses/check/{slug} — Check if current org has access to product
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/licenses", tags=["Licenses"])


class LicenseGrant(BaseModel):
    org_id: str
    product_id: str


@router.get("")
async def listar_licenses(authorization: Optional[str] = Header(None)):
    """List active licenses for the current user's organization."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    org_id = profile.data["org_id"]
    result = db.table("licenses").select("*, products(*)").eq("org_id", org_id).execute()
    return {"data": result.data or []}


@router.post("")
async def grant_license(body: LicenseGrant, authorization: Optional[str] = Header(None)):
    """Grant a product license to an organization (platform admin)."""
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    data = {
        "org_id": body.org_id,
        "product_id": body.product_id,
        "status": "active",
    }
    result = db.table("licenses").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar licença")

    logger.info(f"License granted: org={body.org_id} product={body.product_id}")
    return {"data": result.data[0]}


@router.delete("/{license_id}")
async def revoke_license(license_id: str, authorization: Optional[str] = Header(None)):
    """Revoke a license (set status to revoked)."""
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("licenses").update(
        {"status": "revoked"}
    ).eq("id", license_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Licença não encontrada")

    logger.info(f"License revoked: {license_id}")
    return {"data": result.data[0]}


@router.get("/check/{product_slug}")
async def check_access(product_slug: str, authorization: Optional[str] = Header(None)):
    """Check if the current user's org has access to a product."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    org_id = profile.data["org_id"]

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
