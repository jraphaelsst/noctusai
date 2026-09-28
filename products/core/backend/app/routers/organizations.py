"""
Organizations Router — Manage tenant organizations.

GET    /api/organizations       — List (admin: all, user: own)
GET    /api/organizations/{id}  — Get one
PATCH  /api/organizations/{id}  — Update
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin
from app.schemas.organizations import OrgUpdate
from app.services.permissions import require_org_permission

#: Fields only a NoctusAI platform admin may change. `plano` is the billing
#: tier and `category='test'` bypasses every entitlement check
#: (`services.entitlements._is_test_org`) — an org editing either on itself
#: is a self-upgrade. Org owners/admins may rename their org (`nome`).
_PLATFORM_ADMIN_ONLY_FIELDS = frozenset({"plano", "category"})

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/organizations", tags=["Organizations"])


@router.get("")
async def listar_organizations(authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Get user's profile to check role
    profile = db.table("noctus_users").select("org_id, role").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    # Admin sees all orgs, regular user sees only their own
    if profile.data.get("role") == "admin":
        result = db.table("organizations").select("*").order("nome").execute()
    else:
        org_id = profile.data["org_id"]
        result = db.table("organizations").select("*").eq("id", org_id).execute()

    return {"data": result.data or []}


@router.get("/{org_id}")
async def get_organization(org_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Verify user belongs to this org or is platform admin
    profile = db.table("noctus_users").select("org_id, role").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    if profile.data["org_id"] != org_id and profile.data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    result = db.table("organizations").select("*").eq("id", org_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Organização não encontrada")
    return {"data": result.data}


@router.patch("/{org_id}")
async def atualizar_organization(org_id: str, body: OrgUpdate, authorization: Optional[str] = Header(None)):
    """Update an organization.

    SEC-1 (2026-09-28): a platform admin (`noctus_users.role == 'admin'`) may
    update any org and any field. Anyone else may update only THEIR OWN org,
    only with `settings:manage`, and never `plano` / `category`. Before, any
    member of the org could PATCH all three.
    """
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = db.table("noctus_users").select("org_id, role").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    is_platform_admin = profile.data.get("role") == "admin"

    data = body.model_dump(exclude_none=True)

    if not is_platform_admin:
        if profile.data.get("org_id") != org_id:
            raise HTTPException(status_code=403, detail="Acesso negado")
        await require_org_permission(user.id, org_id, "settings:manage")
        restricted = sorted(_PLATFORM_ADMIN_ONLY_FIELDS & data.keys())
        if restricted:
            raise HTTPException(
                status_code=403,
                detail=f"Somente administradores da plataforma podem alterar: {', '.join(restricted)}",
            )

    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("organizations").update(data).eq("id", org_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Organização não encontrada")
    return {"data": result.data[0]}
