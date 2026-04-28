"""
Test Accounts Router — Admin-only management of test organizations.

POST   /api/admin/test-accounts           — Create test org + user
GET    /api/admin/test-accounts           — List test organizations
DELETE /api/admin/test-accounts/{org_id}  — Deactivate test org

Test organizations receive:
  - category: "test" on the organizations table
  - All product licenses auto-granted
  - Unlimited subscription (no expiry)

-- Supabase SQL to add category column to organizations:
--
-- ALTER TABLE organizations ADD COLUMN category text NOT NULL DEFAULT 'normal'
--   CHECK (category IN ('normal', 'test'));

NOTE: The billing router (billing.py) should check organization.category == 'test'
and block checkout/payment flows for test organizations. Test orgs bypass billing entirely.
"""
import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.database import get_admin_client
from app.dependencies import get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/test-accounts", tags=["Test Accounts"])


class TestAccountCreate(BaseModel):
    nome: str = Field(..., max_length=200, description="Nome do usuário de teste")
    email: str = Field(..., description="Email do usuário de teste")
    password: str = Field(..., min_length=6, description="Senha do usuário de teste")
    empresa: str = Field(..., max_length=200, description="Nome da organização de teste")


@router.post("")
async def criar_test_account(body: TestAccountCreate, authorization: Optional[str] = Header(None)):
    """Create a test organization with a user, auto-grant all licenses, and unlimited subscription."""
    await get_current_admin(authorization)
    db = get_admin_client()

    # 1. Create Supabase auth user
    try:
        auth_response = db.auth.admin.create_user({
            "email": body.email,
            "password": body.password,
            "email_confirm": True,
        })
        user = auth_response.user
        if not user:
            raise HTTPException(status_code=400, detail="Erro ao criar usuário de teste")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro no cadastro: {str(e)}")

    # 2. Create test organization (append suffix if slug already taken)
    base_slug = body.empresa.strip().lower().replace(" ", "-")
    slug = base_slug
    existing_slug = db.table("organizations").select("id").eq("slug", slug).execute()
    if existing_slug.data:
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"

    org_data = {
        "nome": body.empresa.strip(),
        "slug": slug,
        "plano": "free",
        "owner_id": user.id,
        "category": "test",
    }
    org_result = db.table("organizations").insert(org_data).execute()
    if not org_result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar organização de teste")
    org = org_result.data[0]

    # 3. Create user profile linked to org
    profile_data = {
        "id": user.id,
        "email": body.email,
        "nome": body.nome.strip().title(),
        "org_id": org["id"],
        "role": "admin",  # Test account user is admin of their org
        "org_role": "owner",  # Org creator is owner of their org
    }
    db.table("noctus_users").insert(profile_data).execute()

    # 4. Auto-grant all active product licenses (skip if already active)
    all_products = db.table("products").select("id").eq("ativo", True).execute()
    licenses_created = 0
    for product in (all_products.data or []):
        existing = db.table("licenses").select("id").eq(
            "org_id", org["id"]
        ).eq("product_id", product["id"]).eq("status", "active").execute()
        if existing.data:
            continue
        db.table("licenses").insert({
            "org_id": org["id"],
            "product_id": product["id"],
            "status": "active",
        }).execute()
        licenses_created += 1

    # 5. Create unlimited subscription (find or use the highest plan)
    plans_result = db.table("plans").select("id").eq("is_active", True).order(
        "price_monthly", desc=True
    ).execute()
    if plans_result.data:
        sub_data = {
            "org_id": org["id"],
            "plan_id": plans_result.data[0]["id"],
            "status": "active",
            "metadata": {"test_account": True, "unlimited": True},
        }
        db.table("subscriptions").insert(sub_data).execute()

    logger.info(f"Test account created: {body.email} → org '{org['nome']}' (id={org['id']}), {licenses_created} licenses granted")
    return {
        "data": {
            "user_id": user.id,
            "org_id": org["id"],
            "org_nome": org["nome"],
            "category": "test",
            "licenses_granted": licenses_created,
        }
    }


@router.get("")
async def listar_test_accounts(authorization: Optional[str] = Header(None)):
    """List all test organizations."""
    await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("organizations").select("*").eq("category", "test").order("created_at", desc=True).execute()
    return {"data": result.data or []}


@router.delete("/{org_id}")
async def desativar_test_account(org_id: str, authorization: Optional[str] = Header(None)):
    """Deactivate a test organization: revoke licenses, cancel subscription, set category to 'normal'."""
    await get_current_admin(authorization)
    db = get_admin_client()

    # Verify org exists and is a test org
    org = db.table("organizations").select("id, category").eq("id", org_id).single().execute()
    if not org.data:
        raise HTTPException(status_code=404, detail="Organização não encontrada")
    if org.data.get("category") != "test":
        raise HTTPException(status_code=400, detail="Esta organização não é uma conta de teste")

    # Revoke all active licenses
    db.table("licenses").update({"status": "revoked"}).eq("org_id", org_id).eq("status", "active").execute()

    # Cancel active subscriptions
    db.table("subscriptions").update({"status": "canceled"}).eq("org_id", org_id).eq("status", "active").execute()

    # Mark org as deactivated (set plano to 'disabled' to prevent access)
    db.table("organizations").update({
        "category": "normal",
        "plano": "disabled",
    }).eq("id", org_id).execute()

    logger.info(f"Test account deactivated: org_id={org_id}")
    return {"data": {"org_id": org_id, "status": "deactivated"}}
