"""Assuntos Virais endpoints — per-marca viral topics (pesquisa-wave2-contract.md section 3)."""
from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.schemas.assuntos_virais import (
    AssuntosBulk,
    AssuntosCreate,
    AssuntosEmpty,
)
from app.modules.media_creation.services.assuntos_virais_service import (
    AssuntosViraisService,
)
from app.modules.media_creation.services.pesquisa_service import PesquisaError

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/media-creation/pesquisa/assuntos-virais",
    tags=["Media Creation — Assuntos Virais"],
)


def _svc(auth) -> AssuntosViraisService:
    user, _, org_id = auth
    return AssuntosViraisService(get_admin_client(), org_id, str(user.id))


def _raise(exc: PesquisaError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.get("")
async def list_assuntos(
    marca_id: uuid.UUID,
    status: Literal["approved", "pending"] = "approved",
    sort: Literal["plays", "recent"] = "plays",
    limit: int = Query(54, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth=Depends(get_current_user_org),
):
    try:
        return success_response(
            _svc(auth).list_topics(str(marca_id), status=status, sort=sort, limit=limit, offset=offset)
        )
    except PesquisaError as exc:
        _raise(exc)


@router.get("/counts")
async def assuntos_counts(marca_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).counts(str(marca_id)))
    except PesquisaError as exc:
        _raise(exc)


@router.post("")
async def create_assuntos(body: AssuntosCreate, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).add_manual(str(body.marca_id), body.topics))
    except PesquisaError as exc:
        _raise(exc)


@router.post("/bulk")
async def bulk_assuntos(body: AssuntosBulk, auth=Depends(get_current_user_org)):
    try:
        n = _svc(auth).bulk(str(body.marca_id), body.action, [str(i) for i in body.ids])
        return success_response({"affected": n})
    except PesquisaError as exc:
        _raise(exc)


@router.post("/empty")
async def empty_assuntos(body: AssuntosEmpty, auth=Depends(get_current_user_org)):
    try:
        return success_response({"deleted": _svc(auth).empty(str(body.marca_id), body.status)})
    except PesquisaError as exc:
        _raise(exc)


@router.post("/{topic_id}/approve")
async def approve_assunto(topic_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).approve(str(topic_id)))
    except PesquisaError as exc:
        _raise(exc)


@router.post("/{topic_id}/reject")
async def reject_assunto(topic_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).reject(str(topic_id)))
    except PesquisaError as exc:
        _raise(exc)


@router.delete("/{topic_id}", status_code=204)
async def delete_assunto(topic_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        _svc(auth).delete(str(topic_id))
    except PesquisaError as exc:
        _raise(exc)
    return Response(status_code=204)


@router.get("/{topic_id}/fontes")
async def assunto_fontes(topic_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).list_sources(str(topic_id)))
    except PesquisaError as exc:
        _raise(exc)
