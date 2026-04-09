"""
Branding Service — clinic-level and platform-level branding.

Manages visual identity (colors, logo, favicon) for clinics and platform.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)

DEFAULT_BRANDING: Dict[str, Any] = {
    "primary_color": "#6366f1",
    "secondary_color": "#8b5cf6",
    "logo_url": None,
    "favicon_url": None,
}


async def get_clinic_branding(clinic_id: str, db: Any) -> Dict:
    """Return clinic branding or defaults if none set."""
    result = (
        db.table("clinic_branding")
        .select("*")
        .eq("clinic_id", clinic_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        return {**DEFAULT_BRANDING, "clinic_id": clinic_id}
    return row


async def update_clinic_branding(clinic_id: str, data: Dict, db: Any) -> Dict:
    """Upsert clinic branding (colors, logo, favicon)."""
    payload = {k: v for k, v in data.items() if v is not None}
    payload["clinic_id"] = clinic_id

    result = (
        db.table("clinic_branding")
        .upsert(payload, on_conflict="clinic_id")
        .execute()
    )
    row = first_or_none(result)
    if not row:
        # Upsert returned empty — return payload as-is
        return payload
    logger.info("Clinic branding updated: clinic_id=%s", clinic_id)
    return row


async def get_platform_branding(db: Any) -> Dict:
    """Return platform-level branding from platform_settings."""
    result = (
        db.table("platform_settings")
        .select("key, value")
        .in_("key", ["app_name", "primary_color", "secondary_color", "logo_url", "favicon_url"])
        .execute()
    )
    branding: Dict[str, Any] = {
        "app_name": "NoctusAI Therapy",
        "primary_color": "#6366f1",
        "secondary_color": "#8b5cf6",
        "logo_url": None,
        "favicon_url": None,
    }
    for row in result.data or []:
        branding[row["key"]] = row["value"]
    return branding
