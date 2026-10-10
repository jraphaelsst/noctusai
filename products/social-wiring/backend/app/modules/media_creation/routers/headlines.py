"""Headlines endpoints (Geração, BE-4): contract ``specs/geracao-contract.md`` section 4.4 #20-31.

NOTE: no ``from __future__ import annotations`` here -- slowapi's ``@limiter.limit`` wrapper makes
FastAPI resolve string annotations in slowapi's globals, turning body models into query params
(422 "body: Field required").

Static paths (``/lotes``, ``/estruturas/contagem``, ``/excluir``, ``/sugestoes/gerar-agora``) are
declared BEFORE the ``/{headline_id}`` routes. ``success_response`` carries no status code, so
201/202 are declared on the route; a foreign / unknown id is 404, a forbidden state 409, caps 429
with ``Retry-After``, an unavailable worker or AI 503.
"""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL
from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.llm import LLMNotConfigured
from noctusai_lib.integrations.llm.client import resolve_api_key
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.config import settings
from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.deps import get_cerebro_storage
from app.modules.media_creation.schemas.headlines import (
    HeadlineCreate,
    HeadlineEdit,
    IdsBody,
    LoteCreate,
    SugestaoAgora,
)
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.headline_service import HeadlineError, HeadlineService
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation/headlines", tags=["Media Creation — Headlines"])


def get_headline_settings():
    """DI seam for the caps / hard switch. Tests override with a stub."""
    return settings


def get_headline_jobs() -> JobRepository:
    """DI seam for the queue repo. Tests override with a ``FakeJobRepository``."""
    return geracao_jobs.make_jobs_repository(get_admin_client())


def get_headline_storage() -> StorageBackend:
    """DI seam for thumbnail signing (the private library bucket). Same resolution as the other
    media_creation storage seams; tests override with a ``FakeStorageBackend``."""
    return get_cerebro_storage()


def get_ia_check():
    """DI seam: ``(org_id) -> None``, raising ``LLMNotConfigured`` when the org cannot call Anthropic.
    Tests override with a no-op; production resolves the org's key (DB first, then env)."""

    def check(org_id: str) -> None:
        resolve_api_key("anthropic", org_id)

    return check


def _svc(auth, cfg=None, jobs: Optional[JobRepository] = None, storage: Optional[StorageBackend] = None) -> HeadlineService:
    user, _, org_id = auth
    return HeadlineService(get_admin_client(), org_id, str(user.id), cfg=cfg, jobs=jobs, storage=storage)


def _raise(exc: HeadlineError):
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    raise HTTPException(status_code=exc.status, detail=exc.detail, headers=headers) from exc


def _assert_ia(auth, check) -> None:
    try:
        check(auth[2])
    except LLMNotConfigured as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "ia_nao_configurada", "message": "A IA não está configurada para esta organização."},
        ) from exc


# ── batches ─────────────────────────────────────────────────────────────────


@router.post("/lotes", status_code=202)
@limiter.limit(DEFAULT_AI_RL)
async def create_lote(
    request: Request,
    body: LoteCreate,
    auth=Depends(get_current_user_org),
    cfg=Depends(get_headline_settings),
    jobs: JobRepository = Depends(get_headline_jobs),
    ia_check=Depends(get_ia_check),
):
    geracao_jobs.assert_geracao_disponivel(cfg)
    _assert_ia(auth, ia_check)
    await geracao_jobs.assert_orcamento_ia(auth[2])
    try:
        return success_response(await _svc(auth, cfg, jobs).create_lote(body.model_dump(mode="json")))
    except HeadlineError as exc:
        _raise(exc)


@router.get("/lotes")
async def list_lotes(
    marca_id: uuid.UUID,
    origem_in: Optional[list[str]] = Query(None),
    q: Optional[str] = Query(None, max_length=200),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    auth=Depends(get_current_user_org),
    cfg=Depends(get_headline_settings),
):
    try:
        return success_response(
            _svc(auth, cfg).list_lotes(str(marca_id), origem_in=origem_in, q=q, limit=limit, offset=offset)
        )
    except HeadlineError as exc:
        _raise(exc)


@router.post("/lotes/excluir")
async def excluir_lotes(body: IdsBody, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).excluir_lotes([str(i) for i in body.ids]))
    except HeadlineError as exc:
        _raise(exc)


@router.get("/lotes/{lote_id}")
async def get_lote(
    lote_id: uuid.UUID, auth=Depends(get_current_user_org), storage: StorageBackend = Depends(get_headline_storage),
):
    try:
        return success_response(await _svc(auth, storage=storage).get_lote(str(lote_id)))
    except HeadlineError as exc:
        _raise(exc)


@router.post("/lotes/{lote_id}/reprocessar", status_code=202)
@limiter.limit(DEFAULT_AI_RL)
async def reprocessar_lote(
    request: Request,
    lote_id: uuid.UUID,
    auth=Depends(get_current_user_org),
    cfg=Depends(get_headline_settings),
    jobs: JobRepository = Depends(get_headline_jobs),
    ia_check=Depends(get_ia_check),
):
    geracao_jobs.assert_geracao_disponivel(cfg)
    _assert_ia(auth, ia_check)
    await geracao_jobs.assert_orcamento_ia(auth[2])
    try:
        return success_response(await _svc(auth, cfg, jobs).reprocessar(str(lote_id)))
    except HeadlineError as exc:
        _raise(exc)


# ── static paths before /{headline_id} ──────────────────────────────────────


@router.get("/estruturas/contagem")
async def contagem_estruturas(
    marca_id: uuid.UUID,
    variaveis: list[str] = Query(...),
    auth=Depends(get_current_user_org),
):
    try:
        return success_response(_svc(auth).contagem_estruturas(str(marca_id), variaveis))
    except HeadlineError as exc:
        _raise(exc)


@router.post("/sugestoes/gerar-agora", status_code=202)
@limiter.limit(DEFAULT_AI_RL)
async def gerar_sugestoes_agora(
    request: Request,
    body: SugestaoAgora,
    auth=Depends(get_current_user_org),
    cfg=Depends(get_headline_settings),
    jobs: JobRepository = Depends(get_headline_jobs),
    ia_check=Depends(get_ia_check),
):
    geracao_jobs.assert_geracao_disponivel(cfg)
    _assert_ia(auth, ia_check)
    await geracao_jobs.assert_orcamento_ia(auth[2])
    try:
        return success_response(await _svc(auth, cfg, jobs).criar_sugestao(str(body.marca_id)))
    except HeadlineError as exc:
        _raise(exc)


@router.post("/excluir")
async def excluir_headlines(body: IdsBody, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).excluir_headlines([str(i) for i in body.ids]))
    except HeadlineError as exc:
        _raise(exc)


# ── headlines ───────────────────────────────────────────────────────────────


@router.get("")
async def list_headlines(
    marca_id: uuid.UUID,
    lista: str = Query(..., pattern="^(favoritas|sugeridas)$"),
    modo: Optional[str] = Query(None, pattern="^(manual|automatico)$"),
    q: Optional[str] = Query(None, max_length=200),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_headline_storage),
):
    try:
        return success_response(
            await _svc(auth, storage=storage).list_headlines(
                str(marca_id), lista=lista, modo=modo, q=q, limit=limit, offset=offset
            )
        )
    except HeadlineError as exc:
        _raise(exc)


@router.post("", status_code=201)
async def create_headline(body: HeadlineCreate, auth=Depends(get_current_user_org)):
    try:
        return success_response(await _svc(auth).criar(str(body.marca_id), body.texto))
    except HeadlineError as exc:
        _raise(exc)


@router.get("/{headline_id}")
async def get_headline(
    headline_id: uuid.UUID, auth=Depends(get_current_user_org), storage: StorageBackend = Depends(get_headline_storage),
):
    try:
        return success_response(await _svc(auth, storage=storage).get_headline(str(headline_id)))
    except HeadlineError as exc:
        _raise(exc)


@router.patch("/{headline_id}")
async def edit_headline(headline_id: uuid.UUID, body: HeadlineEdit, auth=Depends(get_current_user_org)):
    try:
        return success_response(await _svc(auth).editar(str(headline_id), body.texto))
    except HeadlineError as exc:
        _raise(exc)


@router.post("/{headline_id}/favoritar")
async def favoritar_headline(headline_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(await _svc(auth).favoritar(str(headline_id), True))
    except HeadlineError as exc:
        _raise(exc)


@router.post("/{headline_id}/desfavoritar")
async def desfavoritar_headline(headline_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(await _svc(auth).favoritar(str(headline_id), False))
    except HeadlineError as exc:
        _raise(exc)
