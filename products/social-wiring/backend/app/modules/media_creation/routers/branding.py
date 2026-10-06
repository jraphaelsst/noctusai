"""Branding endpoints — the richer brand-kit model (tokens, brand book,
components, assets), grouped by marca.

- GET    /api/media-creation/branding                      — brandings grouped by marca (+ template, + unassigned)
- POST   /api/media-creation/branding                      — create (optionally from the Branding Template)
- POST   /api/media-creation/branding/import               — create/update from a design-system folder
- GET    /api/media-creation/branding/{id}                 — full branding (tokens, book, components, assets + signed URLs)
- PATCH  /api/media-creation/branding/{id}                 — edit
- DELETE /api/media-creation/branding/{id}                 — remove (template is protected)
- PUT    /api/media-creation/branding/{id}/components      — upsert a component by name
- DELETE /api/media-creation/branding/components/{cid}     — remove a component
- POST   /api/media-creation/branding/{id}/assets          — upload a logo / post model / font (base64 JSON)

Asset rows are deleted through ``DELETE /api/media-creation/references/{id}``
(the existing references route, which now also removes the blob).

There is NO catalog seeding route: the repo catalog and ``seed-catalog`` were
removed (owner decision 2026-10-05) — brandings live in the database.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.deps import get_branding_storage
from app.modules.media_creation.schemas.branding import (
    AssetUpload,
    BrandingCreate,
    BrandingImport,
    BrandingUpdate,
    ComponentUpsert,
)
from app.modules.media_creation.services.branding_service import (
    BrandingError,
    BrandingService,
    decode_b64,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/media-creation/branding",
    tags=["Media Creation — Branding"],
)


def _svc(org_id, storage: StorageBackend) -> BrandingService:
    return BrandingService(get_admin_client(), org_id, storage)


def _http(exc: BrandingError) -> HTTPException:
    """One problem -> plain string detail; a list of problems (a bundle that
    failed validation) -> the seed error shape ``{detail, code, errors}`` (passed
    through flat by the seed handler, so the UI can list every problem)."""
    if exc.errors:
        return HTTPException(
            status_code=exc.status,
            detail={"detail": str(exc.args[0]), "code": "branding_invalid", "errors": exc.errors},
        )
    return HTTPException(status_code=exc.status, detail=str(exc))


@router.get("")
async def list_brandings(
    auth=Depends(get_current_user_org), storage: StorageBackend = Depends(get_branding_storage)
):
    user, _, org_id = auth
    return success_response(_svc(org_id, storage).overview())


@router.post("", status_code=201)
async def create_branding(
    body: BrandingCreate,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_branding_storage),
):
    user, _, org_id = auth
    try:
        return success_response(await _svc(org_id, storage).create(body.model_dump(), str(user.id)))
    except BrandingError as exc:
        raise _http(exc) from exc


@router.post("/import", status_code=201)
async def import_design_system(
    body: BrandingImport,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_branding_storage),
):
    """Create or update a branding from a design-system folder's files."""
    user, _, org_id = auth
    try:
        files = [(f.path, decode_b64(f.content_base64, where=f.path)) for f in body.files]
        result = await _svc(org_id, storage).import_bundle(
            files=files,
            marca_id=body.marca_id,
            is_template=body.is_template,
            name=body.name,
            user_id=str(user.id),
        )
    except BrandingError as exc:
        raise _http(exc) from exc
    logger.info(
        "branding: import %s id=%s components=%d assets=%d",
        result["action"], result["id"], result["components"], result["assets"],
    )
    return success_response(result)


@router.get("/{kit_id}")
async def get_branding(
    kit_id: str,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_branding_storage),
):
    user, _, org_id = auth
    try:
        return success_response(await _svc(org_id, storage).detail(kit_id))
    except BrandingError as exc:
        raise _http(exc) from exc


@router.patch("/{kit_id}")
async def update_branding(
    kit_id: str,
    body: BrandingUpdate,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_branding_storage),
):
    user, _, org_id = auth
    try:
        return success_response(
            await _svc(org_id, storage).update(kit_id, body.model_dump(exclude_unset=True))
        )
    except BrandingError as exc:
        raise _http(exc) from exc


@router.delete("/components/{component_id}")
async def delete_component(
    component_id: str,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_branding_storage),
):
    user, _, org_id = auth
    try:
        _svc(org_id, storage).delete_component(component_id)
    except BrandingError as exc:
        raise _http(exc) from exc
    return {"ok": True, "message": "Componente removido"}


@router.delete("/{kit_id}")
async def delete_branding(
    kit_id: str,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_branding_storage),
):
    user, _, org_id = auth
    try:
        result = await _svc(org_id, storage).delete(kit_id)
    except BrandingError as exc:
        raise _http(exc) from exc
    return {"ok": True, "message": "Branding removido", **result}


@router.put("/{kit_id}/components")
async def upsert_component(
    kit_id: str,
    body: ComponentUpsert,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_branding_storage),
):
    user, _, org_id = auth
    try:
        return success_response(_svc(org_id, storage).upsert_component(kit_id, body.model_dump()))
    except BrandingError as exc:
        raise _http(exc) from exc


@router.post("/{kit_id}/assets", status_code=201)
async def upload_asset(
    kit_id: str,
    body: AssetUpload,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_branding_storage),
):
    user, _, org_id = auth
    try:
        data = decode_b64(body.content_base64, where=body.label)
        row = await _svc(org_id, storage).add_asset(kit_id, body.kind, body.label, data, body.notes)
    except BrandingError as exc:
        raise _http(exc) from exc
    return success_response(row)
