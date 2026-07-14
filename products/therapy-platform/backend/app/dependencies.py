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

from noctusai_seed import create_database_module, create_dependencies
from noctusai_lib.domain.action_log import log_action as _shared_log_action
from noctusai_lib.api.auth import (  # noqa: F401
    first_or_none,
    make_require_role,
    make_resolve_platform_role,
)
from app.config import settings

logger = logging.getLogger(__name__)

_db = create_database_module(settings, schema="therapy")
deps = create_dependencies(_db)

get_current_user = deps.get_current_user
get_user_client = deps.get_user_client
get_admin_client = deps.get_admin_client

# Trusted-first platform-admin cascade (``role-cascade-trusted``, 2026-07-14)
# — `public.noctus_users`, NOT the spoofable `user_metadata` `get_user_role`
# below used to trust via `resolve_sso_role`. `get_core_client` targets
# `public` (service role); the therapy-scoped admin client would 500 with
# PGRST205 resolving `.table("noctus_users")` against the wrong schema —
# see `noctusai_lib.api.auth.make_resolve_platform_role`'s docstring.
resolve_platform_role = make_resolve_platform_role(lambda: _db.get_core_client())

# ── THERAPY-SPECIFIC extensions ─────────────────────────────────────


def get_user_role(user) -> str:
    """Determine the user's role from their metadata.

    Uses the trusted-DB platform-admin cascade first (``resolve_platform_role``
    — was the spoofable ``resolve_sso_role()``), then falls through to
    therapy-native roles from direct registration.

    Returns one of: 'platform_admin', 'clinic_admin', 'therapist', 'patient'.
    """
    # Trusted platform-admin cascade (org owner/admin or NoctusAI admin,
    # resolved from public.noctus_users — never spoofable user_metadata)
    sso = resolve_platform_role(user)
    if sso:
        return sso

    # Direct registration (therapy-native users)
    metadata = user.user_metadata or {}
    role = metadata.get("role")
    if role in ("platform_admin", "clinic_admin", "therapist", "patient"):
        return role

    return "patient"


require_role = make_require_role(get_current_user, get_user_role)
"""Product-bound role-guard dependency factory.

Usage in routers::

    @router.get("/admin/dashboard")
    async def admin_dashboard(
        auth=Depends(require_role("platform_admin")),
    ):
        user, token, role = auth
        ...

Per :func:`noctusai_lib.api.auth.make_require_role`.
"""


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
