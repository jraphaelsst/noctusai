"""
Brand Router — org brand identity (CONTRACT projects/org-brand-identity §3).

GET    /api/brand/current                  — any authenticated user; selected org (X-Noctus-Acting-Org,
                                             narrow-only) → org identity or the NOC standard. ETag/304.
                                             Never returns voice / source / brand_book.
GET    /api/brand/identities               — settings:manage — version list (no voice)
GET    /api/brand/identities/{id}          — settings:manage — full row
POST   /api/brand/identities/ingest        — settings:manage — multipart files[] + descriptions → 202 {job_id}
GET    /api/brand/jobs/{job_id}            — settings:manage — queued|running|done|failed
PATCH  /api/brand/identities/{id}          — settings:manage, draft only — {tokens?, brand_book?, voice?}
POST   /api/brand/identities/{id}/activate — settings:manage — previous active → archived (rollback too)
POST   /api/brand/identities/{id}/assets   — settings:manage, draft only — multipart slot + file

Auth runs FIRST on every route (a sub-dependency resolved before any body
field is validated), so an unauthenticated call is a strict 401, never a 422.
Cross-org ids are 404 (rows are read with the org in the query).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.schemas.brand import BrandIdentityPatch
from app.services.brand import uploads as U
from app.services.brand.extraction import BrandVoice
from app.services.brand.wiring import BrandRuntime, get_runtime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/brand", tags=["Brand"])

ACTING_HEADER = "X-Noctus-Acting-Org"
#: MaxBodySizeMiddleware ceilings — wired in app.main `max_body_path_overrides`.
BODY_LIMITS = {
    "/api/brand/identities/ingest": U.INGEST_BODY_LIMIT,
    "/api/brand/identities/*/assets": U.ASSET_BODY_LIMIT,
}


async def _authenticated(
    request: Request,
    authorization: Optional[str] = Header(None),
    runtime: BrandRuntime = Depends(get_runtime),
) -> tuple:
    user, token = await runtime.authenticate(authorization, request)
    return user, token


def _refused(exc: U.UploadRefused) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": exc.codigo, "detail": exc.message})


async def _manager(request: Request, auth: tuple, runtime: BrandRuntime):
    user, token = auth
    return await runtime.service.manager(user, token, request.headers.get(ACTING_HEADER))


@router.get("/current")
async def brand_current(
    request: Request,
    response: Response,
    auth: tuple = Depends(_authenticated),
    runtime: BrandRuntime = Depends(get_runtime),
):
    user, token = auth
    caller = await runtime.service.reader(user, token, request.headers.get(ACTING_HEADER))
    body, etag = await runtime.service.current(caller)
    headers = {"ETag": etag, "Cache-Control": "private, no-cache", "Vary": f"Authorization, {ACTING_HEADER}"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return body


@router.get("/identities")
async def brand_list(request: Request, auth: tuple = Depends(_authenticated),
                     runtime: BrandRuntime = Depends(get_runtime)):
    caller = await _manager(request, auth, runtime)
    return {"data": await runtime.service.list_identities(caller)}


@router.get("/identities/{identity_id}")
async def brand_get(identity_id: str, request: Request, auth: tuple = Depends(_authenticated),
                    runtime: BrandRuntime = Depends(get_runtime)):
    caller = await _manager(request, auth, runtime)
    return {"data": await runtime.service.get_identity(caller, identity_id)}


@router.post("/identities/ingest", status_code=202)
async def brand_ingest(
    request: Request,
    files: Optional[list[UploadFile]] = File(None),
    descriptions: Optional[str] = Form(None),
    auth: tuple = Depends(_authenticated),
    runtime: BrandRuntime = Depends(get_runtime),
):
    caller = await _manager(request, auth, runtime)
    if not runtime.ingest_limit.allow(caller.org_id):
        raise HTTPException(status_code=429, detail={"code": "limite_ingestao",
                                                     "detail": "Limite de envios por hora atingido"})
    try:
        if files and len(files) > U.MAX_FILES:
            raise U.UploadRefused("arquivos_demais", f"No máximo {U.MAX_FILES} arquivos")
        raw = [(f.filename, await U.read_capped(f)) for f in (files or [])]
        accepted = U.check_batch(raw)
        desc = U.parse_descriptions(descriptions, [a.name for a in accepted])
    except U.UploadRefused as exc:
        raise _refused(exc)
    return await runtime.service.ingest(caller, accepted, desc)


@router.get("/jobs/{job_id}")
async def brand_job(job_id: str, request: Request, auth: tuple = Depends(_authenticated),
                    runtime: BrandRuntime = Depends(get_runtime)):
    caller = await _manager(request, auth, runtime)
    return await runtime.service.job_status(caller, job_id)


@router.patch("/identities/{identity_id}")
async def brand_patch(identity_id: str, request: Request, auth: tuple = Depends(_authenticated),
                      runtime: BrandRuntime = Depends(get_runtime)):
    caller = await _manager(request, auth, runtime)
    try:
        body = BrandIdentityPatch.model_validate(await request.json())
    except ValueError as exc:  # JSON decode error or pydantic ValidationError (a ValueError)
        errors = exc.errors() if isinstance(exc, ValidationError) else [
            {"type": "json_invalid", "loc": ("body",), "msg": "JSON inválido", "input": None}]
        raise RequestValidationError(errors)
    voice = BrandVoice.model_validate(body.voice.model_dump()) if body.voice is not None else None
    data = await runtime.service.patch(caller, identity_id, tokens=body.tokens,
                                       brand_book=body.brand_book, voice=voice)
    return {"data": data}


@router.post("/identities/{identity_id}/activate")
async def brand_activate(identity_id: str, request: Request, auth: tuple = Depends(_authenticated),
                         runtime: BrandRuntime = Depends(get_runtime)):
    caller = await _manager(request, auth, runtime)
    return {"data": await runtime.service.activate(caller, identity_id)}


@router.post("/identities/{identity_id}/assets")
async def brand_asset(
    identity_id: str,
    request: Request,
    file: Optional[UploadFile] = File(None),
    slot: Optional[str] = Form(None),
    family: Optional[str] = Form(None),
    auth: tuple = Depends(_authenticated),
    runtime: BrandRuntime = Depends(get_runtime),
):
    caller = await _manager(request, auth, runtime)
    if file is None or not slot:
        raise HTTPException(status_code=422, detail={"code": "campos_obrigatorios", "detail": "file e slot são obrigatórios"})
    try:
        accepted = U.classify(file.filename, await U.read_capped(file))
    except U.UploadRefused as exc:
        raise _refused(exc)
    data = await runtime.service.upload_asset(caller, identity_id, slot=slot, file=accepted, family=family)
    return {"data": data}
