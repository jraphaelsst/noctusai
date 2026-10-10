"""Pesquisa Extrair endpoints (pesquisa-wave2-contract.md section 3, #11-17)."""
# NOTE: no `from __future__ import annotations` here -- slowapi's @limiter.limit wrapper
# makes FastAPI resolve string annotations in slowapi's globals, turning body models
# into query params (422 "body: Field required").
import logging
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL
from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.primitives.responses import success_response

from app.config import settings
from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.schemas.pesquisa_extracao import ExtracaoCreate
from app.modules.media_creation.services.pesquisa_extracao_service import PesquisaExtracaoService
from app.modules.media_creation.services.pesquisa_extracao_worker import make_jobs_repository
from app.modules.media_creation.services.pesquisa_service import PesquisaError
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/media-creation/pesquisa", tags=["Media Creation — Pesquisa Extrair"]
)


def get_extracao_settings():
    """DI seam for the caps / hard switch. Tests override with a stub."""
    return settings


def get_extracao_jobs() -> JobRepository:
    """DI seam for the queue repo. Tests override with a ``FakeJobRepository``."""
    return make_jobs_repository(get_admin_client())


def _svc(auth, cfg, jobs: Optional[JobRepository] = None) -> PesquisaExtracaoService:
    user, _, org_id = auth
    return PesquisaExtracaoService(get_admin_client(), org_id, str(user.id), cfg=cfg, jobs=jobs)


def _raise(exc: PesquisaError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.get("/fontes")
async def list_fontes(
    marca_id: uuid.UUID, auth=Depends(get_current_user_org), cfg=Depends(get_extracao_settings),
):
    try:
        return success_response(_svc(auth, cfg).fontes(str(marca_id)))
    except PesquisaError as exc:
        _raise(exc)


@router.get("/fontes/posts")
async def list_fonte_posts(
    marca_id: uuid.UUID,
    kind: Literal["instagram_media", "youtube_video", "mc_post"],
    account_id: Optional[uuid.UUID] = None,
    cursor: Optional[str] = None,
    limit: int = Query(24, ge=1, le=50),
    busca: Optional[str] = Query(None, max_length=200),
    auth=Depends(get_current_user_org),
    cfg=Depends(get_extracao_settings),
):
    try:
        return success_response(
            _svc(auth, cfg).posts(
                str(marca_id), kind, account_id=str(account_id) if account_id else None,
                cursor=cursor, limit=limit, busca=busca,
            )
        )
    except PesquisaError as exc:
        _raise(exc)


@router.get("/extracoes/limites")
async def extracao_limites(
    marca_id: uuid.UUID, auth=Depends(get_current_user_org), cfg=Depends(get_extracao_settings),
):
    try:
        return success_response(_svc(auth, cfg).limits(str(marca_id)))
    except PesquisaError as exc:
        _raise(exc)


@router.post("/extracoes", status_code=202)
@limiter.limit(DEFAULT_AI_RL)
async def submit_extracao(
    request: Request,
    body: ExtracaoCreate,
    auth=Depends(get_current_user_org),
    cfg=Depends(get_extracao_settings),
    jobs: JobRepository = Depends(get_extracao_jobs),
):
    refs = [
        {"kind": p.kind, "account_id": str(p.account_id) if p.account_id else None, "id": p.id}
        for p in body.posts
    ]
    try:
        return success_response(
            await _svc(auth, cfg, jobs).submit(
                str(body.marca_id), list(body.tipos), refs, reextrair=body.reextrair
            )
        )
    except PesquisaError as exc:
        _raise(exc)


@router.get("/extracoes")
async def list_extracoes(
    marca_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=20),
    auth=Depends(get_current_user_org),
    cfg=Depends(get_extracao_settings),
):
    try:
        return success_response(_svc(auth, cfg).list_jobs(str(marca_id), limit))
    except PesquisaError as exc:
        _raise(exc)


@router.get("/extracoes/{extracao_id}")
async def get_extracao(
    extracao_id: uuid.UUID, auth=Depends(get_current_user_org), cfg=Depends(get_extracao_settings),
):
    try:
        return success_response(_svc(auth, cfg).get_job(str(extracao_id)))
    except PesquisaError as exc:
        _raise(exc)


@router.post("/extracoes/{extracao_id}/cancel")
async def cancel_extracao(
    extracao_id: uuid.UUID, auth=Depends(get_current_user_org), cfg=Depends(get_extracao_settings),
):
    try:
        return success_response(_svc(auth, cfg).cancel(str(extracao_id)))
    except PesquisaError as exc:
        _raise(exc)
