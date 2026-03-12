"""
Auth Router — Login, Signup, Session for NoctusAI.

POST  /api/auth/signup   — Register new user + org
POST  /api/auth/login    — Email/password login
GET   /api/auth/me       — Get current user profile + org
POST  /api/auth/logout   — Invalidate session
"""
import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, EmailStr

from supabase import create_client
from app.config import settings
from app.database import get_admin_client
from app.dependencies import get_current_user
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])


class SignupRequest(BaseModel):
    nome: str
    email: str
    password: str
    empresa: str  # Organization name


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/signup")
@limiter.limit("10/minute")
async def signup(request: Request, body: SignupRequest):
    """Register a new user and create their organization."""
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
            raise HTTPException(status_code=400, detail="Erro ao criar usuário")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro no cadastro: {str(e)}")

    # 2. Create organization (append suffix if slug already taken)
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
        "category": "normal",
    }
    org_result = db.table("organizations").insert(org_data).execute()
    if not org_result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar organização")
    org = org_result.data[0]

    # 3. Create user profile linked to org
    profile_data = {
        "id": user.id,
        "email": body.email,
        "nome": body.nome.strip().title(),
        "org_id": org["id"],
        "role": "user",
        "org_role": "owner",  # Org creator is owner of their org
    }
    db.table("noctus_users").insert(profile_data).execute()

    # 4. Sync org_id to auth user_metadata so product backends can read it
    try:
        db.auth.admin.update_user_by_id(user.id, {"user_metadata": {"org_id": org["id"]}})
    except Exception as e:
        logger.warning(f"Failed to sync org_id to user_metadata: {e}")

    logger.info(f"New signup: {body.email} → org {org['nome']}")

    # Audit log and welcome email (best-effort)
    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=user.id, org_id=org["id"],
            action="signup", resource_type="user", resource_id=user.id,
            request=request,
        )
    except Exception:
        pass
    try:
        from app.services.email_service import send_welcome_email
        send_welcome_email(to=body.email, user_name=body.nome.strip().title(), org_name=org["nome"])
    except Exception:
        pass

    return {"data": {"user_id": user.id, "org_id": org["id"]}}


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest):
    """Login with email/password. Returns Supabase session."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        response = client.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })
        if not response.session:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        # Audit log (best-effort)
        try:
            from app.services import audit_service
            await audit_service.log(
                user_id=str(response.user.id), org_id=None,
                action="login", resource_type="user", resource_id=str(response.user.id),
                request=request,
            )
        except Exception:
            pass

        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user": {
                "id": response.user.id,
                "email": response.user.email,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="Email ou senha incorretos")


@router.get("/me")
async def get_me(authorization: Optional[str] = Header(None)):
    """Get current user profile with organization and licensed products."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Get noctus user profile
    profile_result = db.table("noctus_users").select("*").eq("id", user.id).single().execute()
    if not profile_result.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    profile = profile_result.data
    org_id = profile.get("org_id")

    # Get organization
    org_result = db.table("organizations").select("*").eq("id", org_id).single().execute()

    # Get licensed products for this org
    licenses_result = db.table("licenses").select(
        "*, products(*)"
    ).eq("org_id", org_id).eq("status", "active").execute()

    licensed_product_ids = [
        lic["product_id"] for lic in (licenses_result.data or [])
    ]

    # Get all products (for the marketplace view)
    all_products = db.table("products").select("*").eq("ativo", True).order("nome").execute()

    products_with_access = []
    for product in (all_products.data or []):
        products_with_access.append({
            **product,
            "has_access": product["id"] in licensed_product_ids,
        })

    return {
        "user": profile,
        "organization": org_result.data if org_result.data else None,
        "products": products_with_access,
    }


class ProfileUpdate(BaseModel):
    nome: Optional[str] = None
    avatar_url: Optional[str] = None


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update the current user's profile (name, avatar)."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("noctus_users").update(update_data).eq("id", user.id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    return {"data": result.data[0]}


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Sign out the current user."""
    user, token = await get_current_user(authorization)
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        client.auth.sign_out()
    except Exception:
        pass
    return {"ok": True}
