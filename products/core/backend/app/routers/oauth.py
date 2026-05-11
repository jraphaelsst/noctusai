"""
OAuth Router — Handle OAuth/Social login flows for NoctusAI.

POST /api/auth/oauth/callback    — Handle OAuth callback, create/link user profile
GET  /api/auth/oauth/providers    — List available OAuth providers

The OAuth flow uses Supabase's built-in OAuth:
1. Frontend initiates OAuth via redirect to Supabase OAuth URL
2. Supabase handles the redirect flow with the provider
3. On success, Supabase redirects back with access_token in URL hash
4. Frontend extracts token, calls /api/auth/oauth/callback to ensure noctus_users profile exists
5. If new user, creates organization and profile (like signup)
"""
import logging
import re
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings
from app.database import get_admin_client, get_supabase_client
from app.dependencies import get_current_user
from app.rate_limit import limiter
from app.schemas.oauth import OAuthCallbackBody

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth/oauth", tags=["OAuth"])

# Supported OAuth providers and their Supabase provider identifiers
PROVIDERS = [
    {
        "id": "google",
        "name": "Google",
        "enabled": True,
    },
    {
        "id": "azure",
        "name": "Microsoft",
        "enabled": True,
    },
]


def _slugify(text: str) -> str:
    """Generate a URL-safe slug from text."""
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug[:50]


@router.get("/providers")
async def list_providers():
    """List available OAuth providers with their Supabase redirect URLs."""
    supabase_url = settings.supabase_url
    redirect_to = f"{settings.app_base_url}/login"

    provider_list = []
    for p in PROVIDERS:
        if not p["enabled"]:
            continue
        # Supabase OAuth URL format
        auth_url = (
            f"{supabase_url}/auth/v1/authorize"
            f"?provider={p['id']}"
            f"&redirect_to={redirect_to}"
        )
        provider_list.append({
            "id": p["id"],
            "name": p["name"],
            "auth_url": auth_url,
        })

    return {"data": provider_list}


@router.post("/callback")
@limiter.limit("10/minute")
async def oauth_callback(
    request: Request,
    body: OAuthCallbackBody,
    authorization: Optional[str] = Header(None),
):
    """
    Handle OAuth callback — ensure noctus_users profile exists.

    After Supabase OAuth completes, the frontend has an access token.
    This endpoint checks if the authenticated user has a noctus_users profile.
    If not, it creates one along with a new organization.
    """
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    user_id = user.id
    email = user.email or ""

    # Check if noctus_users profile already exists
    existing = db.table("noctus_users").select("id, org_id, role, nome").eq("id", user_id).execute()

    if existing.data and len(existing.data) > 0:
        # Profile exists — return it with organization
        profile = existing.data[0]
        org = db.table("organizations").select("*").eq("id", profile["org_id"]).single().execute()

        logger.info(f"OAuth login: existing user {email} via {body.provider}")
        return {
            "data": {
                "user": profile,
                "organization": org.data,
                "is_new": False,
            }
        }

    # Profile doesn't exist — create org + profile (new user via OAuth)
    # Extract name from email or Supabase user metadata
    nome = email.split("@")[0].replace(".", " ").title()
    user_meta = getattr(user, "user_metadata", {}) or {}
    if user_meta.get("full_name"):
        nome = user_meta["full_name"]
    elif user_meta.get("name"):
        nome = user_meta["name"]

    # Create organization (append suffix if slug already taken)
    org_name = f"Org de {nome}"
    org_slug = _slugify(nome)

    existing_slug = db.table("organizations").select("id").eq("slug", org_slug).execute()
    if existing_slug.data:
        import uuid
        org_slug = f"{org_slug}-{uuid.uuid4().hex[:6]}"

    org_result = db.table("organizations").insert({
        "nome": org_name,
        "slug": org_slug,
        "plano": "free",
        "owner_id": user_id,
        "onboarding_completed": False,
        "onboarding_steps": {
            "company_details": False,
            "choose_plan": False,
            "invite_team": False,
            "enable_product": False,
        },
    }).execute()

    if not org_result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar organização")

    org = org_result.data[0]

    # Create noctus_users profile
    profile_result = db.table("noctus_users").insert({
        "id": user_id,
        "email": email,
        "nome": nome,
        "org_id": org["id"],
        "role": "user",
        "org_role": "owner",  # Org creator is owner of their org
    }).execute()

    if not profile_result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar perfil de usuário")

    profile = profile_result.data[0]

    # Create free subscription for the new org
    free_plan = db.table("plans").select("id").eq("slug", "free").execute()
    if free_plan.data and len(free_plan.data) > 0:
        db.table("subscriptions").insert({
            "org_id": org["id"],
            "plan_id": free_plan.data[0]["id"],
            "status": "active",
        }).execute()

    # Sync org_id to auth user_metadata so product backends can read it
    try:
        db.auth.admin.update_user_by_id(user_id, {"user_metadata": {"org_id": org["id"]}})
    except Exception as e:
        logger.warning(f"Failed to sync org_id to user_metadata: {e}")

    logger.info(f"OAuth signup: new user {email} via {body.provider}, org={org['id']}")
    return {
        "data": {
            "user": profile,
            "organization": org,
            "is_new": True,
        }
    }
