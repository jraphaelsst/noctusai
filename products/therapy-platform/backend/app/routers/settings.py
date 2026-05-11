"""
Settings Router — Platform settings, clinic branding, therapist/patient preferences.

Platform-level endpoints require platform_admin role.
Clinic branding requires clinic_admin role.
Therapist/patient endpoints require the corresponding role.

Role enforcement uses ``Depends(require_role(...))`` from
``noctusai_lib.api.auth.make_require_role`` (bound in ``app/dependencies.py``).
Replaces the prior inline ``_require_admin(user)`` / ``_require_role(user, *roles)``
helpers — same 403 behavior, fewer round-trips through manual auth code.

**AI prompts** live as `platform_settings` rows with `ai_prompt_*` keys
(see migration 001_therapy_platform.sql:1466-1471 + `_get_prompt` consumers
in `summary_service.py` / `longitudinal_service.py`). Admins read/write them
via the generic GET/PATCH ``/platform`` endpoints below. The prior dedicated
``/platform/ai-prompts*`` endpoints referenced phantom tables
(`ai_prompt_settings` + `ai_prompt_history`) and were removed by
`therapy-platform-drift-sweep` on 2026-05-11. If per-prompt edit history
becomes a requirement, expose it as `platform_settings_history` filtered by
`setting_key LIKE 'ai_prompt_%'`.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import (
    first_or_none,
    get_admin_client,
    get_clinic_id_for_user,
    require_role,
)
from app.responses import success_response
from app.schemas.settings import (
    ClinicBrandingUpdate,
    PatientSettingsUpdate,
    PlatformSettingUpdate,
    TherapistSettingsUpdate,
)
from app.services import branding_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["Settings"])


# ── Platform Settings (Admin) ────────────────────────────────────────

@router.get("/platform")
async def get_platform_settings(auth=Depends(require_role("platform_admin"))):
    """Get all platform settings (admin only).

    Includes `ai_prompt_*` keys (AI prompt templates are stored in
    `platform_settings`; see module docstring).
    """
    db = get_admin_client()
    result = db.table("platform_settings").select("*").execute()
    return success_response(result.data or [])


@router.patch("/platform")
async def update_platform_setting(
    body: PlatformSettingUpdate,
    auth=Depends(require_role("platform_admin")),
):
    """Update a single platform setting (admin only).

    Also writes a row to `platform_settings_history` with the canonical
    `setting_key` / `old_value` / `new_value` / `changed_by_admin_id`
    columns (per migration 001_therapy_platform.sql therapy.platform_settings_history).
    """
    user, _token, _role = auth
    admin_id = user.id
    db = get_admin_client()

    # Snapshot prior value so the history row can carry `old_value`.
    prior = (
        db.table("platform_settings")
        .select("value")
        .eq("key", body.key)
        .execute()
    )
    prior_value = (first_or_none(prior) or {}).get("value")

    result = (
        db.table("platform_settings")
        .upsert({"key": body.key, "value": body.value})
        .execute()
    )

    # History entry — canonical column names per
    # 001_therapy_platform.sql therapy.platform_settings_history schema.
    db.table("platform_settings_history").insert({
        "setting_key": body.key,
        "old_value": prior_value,
        "new_value": body.value,
        "changed_by_admin_id": admin_id,
    }).execute()

    row = first_or_none(result)
    return success_response(row or {"key": body.key, "value": body.value})


# ── Therapist Settings ──────────────────────────────────────────────

@router.get("/therapist")
async def get_therapist_settings(auth=Depends(require_role("therapist"))):
    """Get own therapist settings."""
    user, _token, _role = auth
    db = get_admin_client()
    result = (
        db.table("therapist_settings")
        .select("*")
        .eq("user_id", user.id)
        .execute()
    )
    row = first_or_none(result)
    return success_response(row or {"user_id": user.id})


@router.patch("/therapist")
async def update_therapist_settings(
    body: TherapistSettingsUpdate,
    auth=Depends(require_role("therapist")),
):
    """Update own therapist settings."""
    user, _token, _role = auth
    db = get_admin_client()

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    update_data["user_id"] = user.id

    result = (
        db.table("therapist_settings")
        .upsert(update_data, on_conflict="user_id")
        .execute()
    )
    row = first_or_none(result)
    return success_response(row or update_data)


# ── Clinic Branding ─────────────────────────────────────────────────

@router.get("/clinic/branding")
async def get_clinic_branding(auth=Depends(require_role("clinic_admin"))):
    """Get clinic branding (clinic admin only)."""
    user, _token, _role = auth
    clinic_id = get_clinic_id_for_user(user)
    if not clinic_id:
        raise HTTPException(status_code=400, detail="Usuário não associado a uma clínica")
    db = get_admin_client()
    result = await branding_service.get_clinic_branding(clinic_id, db)
    return success_response(result)


@router.patch("/clinic/branding")
async def update_clinic_branding(
    body: ClinicBrandingUpdate,
    auth=Depends(require_role("clinic_admin")),
):
    """Update clinic branding (clinic admin only)."""
    user, _token, _role = auth
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
async def get_patient_settings(auth=Depends(require_role("patient"))):
    """Get own patient settings."""
    user, _token, _role = auth
    db = get_admin_client()
    result = (
        db.table("patient_profiles")
        .select("phone, photo_url, notification_preferences")
        .eq("user_id", user.id)
        .execute()
    )
    row = first_or_none(result)
    return success_response(row or {"user_id": user.id})


@router.patch("/patient")
async def update_patient_settings(
    body: PatientSettingsUpdate,
    auth=Depends(require_role("patient")),
):
    """Update own patient settings."""
    user, _token, _role = auth
    db = get_admin_client()

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}

    result = (
        db.table("patient_profiles")
        .update(update_data)
        .eq("user_id", user.id)
        .execute()
    )
    row = first_or_none(result)
    return success_response(row or update_data)
