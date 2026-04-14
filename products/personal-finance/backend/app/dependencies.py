"""
Shared dependencies for FastAPI routers.
Handles JWT auth token extraction and Supabase client creation.
"""
import logging
from typing import Optional
from fastapi import Header, HTTPException
from noctusai_shared.auth import first_or_none, resolve_sso_role  # noqa: F401
from app.database import get_supabase_client

logger = logging.getLogger(__name__)


async def get_current_user(authorization: Optional[str] = Header(None)):
    """Extract and validate JWT from Authorization header. Returns (user, token)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = authorization.replace("Bearer ", "")
    try:
        admin = get_supabase_client()
        user_response = admin.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token inválido")
        return user_response.user, token
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Não autenticado")


async def get_current_user_org(authorization: Optional[str] = Header(None)):
    """
    Extract user + org_id from auth user_metadata.
    Returns (user, token, org_id) tuple.
    """
    user, token = await get_current_user(authorization)
    org_id = (user.user_metadata or {}).get("org_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="Usuário sem organização associada")
    return user, token, org_id


def get_user_role(user) -> str:
    """Resolve the user's role for Personal Finance access.

    Uses shared ``resolve_sso_role()`` first (org owner/admin or NoctusAI
    admin → 'platform_admin'). PF has no role tiers, so non-admin users
    default to 'user'.
    """
    sso = resolve_sso_role(user)
    if sso:
        return sso
    return (user.user_metadata or {}).get("role", "user")


def get_user_client(token: str):
    """Get a Supabase client authenticated as the user (respects RLS)."""
    return get_supabase_client(token)


def get_admin_client():
    """Get a Supabase client with service role (bypasses RLS)."""
    return get_supabase_client()
