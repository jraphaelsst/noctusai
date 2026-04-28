"""
Roles Router — Granular RBAC role definitions for NoctusAI.

GET    /api/roles          — List roles (system + org custom)
POST   /api/roles          — Create custom role for org (admin/owner only)
PATCH  /api/roles/{id}     — Update custom role (admin/owner only, can't edit system roles)
DELETE /api/roles/{id}     — Delete custom role (admin/owner only, can't delete system roles)

-- Supabase SQL to create the roles table:
--
-- CREATE TABLE roles (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid REFERENCES organizations(id),
--   name text NOT NULL,
--   slug text NOT NULL,
--   permissions text[] NOT NULL DEFAULT '{}',
--   is_system boolean NOT NULL DEFAULT false,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
-- ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
-- INSERT INTO roles (org_id, name, slug, permissions, is_system) VALUES
--   (NULL, 'Proprietário', 'owner', ARRAY['*'], true),
--   (NULL, 'Administrador', 'admin', ARRAY['team:manage', 'billing:manage', 'settings:manage', 'products:access'], true),
--   (NULL, 'Membro', 'member', ARRAY['products:access', 'team:read'], true),
--   (NULL, 'Visualizador', 'viewer', ARRAY['products:access:readonly', 'team:read'], true);
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.database import get_admin_client
from app.dependencies import get_current_user
from app.services.permissions import check_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/roles", tags=["Roles"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RoleCreate(BaseModel):
    name: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=50)
    permissions: List[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    permissions: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Known permissions (for validation / documentation)
# ---------------------------------------------------------------------------

KNOWN_PERMISSIONS = [
    "*",
    "team:manage",
    "team:read",
    "billing:manage",
    "billing:read",
    "settings:manage",
    "settings:read",
    "products:access",
    "products:access:readonly",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_profile(db, user_id: str) -> dict:
    """Fetch the noctus_users profile."""
    profile = (
        db.table("noctus_users")
        .select("id, org_id, org_role, role")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    return profile.data


async def _require_role_manage(user, db) -> dict:
    """Verify the caller can manage roles. Returns user profile."""
    profile = await _get_user_profile(db, user.id)
    org_id = profile["org_id"]

    # Must be platform admin or have team:manage permission
    is_platform_admin = profile.get("role") == "admin"
    has_perm = await check_permission(user.id, org_id, "team:manage")

    if not is_platform_admin and not has_perm:
        raise HTTPException(
            status_code=403,
            detail="Você não tem permissão para gerenciar papéis",
        )
    return profile


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def listar_roles(authorization: Optional[str] = Header(None)):
    """List all roles visible to the caller.

    Returns system roles (org_id IS NULL) plus any custom roles
    created for the caller's organization.
    """
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = await _get_user_profile(db, user.id)
    org_id = profile["org_id"]

    # System roles (org_id is NULL)
    system_roles = (
        db.table("roles")
        .select("*")
        .is_("org_id", "null")
        .eq("is_system", True)
        .order("created_at")
        .execute()
    )

    # Org custom roles
    org_roles = (
        db.table("roles")
        .select("*")
        .eq("org_id", org_id)
        .eq("is_system", False)
        .order("created_at")
        .execute()
    )

    all_roles = (system_roles.data or []) + (org_roles.data or [])
    return {"data": all_roles}


@router.post("")
async def criar_role(
    body: RoleCreate,
    authorization: Optional[str] = Header(None),
):
    """Create a custom role for the caller's organization."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = await _require_role_manage(user, db)
    org_id = profile["org_id"]

    # Validate permissions list
    for perm in body.permissions:
        if perm not in KNOWN_PERMISSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Permissão desconhecida: {perm}",
            )

    # Cannot use wildcard in custom roles
    if "*" in body.permissions:
        raise HTTPException(
            status_code=400,
            detail="A permissão coringa (*) é reservada para papéis de sistema",
        )

    # Ensure slug uniqueness within the org (and system roles)
    existing = (
        db.table("roles")
        .select("id")
        .eq("slug", body.slug)
        .execute()
    )
    org_or_system = [
        r for r in (existing.data or [])
    ]
    # Check more specifically: system or same org
    slug_check_system = (
        db.table("roles")
        .select("id")
        .eq("slug", body.slug)
        .is_("org_id", "null")
        .execute()
    )
    slug_check_org = (
        db.table("roles")
        .select("id")
        .eq("slug", body.slug)
        .eq("org_id", org_id)
        .execute()
    )
    if (slug_check_system.data) or (slug_check_org.data):
        raise HTTPException(
            status_code=409,
            detail="Já existe um papel com este slug",
        )

    role_data = {
        "org_id": org_id,
        "name": body.name,
        "slug": body.slug,
        "permissions": body.permissions,
        "is_system": False,
    }

    result = db.table("roles").insert(role_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar papel")

    logger.info(f"Custom role created: {body.name} ({body.slug}) for org={org_id}")
    return {"data": result.data[0]}


@router.patch("/{role_id}")
async def atualizar_role(
    role_id: str,
    body: RoleUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update a custom role. Cannot edit system roles."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    await _require_role_manage(user, db)

    # Fetch the role
    role = (
        db.table("roles")
        .select("id, is_system, org_id")
        .eq("id", role_id)
        .single()
        .execute()
    )
    if not role.data:
        raise HTTPException(status_code=404, detail="Papel não encontrado")

    if role.data.get("is_system"):
        raise HTTPException(
            status_code=403,
            detail="Papéis de sistema não podem ser editados",
        )

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Validate permissions if provided
    if "permissions" in data:
        for perm in data["permissions"]:
            if perm not in KNOWN_PERMISSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Permissão desconhecida: {perm}",
                )
        if "*" in data["permissions"]:
            raise HTTPException(
                status_code=400,
                detail="A permissão coringa (*) é reservada para papéis de sistema",
            )

    result = db.table("roles").update(data).eq("id", role_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Papel não encontrado")

    logger.info(f"Role updated: {role_id}")
    return {"data": result.data[0]}


@router.delete("/{role_id}")
async def deletar_role(
    role_id: str,
    authorization: Optional[str] = Header(None),
):
    """Delete a custom role. Cannot delete system roles.

    Checks that no users in the org currently have this role assigned.
    """
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = await _require_role_manage(user, db)
    org_id = profile["org_id"]

    # Fetch the role
    role = (
        db.table("roles")
        .select("id, slug, is_system, org_id")
        .eq("id", role_id)
        .single()
        .execute()
    )
    if not role.data:
        raise HTTPException(status_code=404, detail="Papel não encontrado")

    if role.data.get("is_system"):
        raise HTTPException(
            status_code=403,
            detail="Papéis de sistema não podem ser excluídos",
        )

    # Ensure the role belongs to the caller's org
    if role.data.get("org_id") != org_id:
        raise HTTPException(status_code=403, detail="Sem permissão para este papel")

    # Check if any users in the org currently have this role
    users_with_role = (
        db.table("noctus_users")
        .select("id")
        .eq("org_id", org_id)
        .eq("org_role", role.data["slug"])
        .execute()
    )
    if users_with_role.data:
        raise HTTPException(
            status_code=409,
            detail=f"{len(users_with_role.data)} membro(s) ainda usam este papel. "
                   "Altere seus papéis antes de excluir.",
        )

    db.table("roles").delete().eq("id", role_id).execute()

    logger.info(f"Role deleted: {role_id} ({role.data['slug']})")
    return {"message": "Papel excluído com sucesso"}
