"""
Shared dependencies for FastAPI routers.
Handles JWT auth token extraction and Supabase client creation.
"""
import logging
from typing import Optional
from fastapi import Header, HTTPException
from app.database import get_supabase_client

logger = logging.getLogger(__name__)


async def get_current_user(authorization: Optional[str] = Header(None)):
    """
    Extract and validate the JWT from the Authorization header.
    Returns (user, token) tuple.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")

    token = authorization.replace("Bearer ", "")
    try:
        admin = get_supabase_client()
        user_response = admin.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token invalido")
        return user_response.user, token
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Nao autenticado")


async def get_current_user_org(authorization: Optional[str] = Header(None)):
    """
    Extract user + org_id from the JWT.
    Returns (user, token, org_id) tuple.
    """
    user, token = await get_current_user(authorization)
    org_id = (user.user_metadata or {}).get("org_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="Usuario sem organizacao associada")
    return user, token, org_id


def get_user_client(token: str):
    """Get a Supabase client authenticated as the user (respects RLS)."""
    return get_supabase_client(token)


def get_admin_client():
    """Get a Supabase client with service role (bypasses RLS)."""
    return get_supabase_client()


def first_or_none(result) -> Optional[dict]:
    """Extract first record from a Supabase list response, or None."""
    if not result.data:
        return None
    if isinstance(result.data, dict):
        return result.data
    return result.data[0]
