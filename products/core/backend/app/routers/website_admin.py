"""Admin website API — `/api/admin/website/*` (contract §3, "Admin").

`get_website_editor` (admin OR marketing) gates every route; routes marked
🔒 in the contract additionally require `get_current_admin` (platform
admin only — a marketing user 403s).
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

from app.dependencies import get_current_admin, get_website_editor
from app.schemas.website import (
    WebsiteLeadActivityCreate,
    WebsiteLeadPatch,
    WebsiteSettingsRollback,
    WebsiteSettingsUpdate,
)
from app.services import audit_service, website_leads_service, website_settings_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/website", tags=["Website (admin)"])

_ADMIN_ONLY_KEYS = ("site_enabled", "signup_enabled")


@router.get("/settings")
async def get_admin_settings(authorization: Optional[str] = Header(None)):
    await get_website_editor(authorization)
    version, data = website_settings_service.get_current(use_cache=False)
    history = website_settings_service.get_history(limit=1)
    created_at = history[0]["created_at"] if history and history[0]["version"] == version else None
    created_by = history[0]["created_by"] if history and history[0]["version"] == version else None
    return {"data": {"version": version, "settings": data, "created_at": created_at, "created_by": created_by}}


@router.put("/settings")
async def put_admin_settings(
    body: WebsiteSettingsUpdate, request: Request, authorization: Optional[str] = Header(None)
):
    user, _token, role = await get_website_editor(authorization)

    current_version, current_data = website_settings_service.get_current(use_cache=False)
    new_data = body.settings.model_dump(mode="json")

    if role == "marketing":
        for key in _ADMIN_ONLY_KEYS:
            if new_data.get(key) != current_data.get(key):
                # See website_public.py's turnstile 403 for why this is a
                # dict, not a plain string — the seed error-shape escape
                # hatch for the contract's literal `{"detail": "..."}`.
                raise HTTPException(
                    status_code=403,
                    detail={"detail": "admin_only_field", "code": "admin_only_field"},
                )

    try:
        row = website_settings_service.update(new_data, body.expected_version, created_by=user.id)
    except website_settings_service.WebsiteVersionConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"detail": "version_conflict", "code": "version_conflict"},
        ) from exc
    except website_settings_service.WebsiteSocialProofEmpty as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await audit_service.log(
        user_id=user.id, org_id=None, action="update", resource_type="website_settings",
        resource_id=str(row["version"]), details={"version": row["version"]}, request=request,
    )
    return {"data": {
        "version": row["version"], "settings": row["data"],
        "created_at": row.get("created_at"), "created_by": row.get("created_by"),
    }}


@router.get("/settings/history")
async def get_settings_history(authorization: Optional[str] = Header(None)):
    await get_website_editor(authorization)
    return {"data": website_settings_service.get_history(limit=50)}


@router.post("/settings/rollback")
async def rollback_settings(
    body: WebsiteSettingsRollback, request: Request, authorization: Optional[str] = Header(None)
):
    user, _token = await get_current_admin(authorization)  # 🔒 admin only
    try:
        row = website_settings_service.rollback(body.version, created_by=user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await audit_service.log(
        user_id=user.id, org_id=None, action="rollback", resource_type="website_settings",
        resource_id=str(row["version"]), details={"rolled_back_to": body.version, "new_version": row["version"]},
        request=request,
    )
    return {"data": {
        "version": row["version"], "settings": row["data"],
        "created_at": row.get("created_at"), "created_by": row.get("created_by"),
    }}


@router.get("/leads")
async def list_leads(
    stage: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    authorization: Optional[str] = Header(None),
):
    await get_website_editor(authorization)
    leads, total = website_leads_service.list_leads(stage=stage, source=source, q=q, limit=limit, offset=offset)
    return {"data": leads, "total": total}


@router.get("/leads/export.csv")
async def export_leads_csv(
    request: Request,
    stage: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=200, le=200),
    offset: int = Query(default=0, ge=0),
    authorization: Optional[str] = Header(None),
):
    user, _token = await get_current_admin(authorization)  # 🔒 admin only — 403 for marketing
    leads, _total = website_leads_service.list_leads(stage=stage, source=source, q=q, limit=limit, offset=offset)

    buffer = io.StringIO()
    fieldnames = [
        "id", "created_at", "source", "name", "email", "phone_e164", "company",
        "profile", "product_interest", "locale", "stage", "owner_user_id",
        "score", "next_action", "next_action_at", "lost_reason",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for lead in leads:
        writer.writerow(lead)

    await audit_service.log(
        user_id=user.id, org_id=None, action="export", resource_type="website_leads",
        details={"count": len(leads)}, request=request,
    )
    return Response(content=buffer.getvalue(), media_type="text/csv")


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str, authorization: Optional[str] = Header(None)):
    await get_website_editor(authorization)
    lead = website_leads_service.get_lead_with_activities(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    return {"data": lead}


@router.patch("/leads/{lead_id}")
async def patch_lead(lead_id: str, body: WebsiteLeadPatch, authorization: Optional[str] = Header(None)):
    user, _token, _role = await get_website_editor(authorization)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Nenhum campo para atualizar")

    lead = website_leads_service.patch_lead(lead_id, updates, actor=f"user:{user.id}")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    return {"data": lead}


@router.post("/leads/{lead_id}/activities", status_code=201)
async def create_lead_activity(
    lead_id: str, body: WebsiteLeadActivityCreate, authorization: Optional[str] = Header(None)
):
    user, _token, _role = await get_website_editor(authorization)
    activity = website_leads_service.add_activity(lead_id, body.kind, body.body, actor=f"user:{user.id}")
    if not activity:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    return {"data": activity}


@router.get("/stats")
async def get_stats(authorization: Optional[str] = Header(None)):
    await get_website_editor(authorization)
    return {"data": website_leads_service.get_stats()}
