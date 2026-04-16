"""
Shared authentication helpers for all NoctusAI APIs.

Provides the common get_current_user auth dependency and the
first_or_none Supabase result helper. Each product backend still
owns its own get_supabase_client, get_user_client, get_admin_client,
and product-specific helpers (get_org_id, get_current_admin, etc.).
"""
from __future__ import annotations

from typing import Optional
from fastapi import Header, HTTPException


def first_or_none(result) -> Optional[dict]:
    """Extract first record from a Supabase list response, or None."""
    if not result.data:
        return None
    if isinstance(result.data, dict):
        return result.data
    return result.data[0]


async def get_current_user(
    authorization: Optional[str] = Header(None),
    *,
    _get_supabase_client=None,
):
    """
    Extract and validate the JWT from the Authorization header.
    Returns (user, token) tuple.

    The _get_supabase_client parameter is injected by each product's
    dependencies.py to supply the product-specific client factory.
    This avoids a circular dependency between shared auth and product
    database modules.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")

    token = authorization.replace("Bearer ", "")
    try:
        if _get_supabase_client is None:
            raise RuntimeError(
                "get_current_user must be called via a product-specific wrapper "
                "that supplies _get_supabase_client"
            )
        admin = _get_supabase_client()  # service role to validate
        user_response = admin.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token inválido")
        return user_response.user, token
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Não autenticado")


def make_get_current_user(get_supabase_client_fn):
    """
    Factory that creates a product-specific get_current_user dependency.

    Usage in each product's dependencies.py:

        from noctusai_shared.auth import make_get_current_user, first_or_none
        from app.database import get_supabase_client

        get_current_user = make_get_current_user(get_supabase_client)
    """
    async def _get_current_user(authorization: Optional[str] = Header(None)):
        return await get_current_user(
            authorization,
            _get_supabase_client=get_supabase_client_fn,
        )
    return _get_current_user


# ---------------------------------------------------------------------------
# SSO role resolution
# ---------------------------------------------------------------------------


def resolve_sso_role(user) -> Optional[str]:
    """Check SSO metadata for product-level admin access.

    When a user enters a product via SSO from the NoctusAI Core platform,
    the Core's ``/api/sso/session`` endpoint syncs ``org_role`` and
    ``noctus_role`` into the user's ``user_metadata``.

    Resolution order:
    1. ``org_role`` in (owner, admin) → ``"platform_admin"`` — the user's
       org bought the product license; they manage it.
    2. ``noctus_role == "admin"`` → ``"platform_admin"`` — NoctusAI
       platform admins have full access to every product.
    3. Otherwise → ``None`` — caller falls through to product-specific
       role logic (e.g. therapy-native roles, ERP DB roles).

    Products should call this first in their ``get_user_role()``::

        def get_user_role(user) -> str:
            sso = resolve_sso_role(user)
            if sso:
                return sso
            # … product-specific logic …
    """
    metadata = getattr(user, "user_metadata", None) or {}
    if metadata.get("org_role") in ("owner", "admin"):
        return "platform_admin"
    if metadata.get("noctus_role") == "admin":
        return "platform_admin"
    return None


def get_sso_context(user) -> dict:
    """Extract all SSO-synced context from user_metadata.

    Returns a dict with keys: ``noctus_role``, ``org_role``, ``org_id``,
    ``org_name``, ``org_logo_url``, ``plan_slug``, ``plan_max_users``,
    ``plan_max_products``, ``plan_features``, ``subscription_status``,
    ``subscription_expires_at``, ``license_expires_at``.

    All values default to None when not present in metadata.
    Products can use this in services to check plan limits, display
    org branding, or show license/trial warnings.
    """
    metadata = getattr(user, "user_metadata", None) or {}
    keys = (
        "noctus_role", "org_role", "org_id",
        "org_name", "org_logo_url",
        "plan_slug", "plan_max_users", "plan_max_products", "plan_features",
        "subscription_status", "subscription_expires_at",
        "license_expires_at",
    )
    return {k: metadata.get(k) for k in keys}


def require_role(get_user_role_fn, *allowed_roles: str):
    """FastAPI dependency factory that enforces role-based access.

    Parameters:
        get_user_role_fn: A callable ``(user) -> str`` that returns
            the resolved role for the user. Each product provides its own.
        *allowed_roles: Role strings that are permitted (e.g.
            ``"platform_admin"``, ``"clinic_admin"``).

    Returns a FastAPI dependency that can be used with ``Depends()``.

    Usage::

        from noctusai_shared.auth import require_role
        from app.dependencies import get_current_user, get_user_role

        admin_only = require_role(get_user_role, "platform_admin")

        @router.get("/admin/dashboard")
        async def dashboard(
            auth=Depends(get_current_user),
            _=Depends(admin_only),
        ):
            ...
    """
    async def _check_role(authorization: Optional[str] = Header(None)):
        user, token = await get_current_user(
            authorization,
            _get_supabase_client=None,  # overridden by product wrapper
        )
        role = get_user_role_fn(user)
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Acesso negado. Restrito a: {', '.join(allowed_roles)}",
            )
        return user, token, role
    return _check_role
