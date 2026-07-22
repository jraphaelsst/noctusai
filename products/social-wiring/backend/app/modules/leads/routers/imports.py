"""Import — /api/leads/import/*. ``preview`` parses + resolves against
the org's CURRENT alias map and writes nothing; ``commit`` parses,
ensures the org's canonical dimensions exist, and upserts (idempotent on
``(org_id, source_sheet, source_row)``).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile

from noctusai_lib.primitives.exceptions import ValidationError_
from noctusai_lib.primitives.responses import paginated_response, success_response

from app.dependencies import coerce_org_uuid, get_current_user_org_unified
from app.modules.leads.deps import get_leads_client
from app.modules.leads.importer import import_service

router = APIRouter(prefix="/api/leads/import", tags=["leads-import"])


@router.get("/batches")
def list_batches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    rows, total = import_service.list_batches(client, org_id, page=page, page_size=page_size)
    return paginated_response(rows, total, page, page_size)


@router.post("/preview")
async def preview_import(
    file: UploadFile = File(...),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    if not file.filename:
        raise ValidationError_("upload missing filename", field="file")
    content = await file.read()
    result = import_service.preview(client, org_id, content, file.filename)
    return success_response(result)


@router.post("/commit", status_code=201)
async def commit_import(
    file: UploadFile = File(...),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    if not file.filename:
        raise ValidationError_("upload missing filename", field="file")
    content = await file.read()
    created_by = getattr(user, "id", None)
    result = import_service.commit(client, org_id, content, file.filename, created_by=created_by)
    return success_response(result)


__all__ = ["router"]
