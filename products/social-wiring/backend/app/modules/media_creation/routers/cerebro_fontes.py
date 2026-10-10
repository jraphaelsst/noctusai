"""Segundo Cérebro sources: file import (14), YouTube import stub (15) and
Minhas extrações (19-24) — cerebro-contract.md §4.

NOTE: no `from __future__ import annotations` here -- slowapi's @limiter.limit wrapper
makes FastAPI resolve string annotations in slowapi's globals, turning the multipart/body
params into query params (422 "Field required").
"""
import logging
import uuid
from typing import Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile,
)

from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL
from noctusai_lib.integrations.documents.transcription import DocumentTranscriber
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.deps import get_cerebro_storage
from app.modules.media_creation.schemas.cerebro_fontes import (
    ExtractionApply,
    ExtractionCreate,
    ExtractionUpdate,
    YoutubeImportRequest,
)
from app.modules.media_creation.services.cerebro_fontes_service import (
    MAX_FILE_BYTES,
    MSG_YOUTUBE_UNAVAILABLE,
    CerebroFontesService,
)
from app.modules.media_creation.services.cerebro_service import CerebroError
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/media-creation/cerebro", tags=["Media Creation — Segundo Cérebro (fontes)"]
)

#: 🔴 THE APP REFUSES TO BOOT WITHOUT THIS ENTRY in `app.main._MAX_BODY_PATH_OVERRIDES`
#: (every mounted `UploadFile` route needs one). 20 MB file + multipart overhead.
MAX_BODY_PATH_OVERRIDES = {
    "/api/media-creation/cerebro/brains/*/imports/file": MAX_FILE_BYTES + 512 * 1024,
}


def get_cerebro_transcriber() -> Optional[DocumentTranscriber]:
    """DI seam for the PDF transcriber. ``None`` = the seed's real ladder
    transcriber (text layer first, vision per page). Tests override it."""
    return None


def _svc(auth, storage: Optional[StorageBackend] = None) -> CerebroFontesService:
    user, _, org_id = auth
    return CerebroFontesService(get_admin_client(), org_id, str(user.id), storage)


def _raise(exc: CerebroError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.post("/brains/{brain_id}/imports/file", status_code=202)
@limiter.limit(DEFAULT_AI_RL)
async def import_file(
    request: Request,
    brain_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_cerebro_storage),
    transcriber: Optional[DocumentTranscriber] = Depends(get_cerebro_transcriber),
):
    svc = _svc(auth, storage)
    content = await file.read(MAX_FILE_BYTES + 1)
    try:
        record = await svc.start_file_import(str(brain_id), file.filename or "", content)
    except CerebroError as exc:
        _raise(exc)
    background.add_task(
        svc.run_file_import, record["id"], str(brain_id), record["filename"], content, transcriber
    )
    return success_response(record)


@router.post("/brains/{brain_id}/imports/youtube")
async def import_youtube(
    brain_id: uuid.UUID, body: YoutubeImportRequest, auth=Depends(get_current_user_org)
):
    # NOC-REMEDIATE[youtube-import]: phase 2 (cerebro-contract.md §10.3) — downloader needs
    # SSRF guards, a duration pre-check and a security review. -- 2026-10-09
    try:
        _svc(auth).brains.get_brain_row(str(brain_id))
    except CerebroError as exc:
        _raise(exc)
    raise HTTPException(status_code=501, detail=MSG_YOUTUBE_UNAVAILABLE)


@router.get("/extracoes")
async def list_extracoes(
    marca_id: uuid.UUID,
    q: Optional[str] = Query(None, max_length=120),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    auth=Depends(get_current_user_org),
):
    try:
        return success_response(
            _svc(auth).list_extractions(str(marca_id), q=q, limit=limit, offset=offset)
        )
    except CerebroError as exc:
        _raise(exc)


@router.post("/extracoes", status_code=201)
async def create_extracao(body: ExtractionCreate, auth=Depends(get_current_user_org)):
    try:
        return success_response(
            _svc(auth).create_extraction(
                str(body.marca_id), body.name, [str(b) for b in body.brain_ids], body.text, body.url
            )
        )
    except CerebroError as exc:
        _raise(exc)


@router.get("/extracoes/{extraction_id}")
async def get_extracao(extraction_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).get_extraction(str(extraction_id)))
    except CerebroError as exc:
        _raise(exc)


@router.patch("/extracoes/{extraction_id}")
async def patch_extracao(
    extraction_id: uuid.UUID, body: ExtractionUpdate, auth=Depends(get_current_user_org)
):
    try:
        return success_response(
            _svc(auth).update_extraction(
                str(extraction_id), name=body.name, transcript=body.transcript,
                brain_ids=body.brain_ids,
            )
        )
    except CerebroError as exc:
        _raise(exc)


@router.post("/extracoes/{extraction_id}/apply")
async def apply_extracao(
    extraction_id: uuid.UUID, body: ExtractionApply, auth=Depends(get_current_user_org)
):
    try:
        return success_response(
            _svc(auth).apply_extraction(
                str(extraction_id),
                None if body.brain_ids is None else [str(b) for b in body.brain_ids],
            )
        )
    except CerebroError as exc:
        _raise(exc)


@router.delete("/extracoes/{extraction_id}", status_code=204)
async def delete_extracao(extraction_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        _svc(auth).delete_extraction(str(extraction_id))
    except CerebroError as exc:
        _raise(exc)
    return Response(status_code=204)
