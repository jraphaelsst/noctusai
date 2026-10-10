"""Segundo Cérebro endpoints — brains core (cerebro-contract.md §4, endpoints
1-12 and 16-18). File import / voice / extractions (13-15, 19-24) ship in the
sources slice.

``success_response`` carries no status code, so 201/202 are declared on the
route; foreign marca/brain/question -> 404, forbidden operation -> 409.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response

from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.deps import get_cerebro_storage
from app.modules.media_creation.schemas.cerebro import (
    AnswersReset,
    AnswerUpdate,
    BrainCreate,
    BrainRename,
    ContentUpdate,
    PerfilUpdate,
    ReviewRequest,
    SuggestionAction,
    SynthesizeRequest,
)
from app.modules.media_creation.services.cerebro_ai import CerebroLlm, get_cerebro_llm
from app.modules.media_creation.services.cerebro_service import CerebroError, CerebroService

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/media-creation/cerebro", tags=["Media Creation — Segundo Cérebro"]
)


def _svc(auth, storage: StorageBackend | None = None) -> CerebroService:
    user, _, org_id = auth
    return CerebroService(get_admin_client(), org_id, str(user.id), storage)


def _raise(exc: CerebroError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.get("/templates")
async def list_templates(auth=Depends(get_current_user_org)):
    return success_response(_svc(auth).list_templates())


@router.get("/brains")
async def list_brains(marca_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).list_brains(str(marca_id)))
    except CerebroError as exc:
        _raise(exc)


@router.post("/brains", status_code=201)
async def create_brain(body: BrainCreate, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).create_brain(str(body.marca_id), body.name))
    except CerebroError as exc:
        _raise(exc)


@router.get("/brains/{brain_id}")
async def get_brain(brain_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).get_brain(str(brain_id)))
    except CerebroError as exc:
        _raise(exc)


@router.patch("/brains/{brain_id}")
async def rename_brain(brain_id: uuid.UUID, body: BrainRename, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).rename_brain(str(brain_id), body.name))
    except CerebroError as exc:
        _raise(exc)


@router.delete("/brains/{brain_id}", status_code=204)
async def delete_brain(
    brain_id: uuid.UUID,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_cerebro_storage),
):
    try:
        await _svc(auth, storage).delete_brain(str(brain_id))
    except CerebroError as exc:
        _raise(exc)
    return Response(status_code=204)


@router.put("/brains/{brain_id}/content")
async def put_content(brain_id: uuid.UUID, body: ContentUpdate, auth=Depends(get_current_user_org)):
    try:
        return success_response(
            _svc(auth).update_content(str(brain_id), body.content, body.expected_version)
        )
    except CerebroError as exc:
        _raise(exc)


@router.post("/brains/{brain_id}/answers/reset")
async def reset_answers(brain_id: uuid.UUID, body: AnswersReset, auth=Depends(get_current_user_org)):
    try:
        return success_response({"deleted": _svc(auth).reset_answers(str(brain_id))})
    except CerebroError as exc:
        _raise(exc)


@router.put("/brains/{brain_id}/answers/{question_id}")
async def put_answer(
    brain_id: uuid.UUID, question_id: str, body: AnswerUpdate, auth=Depends(get_current_user_org)
):
    try:
        return success_response(_svc(auth).put_answer(str(brain_id), question_id, body.text))
    except CerebroError as exc:
        _raise(exc)


@router.post("/brains/{brain_id}/review", status_code=202)
async def review(
    brain_id: uuid.UUID,
    body: ReviewRequest,
    background: BackgroundTasks,
    auth=Depends(get_current_user_org),
    llm: CerebroLlm = Depends(get_cerebro_llm),
):
    svc = _svc(auth)
    try:
        targets = svc.request_review(str(brain_id), body.question_ids)
    except CerebroError as exc:
        _raise(exc)
    background.add_task(svc.run_review, str(brain_id), targets, llm)
    return success_response({"queued": len(targets)})


@router.post("/brains/{brain_id}/answers/{question_id}/suggestion")
async def suggestion(
    brain_id: uuid.UUID, question_id: str, body: SuggestionAction, auth=Depends(get_current_user_org)
):
    try:
        return success_response(
            _svc(auth).apply_suggestion(str(brain_id), question_id, body.action)
        )
    except CerebroError as exc:
        _raise(exc)


@router.post("/brains/{brain_id}/synthesize", status_code=202)
async def synthesize(
    brain_id: uuid.UUID,
    body: SynthesizeRequest,
    background: BackgroundTasks,
    auth=Depends(get_current_user_org),
    llm: CerebroLlm = Depends(get_cerebro_llm),
):
    svc = _svc(auth)
    try:
        brain = svc.start_synthesis(str(brain_id), body.mode, body.expected_version)
    except CerebroError as exc:
        _raise(exc)
    background.add_task(svc.run_synthesis, str(brain_id), body.mode, body.expected_version, llm)
    return success_response({"brain": brain})


@router.get("/brains/{brain_id}/imports")
async def list_imports(
    brain_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    auth=Depends(get_current_user_org),
):
    try:
        return success_response(_svc(auth).list_imports(str(brain_id), limit=limit))
    except CerebroError as exc:
        _raise(exc)


@router.get("/perfil")
async def get_perfil(marca_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).get_perfil(str(marca_id)))
    except CerebroError as exc:
        _raise(exc)


@router.put("/perfil")
async def put_perfil(body: PerfilUpdate, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).put_perfil(str(body.marca_id), body.bio))
    except CerebroError as exc:
        _raise(exc)
