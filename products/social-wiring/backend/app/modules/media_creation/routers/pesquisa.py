"""Minha Pesquisa endpoints — per-marca research items (pesquisa-contract.md §3)."""
# NOTE: no `from __future__ import annotations` here -- slowapi's @limiter.limit wrapper
# makes FastAPI resolve string annotations in slowapi's globals, turning body models
# into query params (422 "body: Field required").
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.rate_limit import limiter
from app.modules.media_creation.schemas.pesquisa import (
    ItemsBulk,
    ItemsClassify,
    ItemsCreate,
    ItemsEmpty,
)
from app.modules.media_creation.services.pesquisa_service import (
    PesquisaError,
    PesquisaLlm,
    PesquisaService,
    chat_pesquisa_llm,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/media-creation/pesquisa", tags=["Media Creation — Pesquisa"]
)


def get_pesquisa_llm() -> PesquisaLlm:
    """DI seam for the classifier LLM. Tests override with a fake callable."""
    return chat_pesquisa_llm


def _svc(auth) -> PesquisaService:
    user, _, org_id = auth
    return PesquisaService(get_admin_client(), org_id, str(user.id))


def _raise(exc: PesquisaError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.get("/variables")
async def list_variables(auth=Depends(get_current_user_org)):
    return success_response(_svc(auth).list_variables())


@router.get("/items")
async def list_items(
    marca_id: uuid.UUID,
    status: Literal["approved", "pending"] = "approved",
    variable_slug: str | None = None,
    sort: Literal["recent", "plays"] = "recent",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth=Depends(get_current_user_org),
):
    try:
        return success_response(
            _svc(auth).list_items(
                str(marca_id), status=status, variable_slug=variable_slug,
                sort=sort, limit=limit, offset=offset,
            )
        )
    except PesquisaError as exc:
        _raise(exc)


@router.get("/items/counts")
async def items_counts(marca_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).counts(str(marca_id)))
    except PesquisaError as exc:
        _raise(exc)


@router.post("/items")
async def create_items(body: ItemsCreate, auth=Depends(get_current_user_org)):
    try:
        return success_response(
            _svc(auth).add_manual(str(body.marca_id), body.variable_slug, body.lines)
        )
    except PesquisaError as exc:
        _raise(exc)


@router.post("/items/classify")
@limiter.limit(DEFAULT_AI_RL)
async def classify_items(
    request: Request,
    body: ItemsClassify,
    auth=Depends(get_current_user_org),
    llm: PesquisaLlm = Depends(get_pesquisa_llm),
):
    try:
        return success_response(await _svc(auth).classify(str(body.marca_id), body.text, llm))
    except PesquisaError as exc:
        _raise(exc)


@router.post("/items/bulk")
async def bulk_items(body: ItemsBulk, auth=Depends(get_current_user_org)):
    try:
        n = _svc(auth).bulk(str(body.marca_id), body.action, [str(i) for i in body.ids])
        return success_response({"affected": n})
    except PesquisaError as exc:
        _raise(exc)


@router.post("/items/empty")
async def empty_items(body: ItemsEmpty, auth=Depends(get_current_user_org)):
    try:
        return success_response({"deleted": _svc(auth).empty(str(body.marca_id))})
    except PesquisaError as exc:
        _raise(exc)


@router.post("/items/{item_id}/approve")
async def approve_item(item_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).approve(str(item_id)))
    except PesquisaError as exc:
        _raise(exc)


@router.post("/items/{item_id}/reject")
async def reject_item(item_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).reject(str(item_id)))
    except PesquisaError as exc:
        _raise(exc)


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        _svc(auth).delete(str(item_id))
    except PesquisaError as exc:
        _raise(exc)
    return Response(status_code=204)
