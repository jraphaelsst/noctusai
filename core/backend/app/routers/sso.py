"""
SSO Router — Generate and validate SSO tokens for cross-product authentication.

POST  /api/sso/token           — Generate SSO token for a product
POST  /api/sso/validate        — Validate SSO token (called by products)
GET   /api/sso/launch/{slug}   — Redirect to product with SSO token
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.database import get_admin_client
from app.dependencies import get_current_user, create_sso_token, verify_sso_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sso", tags=["SSO"])


class SSOTokenRequest(BaseModel):
    product_slug: str


class SSOValidateRequest(BaseModel):
    token: str


@router.post("/token")
async def generate_sso_token(body: SSOTokenRequest, authorization: Optional[str] = Header(None)):
    """Generate a short-lived SSO token to access a product."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Get user profile
    profile = db.table("noctus_users").select("*").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    org_id = profile.data["org_id"]
    role = profile.data.get("role", "user")

    # Check if org has access to product
    product = db.table("products").select("id, slug").eq("slug", body.product_slug).single().execute()
    if not product.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    license_check = db.table("licenses").select("id").eq(
        "org_id", org_id
    ).eq("product_id", product.data["id"]).eq("status", "active").execute()

    if not license_check.data:
        raise HTTPException(status_code=403, detail="Organização não tem acesso a este produto")

    # Generate SSO token
    sso_token = create_sso_token(
        user_id=user.id,
        org_id=org_id,
        product_slug=body.product_slug,
        email=user.email,
        role=role,
    )

    logger.info(f"SSO token generated for user={user.id} product={body.product_slug}")
    return {"sso_token": sso_token, "product_slug": body.product_slug}


@router.post("/validate")
async def validate_sso_token(body: SSOValidateRequest):
    """Validate an SSO token. Called by products to verify user access."""
    payload = verify_sso_token(body.token)
    return {
        "valid": True,
        "user_id": payload["sub"],
        "org_id": payload["org_id"],
        "product": payload["product"],
        "email": payload["email"],
        "role": payload["role"],
    }


@router.get("/launch/{product_slug}")
async def launch_product(product_slug: str, authorization: Optional[str] = Header(None)):
    """Generate SSO token and redirect to the product URL."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Get user profile
    profile = db.table("noctus_users").select("org_id, role").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    org_id = profile.data["org_id"]
    role = profile.data.get("role", "user")

    # Get product
    product = db.table("products").select("*").eq("slug", product_slug).single().execute()
    if not product.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    # Check license
    license_check = db.table("licenses").select("id").eq(
        "org_id", org_id
    ).eq("product_id", product.data["id"]).eq("status", "active").execute()

    if not license_check.data:
        raise HTTPException(status_code=403, detail="Sem acesso a este produto")

    # Generate SSO token
    sso_token = create_sso_token(
        user_id=user.id,
        org_id=org_id,
        product_slug=product_slug,
        email=user.email,
        role=role,
    )

    # Redirect to product with token
    redirect_url = f"{product.data['url_base']}/sso?token={sso_token}"
    return RedirectResponse(url=redirect_url, status_code=302)
