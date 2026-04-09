"""
Settings Router — Platform settings, AI prompts, clinic branding, therapist/patient preferences.

Platform-level endpoints require platform_admin role.
Clinic branding requires clinic_admin role.
Therapist/patient endpoints require the corresponding role.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    get_current_user,
    get_admin_client,
    get_user_client,
    get_user_role,
    get_clinic_id_for_user,
)
from app.responses import success_response
from app.schemas.settings import (
    AIPromptUpdate,
    ClinicBrandingUpdate,
    PatientSettingsUpdate,
    PlatformSettingUpdate,
    TherapistSettingsUpdate,
)
from app.services import branding_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["Settings"])


def _require_admin(user) -> str:
    """Enforce platform_admin role. Returns user.id."""
    role = get_user_role(user)
    if role != "platform_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores da plataforma")
    return user.id


def _require_role(user, *allowed_roles: str) -> str:
    """Enforce one of the allowed roles. Returns user.id."""
    role = get_user_role(user)
    if role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Acesso restrito a: {', '.join(allowed_roles)}",
        )
    return user.id


# ── Platform Settings (Admin) ────────────────────────────────────────

@router.get("/platform")
async def get_platform_settings(authorization: Optional[str] = Header(None)):
    """Get all platform settings (admin only)."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()
    result = db.table("platform_settings").select("*").execute()
    return success_response(result.data or [])


@router.patch("/platform")
async def update_platform_setting(
    body: PlatformSettingUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update a single platform setting (admin only)."""
    user, _ = await get_current_user(authorization)
    admin_id = _require_admin(user)
    db = get_admin_client()

    result = (
        db.table("platform_settings")
        .upsert({"key": body.key, "value": body.value, "updated_by": admin_id})
        .execute()
    )

    # Create history entry
    db.table("settings_history").insert({
        "setting_type": "platform",
        "setting_key": body.key,
        "new_value": body.value,
        "changed_by": admin_id,
    }).execute()

    from app.dependencies import first_or_none
    row = first_or_none(result)
    return success_response(row or {"key": body.key, "value": body.value})


# ── AI Prompts (Admin) ──────────────────────────────────────────────

@router.get("/platform/ai-prompts")
async def get_ai_prompts(authorization: Optional[str] = Header(None)):
    """Get all AI prompt settings (admin only)."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()
    result = (
        db.table("ai_prompt_settings")
        .select("*")
        .order("prompt_key")
        .execute()
    )
    return success_response(result.data or [])


@router.patch("/platform/ai-prompts")
async def update_ai_prompt(
    body: AIPromptUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update an AI prompt template (admin only, versioned)."""
    user, _ = await get_current_user(authorization)
    admin_id = _require_admin(user)
    db = get_admin_client()

    result = (
        db.table("ai_prompt_settings")
        .upsert({"prompt_key": body.prompt_key, "prompt_text": body.prompt_text, "updated_by": admin_id})
        .execute()
    )

    # Version history
    db.table("ai_prompt_history").insert({
        "prompt_key": body.prompt_key,
        "prompt_text": body.prompt_text,
        "changed_by": admin_id,
    }).execute()

    from app.dependencies import first_or_none
    row = first_or_none(result)
    return success_response(row or {"prompt_key": body.prompt_key, "prompt_text": body.prompt_text})


@router.get("/platform/ai-prompts/history")
async def get_ai_prompt_history(
    prompt_key: str = Query(...),
    authorization: Optional[str] = Header(None),
):
    """Get version history for a specific AI prompt (admin only)."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()
    result = (
        db.table("ai_prompt_history")
        .select("*")
        .eq("prompt_key", prompt_key)
        .order("created_at", desc=True)
        .execute()
    )
    return success_response(result.data or [])


# ── Therapist Settings ──────────────────────────────────────────────

@router.get("/therapist")
async def get_therapist_settings(authorization: Optional[str] = Header(None)):
    """Get own therapist settings."""
    user, token = await get_current_user(authorization)
    _require_role(user, "therapist")
    db = get_admin_client()
    result = (
        db.table("therapist_settings")
        .select("*")
        .eq("user_id", user.id)
        .execute()
    )
    from app.dependencies import first_or_none
    row = first_or_none(result)
    return success_response(row or {"user_id": user.id})


@router.patch("/therapist")
async def update_therapist_settings(
    body: TherapistSettingsUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update own therapist settings."""
    user, token = await get_current_user(authorization)
    _require_role(user, "therapist")
    db = get_admin_client()

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    update_data["user_id"] = user.id

    result = (
        db.table("therapist_settings")
        .upsert(update_data, on_conflict="user_id")
        .execute()
    )
    from app.dependencies import first_or_none
    row = first_or_none(result)
    return success_response(row or update_data)


# ── Clinic Branding ─────────────────────────────────────────────────

@router.get("/clinic/branding")
async def get_clinic_branding(authorization: Optional[str] = Header(None)):
    """Get clinic branding (clinic admin only)."""
    user, _ = await get_current_user(authorization)
    _require_role(user, "clinic_admin")
    clinic_id = get_clinic_id_for_user(user)
    if not clinic_id:
        raise HTTPException(status_code=400, detail="Usuário não associado a uma clínica")
    db = get_admin_client()
    result = await branding_service.get_clinic_branding(clinic_id, db)
    return success_response(result)


@router.patch("/clinic/branding")
async def update_clinic_branding(
    body: ClinicBrandingUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update clinic branding (clinic admin only)."""
    user, _ = await get_current_user(authorization)
    _require_role(user, "clinic_admin")
    clinic_id = get_clinic_id_for_user(user)
    if not clinic_id:
        raise HTTPException(status_code=400, detail="Usuário não associado a uma clínica")
    db = get_admin_client()
    result = await branding_service.update_clinic_branding(
        clinic_id, body.model_dump(exclude_none=True), db,
    )
    return success_response(result)


# ── Patient Settings ────────────────────────────────────────────────

@router.get("/patient")
async def get_patient_settings(authorization: Optional[str] = Header(None)):
    """Get own patient settings."""
    user, token = await get_current_user(authorization)
    _require_role(user, "patient")
    db = get_admin_client()
    result = (
        db.table("patient_profiles")
        .select("phone, photo_url, notification_preferences")
        .eq("user_id", user.id)
        .execute()
    )
    from app.dependencies import first_or_none
    row = first_or_none(result)
    return success_response(row or {"user_id": user.id})


@router.patch("/patient")
async def update_patient_settings(
    body: PatientSettingsUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update own patient settings."""
    user, token = await get_current_user(authorization)
    _require_role(user, "patient")
    db = get_admin_client()

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}

    result = (
        db.table("patient_profiles")
        .update(update_data)
        .eq("user_id", user.id)
        .execute()
    )
    from app.dependencies import first_or_none
    row = first_or_none(result)
    return success_response(row or update_data)
