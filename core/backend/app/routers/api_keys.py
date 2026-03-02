"""
API Keys Router — Manage API keys for external integrations.

GET    /api/api-keys           — List keys for current org (prefix only)
POST   /api/api-keys           — Create key (returns full key ONCE)
PATCH  /api/api-keys/{id}      — Update name/scopes/expiry
DELETE /api/api-keys/{id}      — Revoke key
GET    /api/admin/api-keys     — List ALL keys across orgs (admin only)

-- Supabase SQL to create the api_keys table:
--
-- CREATE TABLE api_keys (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL REFERENCES organizations(id),
--   name text NOT NULL,
--   key_prefix text NOT NULL,
--   key_hash text NOT NULL,
--   scopes jsonb NOT NULL DEFAULT '["read"]',
--   last_used_at timestamptz,
--   expires_at timestamptz,
--   is_active boolean NOT NULL DEFAULT true,
--   created_by uuid NOT NULL REFERENCES noctus_users(id),
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
--
-- ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "api_keys_read_own" ON api_keys FOR SELECT TO authenticated
--   USING (org_id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid()));
-- CREATE POLICY "api_keys_write_own" ON api_keys FOR ALL TO authenticated
--   USING (org_id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid()));
-- CREATE POLICY "api_keys_admin_all" ON api_keys FOR ALL USING (
--   auth.uid() IN (SELECT id FROM noctus_users WHERE role = 'admin')
-- );
"""
import secrets
import hashlib
import logging
from typing import Optional, List
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(tags=["API Keys"])


class ApiKeyCreate(BaseModel):
    name: str = Field(..., max_length=100)
    scopes: List[str] = Field(default=["read"])
    expires_at: Optional[str] = None


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    scopes: Optional[List[str]] = None
    expires_at: Optional[str] = None


def _generate_api_key() -> tuple[str, str, str]:
    """Generate a Stripe-like API key. Returns (raw_key, key_hash, key_prefix)."""
    raw_key = f"noctus_k_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:16]
    return raw_key, key_hash, key_prefix


@router.get("/api/api-keys")
async def listar_api_keys(authorization: Optional[str] = Header(None)):
    """List API keys for the current user's organization (prefix only)."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    org_id = profile.data["org_id"]
    result = db.table("api_keys").select(
        "id, org_id, name, key_prefix, scopes, last_used_at, expires_at, is_active, created_by, created_at"
    ).eq("org_id", org_id).eq("is_active", True).order("created_at", desc=True).execute()

    return {"data": result.data or []}


@router.post("/api/api-keys")
async def criar_api_key(body: ApiKeyCreate, authorization: Optional[str] = Header(None)):
    """Create a new API key. Returns the full key ONCE — store it securely."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    org_id = profile.data["org_id"]
    raw_key, key_hash, key_prefix = _generate_api_key()

    data = {
        "org_id": org_id,
        "name": body.name,
        "key_prefix": key_prefix,
        "key_hash": key_hash,
        "scopes": body.scopes,
        "is_active": True,
        "created_by": user.id,
    }
    if body.expires_at:
        data["expires_at"] = body.expires_at

    result = db.table("api_keys").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar chave API")

    logger.info(f"API key created: {key_prefix}... for org={org_id}")

    # Return the full key once — it cannot be retrieved again
    response_data = result.data[0].copy()
    response_data["raw_key"] = raw_key
    return {"data": response_data}


@router.patch("/api/api-keys/{key_id}")
async def atualizar_api_key(
    key_id: str, body: ApiKeyUpdate,
    authorization: Optional[str] = Header(None)
):
    """Update an API key's name, scopes, or expiry."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Scope to user's org
    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    org_id = profile.data["org_id"]

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("api_keys").update(data).eq("id", key_id).eq("org_id", org_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Chave API não encontrada")

    logger.info(f"API key updated: {key_id}")
    return {"data": result.data[0]}


@router.delete("/api/api-keys/{key_id}")
async def revogar_api_key(key_id: str, authorization: Optional[str] = Header(None)):
    """Revoke an API key (set inactive)."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Scope to user's org
    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    org_id = profile.data["org_id"]

    result = db.table("api_keys").update(
        {"is_active": False}
    ).eq("id", key_id).eq("org_id", org_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Chave API não encontrada")

    logger.info(f"API key revoked: {key_id}")
    return {"data": result.data[0]}


@router.get("/api/admin/api-keys")
async def admin_listar_api_keys(authorization: Optional[str] = Header(None)):
    """List ALL API keys across all orgs (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("api_keys").select(
        "id, org_id, name, key_prefix, scopes, last_used_at, expires_at, is_active, created_by, created_at, organizations(id, nome)"
    ).order("created_at", desc=True).execute()

    return {"data": result.data or []}
