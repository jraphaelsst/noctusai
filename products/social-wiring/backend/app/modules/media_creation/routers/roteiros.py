"""Roteiros (Roteiro Avançado) endpoints (geracao-contract.md section 4.5, #32-#40).

Prefix ``/api/media-creation``, auth ``get_current_user_org``, ``success_response`` envelope.
A foreign marca / roteiro / brain / viral / headline is a 404 (never 403); a forbidden state is a
409; the daily cap is a 429 with ``Retry-After``; no worker / no AI key is a 503 ``{code}``.
"""
# NOTE: no `from __future__ import annotations` here -- slowapi's @limiter.limit wrapper
# makes FastAPI resolve string annotations in slowapi's globals, turning body models
# into query params (422 "body: Field required").
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL
from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.config import settings
from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.deps import get_cerebro_storage
from app.modules.media_creation.schemas.roteiros import (
    ExcluirRequest,
    FeedbackRequest,
    GerarRequest,
    ReprocessarRequest,
    RespostasUpdate,
    RoteiroCreate,
    RoteiroUpdate,
)
from app.modules.media_creation.services.geracao_jobs import make_jobs_repository
from app.modules.media_creation.services.roteiro_service import (
    IaCheck,
    RoteiroError,
    RoteiroService,
    get_roteiro_ia_check,
)
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation/roteiros", tags=["Media Creation — Roteiros"])


def get_roteiro_settings():
    """DI seam for the caps / model. Tests override with a stub."""
    return settings


def get_roteiro_jobs() -> JobRepository:
    """DI seam for the queue repo. Tests override with a ``FakeJobRepository``."""
    return make_jobs_repository(get_admin_client())


def get_roteiro_storage() -> StorageBackend:
    """Blob storage used only to sign the viral thumbnail. Tests override with a ``FakeStorageBackend``."""
    return get_cerebro_storage()


def _svc(
    auth, cfg, jobs: Optional[JobRepository] = None, ia_check: Optional[IaCheck] = None,
    storage: Optional[StorageBackend] = None,
) -> RoteiroService:
    user, _, org_id = auth
    kwargs = {"ia_check": ia_check} if ia_check is not None else {}
    return RoteiroService(get_admin_client(), org_id, str(user.id), cfg=cfg, jobs=jobs, storage=storage, **kwargs)


def _raise(exc: RoteiroError):
    raise HTTPException(status_code=exc.status, detail=exc.detail, headers=exc.headers) from exc


@router.post("", status_code=202)
@limiter.limit(DEFAULT_AI_RL)
async def criar_roteiro(
    request: Request,
    body: RoteiroCreate,
    auth=Depends(get_current_user_org),
    cfg=Depends(get_roteiro_settings),
    storage: StorageBackend = Depends(get_roteiro_storage),
    jobs: JobRepository = Depends(get_roteiro_jobs),
    ia_check: IaCheck = Depends(get_roteiro_ia_check),
):
    try:
        return success_response(await _svc(auth, cfg, jobs, ia_check, storage).create(body))
    except RoteiroError as exc:
        _raise(exc)


@router.get("")
async def listar_roteiros(
    marca_id: uuid.UUID,
    q: Optional[str] = Query(None, max_length=200),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    auth=Depends(get_current_user_org),
    cfg=Depends(get_roteiro_settings),
):
    try:
        return success_response(_svc(auth, cfg).list(str(marca_id), q=q, limit=limit, offset=offset))
    except RoteiroError as exc:
        _raise(exc)


@router.post("/excluir")
async def excluir_roteiros(
    body: ExcluirRequest, auth=Depends(get_current_user_org), cfg=Depends(get_roteiro_settings),
):
    try:
        return success_response(_svc(auth, cfg).excluir([str(i) for i in body.ids]))
    except RoteiroError as exc:
        _raise(exc)


@router.get("/{roteiro_id}")
async def obter_roteiro(
    roteiro_id: uuid.UUID, auth=Depends(get_current_user_org), cfg=Depends(get_roteiro_settings),
    storage: StorageBackend = Depends(get_roteiro_storage),
):
    try:
        return success_response(await _svc(auth, cfg, storage=storage).get(str(roteiro_id)))
    except RoteiroError as exc:
        _raise(exc)


@router.put("/{roteiro_id}/perguntas")
async def responder_perguntas(
    roteiro_id: uuid.UUID,
    body: RespostasUpdate,
    auth=Depends(get_current_user_org),
    cfg=Depends(get_roteiro_settings),
    storage: StorageBackend = Depends(get_roteiro_storage),
):
    try:
        return success_response(await _svc(auth, cfg, storage=storage).responder(str(roteiro_id), body.respostas))
    except RoteiroError as exc:
        _raise(exc)


@router.post("/{roteiro_id}/gerar", status_code=202)
@limiter.limit(DEFAULT_AI_RL)
async def gerar_roteiro(
    request: Request,
    roteiro_id: uuid.UUID,
    body: GerarRequest,
    auth=Depends(get_current_user_org),
    cfg=Depends(get_roteiro_settings),
    storage: StorageBackend = Depends(get_roteiro_storage),
    jobs: JobRepository = Depends(get_roteiro_jobs),
    ia_check: IaCheck = Depends(get_roteiro_ia_check),
):
    try:
        return success_response(
            await _svc(auth, cfg, jobs, ia_check, storage).gerar(str(roteiro_id), pular_perguntas=body.pular_perguntas)
        )
    except RoteiroError as exc:
        _raise(exc)


@router.put("/{roteiro_id}")
async def salvar_roteiro(
    roteiro_id: uuid.UUID,
    body: RoteiroUpdate,
    auth=Depends(get_current_user_org),
    cfg=Depends(get_roteiro_settings),
    storage: StorageBackend = Depends(get_roteiro_storage),
):
    try:
        return success_response(await _svc(auth, cfg, storage=storage).salvar(str(roteiro_id), body))
    except RoteiroError as exc:
        _raise(exc)


@router.post("/{roteiro_id}/feedback")
async def feedback_roteiro(
    roteiro_id: uuid.UUID,
    body: FeedbackRequest,
    auth=Depends(get_current_user_org),
    cfg=Depends(get_roteiro_settings),
    storage: StorageBackend = Depends(get_roteiro_storage),
):
    try:
        return success_response(await _svc(auth, cfg, storage=storage).feedback(str(roteiro_id), body.feedback, body.motivo))
    except RoteiroError as exc:
        _raise(exc)


@router.post("/{roteiro_id}/reprocessar", status_code=202)
@limiter.limit(DEFAULT_AI_RL)
async def reprocessar_roteiro(
    request: Request,
    roteiro_id: uuid.UUID,
    body: ReprocessarRequest,
    auth=Depends(get_current_user_org),
    cfg=Depends(get_roteiro_settings),
    storage: StorageBackend = Depends(get_roteiro_storage),
    jobs: JobRepository = Depends(get_roteiro_jobs),
    ia_check: IaCheck = Depends(get_roteiro_ia_check),
):
    try:
        return success_response(
            await _svc(auth, cfg, jobs, ia_check, storage).reprocessar(str(roteiro_id), body.instrucoes_adicionais)
        )
    except RoteiroError as exc:
        _raise(exc)
