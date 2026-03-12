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
