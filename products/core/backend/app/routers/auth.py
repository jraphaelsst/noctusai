"""
Auth Router — Login, Signup, Session for NoctusAI.

POST  /api/auth/signup   — Register new user + org
POST  /api/auth/login    — Email/password login
GET   /api/auth/me       — Get current user profile + org
POST  /api/auth/logout   — Invalidate session
"""
import logging
import re
import uuid
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Request

from supabase import create_client
from app.config import settings
from app.database import get_admin_client
from app.dependencies import get_current_user
from app.rate_limit import limiter
from app.schemas.auth import SignupRequest, LoginRequest, ProfileUpdate, PasswordChange, RefreshRequest
from noctusai_lib.config.product_urls import resolve_product_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])

_SLUG_PREFIX = {"individual": "indv", "company": "comp"}


def _slugify(text: str) -> str:
    """Generate a URL-safe slug from text (max 44 chars, leaving room for prefix_)."""
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug[:44]


def _make_org_slug(base_name: str, org_type: str) -> str:
    """Build a prefixed slug: 'indv_<base>' or 'comp_<base>'."""
    prefix = _SLUG_PREFIX.get(org_type, "indv")
    base = _slugify(base_name)
    return f"{prefix}_{base}"


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

    # 2. Create organization with org_type, number_of_users, and prefixed slug.
    #    Slug format: 'indv_<base>' for individuals, 'comp_<base>' for companies.
    org_type = body.org_type
    number_of_users = body.number_of_users
    slug = _make_org_slug(body.empresa.strip(), org_type)
    existing_slug = db.table("organizations").select("id").eq("slug", slug).execute()
    if existing_slug.data:
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    org_data = {
        "nome": body.empresa.strip(),
        "slug": slug,
        "plano": "free",
        "owner_id": user.id,
        "category": "normal",
        "org_type": org_type,
        "number_of_users": number_of_users,
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
        logger.warning(
            "auth: user_metadata sync failed for user_id=%s (%s); request continues",
            user.id, e,
        )

    # Log signup with user_id (UUID), not email — emails are LGPD personal data.
    logger.info("auth: new signup user_id=%s org_id=%s", user.id, org["id"])

    # Audit log and welcome email (best-effort)
    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=user.id, org_id=org["id"],
            action="signup", resource_type="user", resource_id=user.id,
            request=request,
        )
    except Exception as exc:
        logger.warning("auth: signup audit log failed for user_id=%s (%s); request continues", user.id, exc)
    try:
        from app.services.email_service import send_welcome_email
        send_welcome_email(to=body.email, user_name=body.nome.strip().title(), org_name=org["nome"])
    except Exception as exc:
        # Log user_id (UUID), NOT body.email — emails are LGPD personal data
        # and shouldn't persist in operator log streams. Same rule as the
        # surrounding audit-log warnings (which all use user_id=%s).
        logger.warning("auth: welcome email send failed for user_id=%s (%s); request continues", user.id, exc)

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
        except Exception as exc:
            logger.warning("auth: login audit log failed for user_id=%s (%s); login proceeds", response.user.id, exc)

        # Enforce concurrent session cap (best-effort)
        try:
            admin_db = get_admin_client()
            admin_db.rpc("enforce_session_cap", {"p_user_id": str(response.user.id)}).execute()
        except Exception as exc:
            logger.warning("auth: enforce_session_cap RPC failed for user_id=%s (%s); login proceeds", response.user.id, exc)

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

    # Get licensed products for this org (checks expiry)
    from app.dependencies import get_licensed_product_ids
    licensed_product_ids = get_licensed_product_ids(db, org_id)

    # Get all products (for the marketplace view).
    #
    # Platform admins ALSO see inactive products, so they can reactivate one
    # straight from the dashboard card instead of having to open the admin
    # panel. Everyone else sees only active products — an inactive product is
    # one we have agreed not to work on, and it must not appear in a normal
    # user's marketplace.
    #
    # `role` comes from the profile already loaded above (the same field the
    # frontend derives `isAdmin` from), so this costs no extra query and
    # cannot disagree with the client's own view of who is an admin.
    is_platform_admin = profile.get("role") == "admin"
    products_query = db.table("products").select("*")
    if not is_platform_admin:
        products_query = products_query.eq("ativo", True)
    all_products = products_query.order("nome").execute()

    # Resolve url_base through the seed-side resolver so each product's
    # frontend URL adapts to the deploy environment (env-driven) without
    # rewriting public.products rows. Empty / missing resolution surfaces
    # as a logged warning; the row keeps its DB url_base as the dashboard
    # tile's last-resort destination — the dashboard must render even when
    # one product's URL config is gappy.
    products_with_access = []
    for product in (all_products.data or []):
        try:
            resolved_url = resolve_product_url(
                product["slug"],
                db_url_base=product.get("url_base"),
            )
        except ValueError as exc:
            logger.warning(
                "url_base resolution failed for product slug=%s: %s",
                product.get("slug"), exc,
            )
            resolved_url = product.get("url_base") or ""
        products_with_access.append({
            **product,
            "url_base": resolved_url,
            "has_access": product["id"] in licensed_product_ids,
        })

    return {
        "user": profile,
        "organization": org_result.data if org_result.data else None,
        "products": products_with_access,
    }


@router.post("/change-password")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    body: PasswordChange,
    authorization: Optional[str] = Header(None),
):
    """Change the current user's password."""
    user, token = await get_current_user(authorization)

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 8 caracteres")

    db = get_admin_client()
    try:
        db.auth.admin.update_user_by_id(user.id, {"password": body.new_password})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Revoke all other sessions for this user (best-effort)
    try:
        db.auth.admin.sign_out(str(user.id), scope="others")
    except Exception as exc:
        logger.warning("auth: sign_out other sessions failed for user_id=%s (%s); password change proceeds", user.id, exc)

    # Audit log (best-effort)
    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=str(user.id), org_id=None,
            action="password_change", resource_type="user", resource_id=str(user.id),
            request=request,
        )
    except Exception as exc:
        logger.warning("auth: password-change audit log failed for user_id=%s (%s)", user.id, exc)

    return {"ok": True, "message": "Senha atualizada com sucesso"}


@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh_token(request: Request, body: RefreshRequest):
    """Exchange a refresh token for a new access token."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        response = client.auth.refresh_session(body.refresh_token)
        if not response.session:
            raise HTTPException(status_code=401, detail="Refresh token inválido")

        # Update last_active_at (best-effort)
        if response.user:
            try:
                admin_db = get_admin_client()
                admin_db.table("noctus_users").update(
                    {"last_active_at": "now()"}
                ).eq("id", str(response.user.id)).execute()
            except Exception as exc:
                logger.warning("auth: last_active_at update failed for user_id=%s (%s); refresh proceeds", response.user.id, exc)

            # Audit log (best-effort)
            try:
                from app.services import audit_service
                await audit_service.log(
                    user_id=str(response.user.id), org_id=None,
                    action="token_refresh", resource_type="user",
                    resource_id=str(response.user.id),
                    request=request,
                )
            except Exception as exc:
                logger.warning("auth: token-refresh audit log failed for user_id=%s (%s)", response.user.id, exc)

        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Falha ao renovar token")


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
    except Exception as exc:
        logger.warning("auth: client.sign_out() failed for user_id=%s (%s); logout still returns ok", user.id, exc)
    return {"ok": True}
