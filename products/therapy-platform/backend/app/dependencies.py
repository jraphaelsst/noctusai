"""
Shared dependencies for FastAPI routers.

Handles JWT auth, role resolution, and Supabase client creation.
Unlike ERP/PF (which use org_id for tenant isolation), the therapy
platform uses role-based access with clinic_id scoping. Users log in
directly via Supabase Auth — no NoctusAI SSO.

Roles: platform_admin, clinic_admin, therapist, patient
"""
from __future__ import annotations

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
            raise HTTPException(status_code=401, detail="Token invalido")
        return user_response.user, token
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Nao autenticado")


def get_user_role(user) -> str:
    """Determine the user's role from their metadata.

    Uses shared ``resolve_sso_role()`` first (handles org_role + noctus_role),
    then falls through to therapy-native roles from direct registration.

    Returns one of: 'platform_admin', 'clinic_admin', 'therapist', 'patient'.
    """
    # SSO-derived admin access (org owner/admin or NoctusAI admin)
    sso = resolve_sso_role(user)
    if sso:
        return sso

    # Direct registration (therapy-native users)
    metadata = user.user_metadata or {}
    role = metadata.get("role")
    if role in ("platform_admin", "clinic_admin", "therapist", "patient"):
        return role

    return "patient"


def require_role(*allowed_roles: str):
    """Dependency factory that checks the user's role against allowed roles.

    Usage in routers:
        @router.get("/admin/dashboard")
        async def admin_dashboard(
            user_and_token=Depends(get_current_user),
            _=Depends(require_role("platform_admin")),
        ):
    """
    async def _check_role(authorization: Optional[str] = Header(None)):
        user, token = await get_current_user(authorization)
        role = get_user_role(user)
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Acesso negado. Funcionalidade restrita a: {', '.join(allowed_roles)}",
            )
        return user, token, role
    return _check_role


def get_clinic_id_for_user(user) -> Optional[str]:
    """Resolve clinic_id from user metadata.

    For clinic admins: returns their clinic_id.
    For clinic-affiliated therapists: returns their clinic_id.
    For independent therapists/patients: returns None.
    """
    metadata = user.user_metadata or {}
    return metadata.get("clinic_id")


def get_user_client(token: str):
    """Get a Supabase client authenticated as the user (respects RLS)."""
    return get_supabase_client(token)


def get_admin_client():
    """Get a Supabase client with service role (bypasses RLS)."""
    return get_supabase_client()


def log_action(
    user_id: str,
    tipo_acao: str,
    tipo_entidade: str,
    entidade_id: Optional[str] = None,
    descricao: str = "",
    detalhes: Optional[dict] = None,
):
    """Server-side action logging. Always runs with service role."""
    admin = get_admin_client()
    try:
        admin.table("action_log").insert({
            "user_id": user_id,
            "tipo_acao": tipo_acao,
            "tipo_entidade": tipo_entidade,
            "entidade_id": entidade_id,
            "descricao": descricao,
            "detalhes": detalhes or {},
        }).execute()
    except Exception as e:
        logger.warning("Failed to log action: %s", e)
