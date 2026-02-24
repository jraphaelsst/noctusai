"""
NoctusAI Core — Auth dependencies and JWT helpers.
"""
import jwt
import datetime
from typing import Optional, Tuple, List
from fastapi import Header, HTTPException
from app.config import settings
from app.database import get_supabase_client, get_admin_client


async def get_current_user(authorization: Optional[str] = Header(None)) -> Tuple:
    """Extract and validate user from Supabase auth token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")

    token = authorization.replace("Bearer ", "")
    client = get_supabase_client()

    try:
        user_response = client.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token inválido")
        return user_response.user, token
    except Exception:
        raise HTTPException(status_code=401, detail="Não autenticado")


async def get_current_admin(authorization: Optional[str] = Header(None)) -> Tuple:
    """Extract user and verify they have platform admin role."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = db.table("noctus_users").select("role").eq("id", user.id).single().execute()
    if not profile.data or profile.data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return user, token


async def get_current_user_with_permissions(
    authorization: Optional[str] = Header(None),
) -> Tuple:
    """Authenticate user and return (user, token, permissions_list).

    Resolves the user's org role, looks up the role's permissions in the
    `roles` table (org-specific first, then system fallback), and returns
    the full permission list alongside the standard auth tuple.
    """
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Fetch user profile with org role
    profile = (
        db.table("noctus_users")
        .select("org_id, org_role")
        .eq("id", user.id)
        .single()
        .execute()
    )
    if not profile.data:
        return user, token, []

    org_id = profile.data.get("org_id")
    role_slug = profile.data.get("org_role", "member")

    # Look up role permissions: org-specific first
    permissions: List[str] = []
    role_record = (
        db.table("roles")
        .select("permissions")
        .eq("slug", role_slug)
        .eq("org_id", org_id)
        .execute()
    )

    if not role_record.data:
        # Fallback to system role (org_id IS NULL)
        role_record = (
            db.table("roles")
            .select("permissions")
            .eq("slug", role_slug)
            .is_("org_id", "null")
            .execute()
        )

    if role_record.data:
        permissions = role_record.data[0].get("permissions", [])

    return user, token, permissions


def create_sso_token(user_id: str, org_id: str, product_slug: str,
                     email: str, role: str = "user") -> str:
    """Create a short-lived SSO token for product access."""
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "product": product_slug,
        "email": email,
        "role": role,
        "type": "sso",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(
            minutes=settings.sso_token_expiration_minutes
        ),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_sso_token(token: str) -> dict:
    """Verify and decode an SSO token. Used by products to validate access."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "sso":
            raise HTTPException(status_code=401, detail="Token não é SSO")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token SSO expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token SSO inválido")
