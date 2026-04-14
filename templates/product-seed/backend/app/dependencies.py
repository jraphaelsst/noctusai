"""
{{PRODUCT_NAME}} — Auth dependencies.

get_current_user lives here (not in shared) so that unittest.mock.patch works
correctly — closures capture references at import time.
"""
from typing import Optional
from fastapi import Header, HTTPException
from noctusai_shared.auth import first_or_none, resolve_sso_role  # noqa: F401
from app.database import get_supabase_client


async def get_current_user(authorization: Optional[str] = Header(None)):
    """Extract and validate JWT from Authorization header. Returns (user, token)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = authorization.replace("Bearer ", "")
    try:
        client = get_supabase_client()
        user_response = client.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token inválido")
        return user_response.user, token
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Não autenticado")


def get_user_role(user) -> str:
    """Resolve the user's role.

    Uses shared ``resolve_sso_role()`` first (org owner/admin or NoctusAI
    admin → 'platform_admin'), then falls through to product-specific roles.
    Customize the fallback with your product's role hierarchy.
    """
    sso = resolve_sso_role(user)
    if sso:
        return sso
    return (user.user_metadata or {}).get("role", "user")


def get_org_id(user) -> str:
    """Extract org_id from user metadata."""
    metadata = user.user_metadata or {}
    org_id = metadata.get("org_id")
    if not org_id:
        raise HTTPException(status_code=404, detail="Organização não encontrada")
    return org_id
