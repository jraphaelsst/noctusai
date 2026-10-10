"""Shared voice-transcription endpoints (transcription-contract.md section 4).

    POST   /api/transcricoes          202  multipart: arquivo + contexto_tipo + contexto_ref
    GET    /api/transcricoes/{id}          status / posicao / texto / erro (own jobs only)
    DELETE /api/transcricoes/{id}          cancel a queued job (409 once processing)
    GET    /api/transcricoes/_stats        platform admin: queue + daily minutes per org

Errors are ``{codigo, mensagem}`` (+ ``detail``) with ``Retry-After`` on 429/503;
another user's job is a 404, never a 403.
"""
# NOTE: no `from __future__ import annotations` here -- slowapi's @limiter.limit wrapper
# makes FastAPI resolve string annotations in slowapi's globals, turning the multipart
# params into query params (422 "Field required").
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL
from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.transcricoes.deps import (
    KillSwitch,
    TranscriberFactory,
    get_kill_switch,
    get_platform_admin_check,
    get_transcricao_jobs,
    get_transcricao_storage,
    get_transcriber_factory,
)
from app.modules.transcricoes.errors import TranscricaoErro, erro_response
from app.modules.transcricoes.service import MAX_BODY_BYTES, TranscricaoService
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/transcricoes", tags=["Transcrições"])

#: 🔴 THE APP REFUSES TO BOOT WITHOUT THIS ENTRY in `app.main._MAX_BODY_PATH_OVERRIDES`
#: (every mounted `UploadFile` route needs one). 15 MB file + multipart overhead; the
#: exact cap (413 `arquivo_grande`) is enforced by the route's stream cut.
MAX_BODY_PATH_OVERRIDES = {"/api/transcricoes": MAX_BODY_BYTES}


def build_service(
    auth, storage: StorageBackend, jobs: JobRepository,
    factory: TranscriberFactory, kill_switch: KillSwitch,
) -> TranscricaoService:
    user, _, org_id = auth
    user_id = str(getattr(user, "id", "") or "")
    if not user_id:
        # A product-token caller has no user; recordings belong to a person.
        raise HTTPException(status_code=403, detail="Esta área exige um usuário autenticado.")
    return TranscricaoService(
        get_admin_client(), str(org_id), user_id,
        storage=storage, jobs=jobs, transcriber_factory=factory, kill_switch=kill_switch,
    )


def require_platform_admin(
    auth=Depends(get_current_user_org), is_admin=Depends(get_platform_admin_check),
):
    user_id = str(getattr(auth[0], "id", "") or "")
    if not user_id or not is_admin(user_id):
        raise HTTPException(status_code=403, detail="Restrito a administradores da plataforma NoctusAI.")
    return auth


@router.post("", status_code=202)
@limiter.limit(DEFAULT_AI_RL)
async def submit_transcricao(
    request: Request,
    arquivo: UploadFile = File(...),
    contexto_tipo: str = Form(...),
    contexto_ref: str = Form(...),
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_transcricao_storage),
    jobs: JobRepository = Depends(get_transcricao_jobs),
    factory: TranscriberFactory = Depends(get_transcriber_factory),
    kill_switch: KillSwitch = Depends(get_kill_switch),
):
    svc = build_service(auth, storage, jobs, factory, kill_switch)
    try:
        declared = int(request.headers.get("content-length") or 0)
        if declared > MAX_BODY_BYTES:
            raise TranscricaoErro("arquivo_grande")
        return success_response(await svc.submit_upload(arquivo, contexto_tipo, contexto_ref))
    except TranscricaoErro as exc:
        return erro_response(exc)


@router.get("/_stats")
async def transcricoes_stats(
    auth=Depends(require_platform_admin),
    storage: StorageBackend = Depends(get_transcricao_storage),
    jobs: JobRepository = Depends(get_transcricao_jobs),
    factory: TranscriberFactory = Depends(get_transcriber_factory),
    kill_switch: KillSwitch = Depends(get_kill_switch),
):
    svc = build_service(auth, storage, jobs, factory, kill_switch)
    return success_response(await svc.stats())


@router.get("/{transcricao_id}")
async def get_transcricao(
    transcricao_id: uuid.UUID,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_transcricao_storage),
    jobs: JobRepository = Depends(get_transcricao_jobs),
    factory: TranscriberFactory = Depends(get_transcriber_factory),
    kill_switch: KillSwitch = Depends(get_kill_switch),
):
    svc = build_service(auth, storage, jobs, factory, kill_switch)
    try:
        return success_response(svc.get(str(transcricao_id)))
    except TranscricaoErro as exc:
        return erro_response(exc)


@router.delete("/{transcricao_id}")
async def cancel_transcricao(
    transcricao_id: uuid.UUID,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_transcricao_storage),
    jobs: JobRepository = Depends(get_transcricao_jobs),
    factory: TranscriberFactory = Depends(get_transcriber_factory),
    kill_switch: KillSwitch = Depends(get_kill_switch),
):
    svc = build_service(auth, storage, jobs, factory, kill_switch)
    try:
        return success_response(await svc.cancel(str(transcricao_id)))
    except TranscricaoErro as exc:
        return erro_response(exc)
