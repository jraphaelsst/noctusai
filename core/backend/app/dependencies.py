"""
NoctusAI Core — Auth dependencies and JWT helpers.
"""
import re
import jwt
import datetime
from datetime import datetime as dt, timezone
from typing import Optional, Tuple, List
from fastapi import Header, HTTPException
from app.config import settings
from app.database import get_supabase_client, get_admin_client


def _parse_timestamp(value: str) -> dt:
    """Parse Supabase timestamp to datetime. Handles '2026-04-09 00:00:00+00' format."""
    ts = str(value).replace("Z", "+00:00").replace(" ", "T")
    ts = re.sub(r'([+-]\d{2})$', r'\1:00', ts)
    return dt.fromisoformat(ts)


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


async def get_org_id(user) -> str:
    """Extract org_id from noctus_users table for the given user.

    Raises HTTPException(404) if profile or org_id not found.
    """
    db = get_admin_client()
    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data or not profile.data.get("org_id"):
        raise HTTPException(status_code=404, detail="Perfil ou organização não encontrada")
    return profile.data["org_id"]


def check_org_license(db, org_id: str, product_id: str) -> bool:
    """Check if an org has a valid, non-expired license for a product.

    A license is valid when:
    - status = 'active'
    - fim IS NULL (permanent) OR fim > now()
    """
    result = db.table("licenses").select("id, fim").eq(
        "org_id", org_id
    ).eq("product_id", product_id).eq("status", "active").execute()

    if not result.data:
        return False

    now = dt.now(timezone.utc)
    for lic in result.data:
        fim = lic.get("fim")
        if fim is None:
            return True
        try:
            if _parse_timestamp(fim) > now:
                return True
        except (ValueError, TypeError):
            continue

    return False


def get_licensed_product_ids(db, org_id: str) -> list:
    """Get list of product IDs the org has valid licenses for.

    Filters out expired licenses (fim is not null AND fim <= now()).
    """
    result = db.table("licenses").select(
        "product_id, fim"
    ).eq("org_id", org_id).eq("status", "active").execute()

    if not result.data:
        return []

    now = dt.now(timezone.utc)
    valid_ids = []
    for lic in result.data:
        fim = lic.get("fim")
        if fim is None:
            valid_ids.append(lic["product_id"])
        else:
            try:
                if _parse_timestamp(fim) > now:
                    valid_ids.append(lic["product_id"])
            except (ValueError, TypeError):
                continue
    return valid_ids


def create_sso_token(user_id: str, org_id: str, product_slug: str,
                     email: str, role: str = "user",
                     org_role: str = "member") -> str:
    """Create a short-lived SSO token for product access.

    ``role`` is the NoctusAI platform-level role (admin / manager / user).
    ``org_role`` is the user's role within their org (owner / admin / member / viewer).
    Products use ``org_role`` to decide product-level admin access.
    """
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "product": product_slug,
        "email": email,
        "role": role,
        "org_role": org_role,
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
