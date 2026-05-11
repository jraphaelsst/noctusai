"""
Settings Router — Platform and organization settings for NoctusAI.

Platform settings (admin only):
GET    /api/settings/platform          — List all platform settings
PUT    /api/settings/platform/{key}    — Upsert a platform setting
DELETE /api/settings/platform/{key}    — Delete a platform setting

Org settings (authenticated, RLS-scoped):
GET    /api/settings/org               — List org settings for current user's org
PUT    /api/settings/org/{key}         — Upsert an org setting
DELETE /api/settings/org/{key}         — Delete an org setting

Key resolution:
GET    /api/settings/resolve/{key}     — Resolve: org → platform → None

-- Supabase SQL:
--
-- CREATE TABLE IF NOT EXISTS platform_settings (
--   key TEXT PRIMARY KEY,
--   value TEXT NOT NULL,
--   description TEXT,
--   is_secret BOOLEAN DEFAULT false,
--   updated_at TIMESTAMPTZ DEFAULT now(),
--   updated_by UUID REFERENCES auth.users(id)
-- );
--
-- CREATE TABLE IF NOT EXISTS org_settings (
--   id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
--   org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
--   key TEXT NOT NULL,
--   value TEXT NOT NULL,
--   is_secret BOOLEAN DEFAULT false,
--   updated_at TIMESTAMPTZ DEFAULT now(),
--   UNIQUE(org_id, key)
-- );
-- ALTER TABLE org_settings ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "org_members_manage_settings" ON org_settings
--   FOR ALL USING (org_id IN (SELECT org_id FROM org_members WHERE user_id = auth.uid()));
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin, get_org_id
from app.schemas.settings import OrgSettingBody, PlatformSettingBody
from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["Settings"])


def _mask_value(value: str) -> str:
    """Mask a secret value, showing only last 4 chars."""
    if len(value) <= 4:
        return "****"
    return "*" * (len(value) - 4) + value[-4:]


# ── Platform settings (admin only) ──────────────────────────────────────

@router.get("/platform")
async def listar_platform_settings(authorization: Optional[str] = Header(None)):
    """List all platform settings (admin only). Secret values are masked."""
    await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("platform_settings").select("*").order("key").execute()
    items = result.data or []

    for item in items:
        if item.get("is_secret"):
            item["value"] = _mask_value(item["value"])

    return {"data": items}


@router.put("/platform/{key}")
async def upsert_platform_setting(
    key: str,
    body: PlatformSettingBody,
    authorization: Optional[str] = Header(None),
):
    """Create or update a platform setting (admin only)."""
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("platform_settings").upsert(
        {
            "key": key,
            "value": body.value,
            "description": body.description,
            "is_secret": body.is_secret,
            "updated_by": user.id,
        },
        on_conflict="key",
    ).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao salvar configuração")

    logger.info(f"Platform setting upserted: {key}")
    return {"data": result.data[0] if isinstance(result.data, list) else result.data}


@router.delete("/platform/{key}")
async def deletar_platform_setting(
    key: str,
    authorization: Optional[str] = Header(None),
):
    """Delete a platform setting (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    delete_or_404(db, "platform_settings", ("key", key), message="Configuração não encontrada")

    logger.info(f"Platform setting deleted: {key}")
    return {"message": "Configuração removida com sucesso"}


# ── Org settings (authenticated, RLS-scoped) ────────────────────────────

@router.get("/org")
async def listar_org_settings(authorization: Optional[str] = Header(None)):
    """List settings for the current user's organization."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    result = db.table("org_settings").select("*").eq("org_id", org_id).order("key").execute()
    items = result.data or []

    for item in items:
        if item.get("is_secret"):
            item["value"] = _mask_value(item["value"])

    return {"data": items}


@router.put("/org/{key}")
async def upsert_org_setting(
    key: str,
    body: OrgSettingBody,
    authorization: Optional[str] = Header(None),
):
    """Create or update an org setting."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    result = db.table("org_settings").upsert(
        {
            "org_id": org_id,
            "key": key,
            "value": body.value,
            "is_secret": body.is_secret,
        },
        on_conflict="org_id,key",
    ).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao salvar configuração")

    logger.info(f"Org setting upserted: {key} for org {org_id}")
    return {"data": result.data[0] if isinstance(result.data, list) else result.data}


@router.delete("/org/{key}")
async def deletar_org_setting(
    key: str,
    authorization: Optional[str] = Header(None),
):
    """Delete an org setting."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    delete_or_404(db, "org_settings", ("org_id", org_id), ("key", key), message="Configuração não encontrada")

    logger.info(f"Org setting deleted: {key} for org {org_id}")
    return {"message": "Configuração removida com sucesso"}


# ── Key resolution ───────────────────────────────────────────────────────

@router.get("/resolve/{key}")
async def resolver_setting(key: str, authorization: Optional[str] = Header(None)):
    """Resolve a setting: org-level → platform-level → None."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Try org-level first
    try:
        org_id = await get_org_id(user)
    except Exception as exc:
        logger.debug("settings: get_org_id returned no org for user=%s (%s); will fall back to user-level setting", user.id, exc)
        org_id = None

    if org_id:
        org_result = (
            db.table("org_settings")
            .select("value")
            .eq("org_id", org_id)
            .eq("key", key)
            .limit(1)
            .execute()
        )
        if org_result.data and org_result.data[0].get("value"):
            return {"data": {"key": key, "value": org_result.data[0]["value"], "source": "org"}}

    # Fall back to platform-level
    platform_result = (
        db.table("platform_settings")
        .select("value")
        .eq("key", key)
        .limit(1)
        .execute()
    )
    if platform_result.data and platform_result.data[0].get("value"):
        return {"data": {"key": key, "value": platform_result.data[0]["value"], "source": "platform"}}

    return {"data": None}
