"""
Shared dependencies for FastAPI routers.

Handles JWT auth, role resolution, and Supabase client creation.
Unlike ERP/PF (which use org_id for tenant isolation), the therapy
platform uses role-based access with clinic_id scoping. Users log in
directly via Supabase Auth — no NoctusAI SSO.

Roles: platform_admin, clinic_admin, therapist, patient
"""
import logging
from typing import Optional

from fastapi import Header, HTTPException

from noctusai_seed import create_database_module, create_dependencies
from noctusai_lib.domain.action_log import log_action as _shared_log_action
from noctusai_lib.api.auth import first_or_none, resolve_sso_role  # noqa: F401
from app.config import settings

logger = logging.getLogger(__name__)

_db = create_database_module(settings, schema="therapy")
deps = create_dependencies(_db)

get_current_user = deps.get_current_user
get_user_client = deps.get_user_client
get_admin_client = deps.get_admin_client

# ── THERAPY-SPECIFIC extensions ─────────────────────────────────────


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


def get_supabase_client(access_token=None):
    """Backwards-compatible alias for database client creation."""
    return _db.get_client(access_token)


def log_action(
    user_id: str,
    tipo_acao: str,
    tipo_entidade: str,
    entidade_id: Optional[str] = None,
    descricao: str = "",
    detalhes: Optional[dict] = None,
):
    """Server-side action logging. Always runs with service role."""
    _shared_log_action(
        get_admin_client(), "action_log", "user_id",
        user_id, tipo_acao, tipo_entidade, entidade_id, descricao, detalhes,
    )
