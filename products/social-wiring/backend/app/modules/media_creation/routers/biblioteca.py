"""Biblioteca de Virais + Minha Biblioteca -- endpoints 7-19 (geracao-contract.md section 4.3).

NOTE: no ``from __future__ import annotations`` here -- slowapi's ``@limiter.limit`` wrapper makes
FastAPI resolve string annotations in slowapi's globals, turning body params into query params.

Auth is ``get_current_user_org`` on every route (strict 401 without a session). A foreign / unknown
marca, profile, viral or reference is a 404. ``ingestao_ativa`` (the kill switch state) rides on the
profile payloads so the UI can say "a ingestão está desligada" instead of showing a silent spinner.
"""
import logging
import uuid
from typing import Callable, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL
from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.config import settings
from app.dependencies import (
    get_admin_client,
    get_current_user_org,
    get_platform_admin_check,
    require_platform_admin,
)
from app.modules.certidoes.deps import storage_for
from app.modules.media_creation.schemas.biblioteca import (
    OptoutCreate,
    PerfilCreate,
    PerfilPatch,
    ReferenciaPatch,
    ReferenciasCreate,
    ReferenciasPerfil,
)
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services import biblioteca_optout
from app.modules.media_creation.services.biblioteca_service import (
    BibliotecaError,
    BibliotecaService,
    ViralFiltros,
    purgar_handle,
)
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation/biblioteca", tags=["Media Creation — Biblioteca"])

_DATE = r"^\d{4}-\d{2}-\d{2}$"


def get_biblioteca_storage() -> StorageBackend:
    """Blob storage (PRIVATE ``sw-biblioteca``). Tests MUST override with a ``FakeStorageBackend``."""
    return storage_for(get_admin_client())


def get_biblioteca_jobs() -> JobRepository:
    """Queue repo. Tests override with a ``FakeJobRepository``."""
    return geracao_jobs.make_jobs_repository(get_admin_client())


def get_ingestao_switch() -> Callable[[], bool]:
    """The ``biblioteca_ingestao_habilitada`` reader (fail-closed). Tests override it."""
    return geracao_jobs.read_ingestao_habilitada


def _svc(auth, storage: StorageBackend, jobs: JobRepository, switch: Callable[[], bool]) -> BibliotecaService:
    user, _, org_id = auth
    return BibliotecaService(
        get_admin_client(), str(org_id), str(getattr(user, "id", "") or "") or None,
        storage=storage, jobs=jobs, switch=switch, max_perfis_org=int(settings.biblioteca_max_perfis_org),
        sync_manual_dia_org=int(settings.biblioteca_sync_manual_dia_org),
    )


def _raise(exc: BibliotecaError):
    headers = {"Retry-After": str(exc.retry_after_s)} if exc.retry_after_s else None
    detail = {"detail": exc.detail, "code": exc.code} if exc.code else exc.detail
    raise HTTPException(status_code=exc.status, detail=detail, headers=headers) from exc


# ── virais ──────────────────────────────────────────────────────────────────


@router.get("/virais")
async def list_virais(
    marca_id: uuid.UUID,
    nichos: list[int] = Query(default=[], max_length=10),
    profissoes: list[int] = Query(default=[], max_length=10),
    ver_todos: bool = False,
    ordem: Literal["mais_vistos", "mais_recentes"] = "mais_vistos",
    q: Optional[str] = Query(None, max_length=300),
    buscar_em: Literal["gancho", "transcricao"] = "gancho",
    data_de: Optional[str] = Query(None, pattern=_DATE),
    data_ate: Optional[str] = Query(None, pattern=_DATE),
    views_min: Optional[int] = Query(None, ge=0),
    likes_min: Optional[int] = Query(None, ge=0),
    comments_min: Optional[int] = Query(None, ge=0),
    perfil_id: Optional[uuid.UUID] = None,
    formato_id: Optional[int] = Query(None, ge=1),
    codigo: Optional[int] = Query(None, ge=1),
    somente_virais: bool = True,
    pool: Optional[Literal["minha_biblioteca"]] = None,
    page: int = Query(1, ge=1, le=1000),
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    f = ViralFiltros(
        marca_id=str(marca_id), nichos=list(dict.fromkeys(nichos)), profissoes=list(dict.fromkeys(profissoes)),
        ver_todos=ver_todos, ordem=ordem, q=q, buscar_em=buscar_em, data_de=data_de, data_ate=data_ate,
        views_min=views_min, likes_min=likes_min, comments_min=comments_min,
        perfil_id=str(perfil_id) if perfil_id else None, formato_id=formato_id, codigo=codigo,
        somente_virais=somente_virais, pool=pool, page=page,
    )
    svc = _svc(auth, storage, jobs, switch)
    try:
        data = await svc.list_virais(f)
    except BibliotecaError as exc:
        _raise(exc)
    data["ingestao_ativa"] = svc.ingestao_ativa()
    return success_response(data)


@router.get("/virais/{viral_id}")
async def get_viral(
    viral_id: uuid.UUID,
    marca_id: uuid.UUID,
    debug: int = Query(0, ge=0, le=1),
    auth=Depends(get_current_user_org),
    is_admin: Callable[[str], bool] = Depends(get_platform_admin_check),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    user_id = str(getattr(auth[0], "id", "") or "")
    # The blueprint is internal: only a platform admin asking for debug ever sees it.
    incluir = bool(debug) and bool(user_id) and bool(is_admin(user_id))
    try:
        return success_response(
            await _svc(auth, storage, jobs, switch).get_viral(str(viral_id), str(marca_id), incluir_blueprint=incluir)
        )
    except BibliotecaError as exc:
        _raise(exc)


# ── perfis ──────────────────────────────────────────────────────────────────


@router.get("/perfis")
async def list_perfis(
    q: Optional[str] = Query(None, max_length=100),
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    return success_response(await _svc(auth, storage, jobs, switch).list_perfis(q))


@router.get("/perfis/verificar")
async def verificar_perfil(
    handle: str = Query(..., min_length=1, max_length=200),
    marca_id: Optional[uuid.UUID] = None,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    try:
        return success_response(
            await _svc(auth, storage, jobs, switch).verificar(handle, str(marca_id) if marca_id else None)
        )
    except BibliotecaError as exc:
        _raise(exc)


@router.post("/perfis", status_code=201)
@limiter.limit(DEFAULT_AI_RL)
async def solicitar_perfil(
    request: Request,
    body: PerfilCreate,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    try:
        return success_response(
            await _svc(auth, storage, jobs, switch).criar_perfil(
                str(body.marca_id), body.handle,
                str(body.conta_descoberta_id) if body.conta_descoberta_id else None,
            )
        )
    except BibliotecaError as exc:
        _raise(exc)


@router.post("/perfis/{perfil_id}/sincronizar", status_code=202)
@limiter.limit(DEFAULT_AI_RL)
async def sincronizar_perfil(
    request: Request,
    perfil_id: uuid.UUID,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    try:
        return success_response(await _svc(auth, storage, jobs, switch).sincronizar(str(perfil_id)))
    except BibliotecaError as exc:
        _raise(exc)


@router.patch("/perfis/{perfil_id}")
async def patch_perfil(
    perfil_id: uuid.UUID,
    body: PerfilPatch,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    try:
        return success_response(
            await _svc(auth, storage, jobs, switch).patch_perfil(
                str(perfil_id), body.status, str(body.conta_descoberta_id) if body.conta_descoberta_id else None
            )
        )
    except BibliotecaError as exc:
        _raise(exc)


@router.delete("/perfis/{perfil_id}", status_code=204)
async def delete_perfil(
    perfil_id: uuid.UUID,
    marca_id: Optional[uuid.UUID] = None,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    try:
        await _svc(auth, storage, jobs, switch).delete_perfil(str(perfil_id), str(marca_id) if marca_id else None)
    except BibliotecaError as exc:
        _raise(exc)
    return Response(status_code=204)


@router.get("/contas-descoberta")
async def contas_descoberta(
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    return success_response(_svc(auth, storage, jobs, switch).contas_descoberta())


# ── Minha Biblioteca ────────────────────────────────────────────────────────


@router.get("/referencias")
async def list_referencias(
    marca_id: uuid.UUID,
    q: Optional[str] = Query(None, max_length=100),
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    try:
        return success_response(await _svc(auth, storage, jobs, switch).list_referencias(str(marca_id), q))
    except BibliotecaError as exc:
        _raise(exc)


@router.post("/referencias", status_code=201)
async def criar_referencias(
    body: ReferenciasCreate,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    svc = _svc(auth, storage, jobs, switch)
    try:
        if isinstance(body, ReferenciasPerfil):
            out = await svc.criar_referencias_perfil(
                str(body.marca_id), [str(p) for p in body.perfil_ids], body.auto_atualizar
            )
        else:
            out = await svc.criar_referencias_video(str(body.marca_id), [str(v) for v in body.viral_ids])
    except BibliotecaError as exc:
        _raise(exc)
    return success_response(out)


@router.patch("/referencias/{ref_id}")
async def patch_referencia(
    ref_id: uuid.UUID,
    body: ReferenciaPatch,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    try:
        return success_response(
            await _svc(auth, storage, jobs, switch).patch_referencia(str(ref_id), body.auto_atualizar, body.posts_ate)
        )
    except BibliotecaError as exc:
        _raise(exc)


@router.delete("/referencias/{ref_id}", status_code=204)
async def delete_referencia(
    ref_id: uuid.UUID,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_biblioteca_storage),
    jobs: JobRepository = Depends(get_biblioteca_jobs),
    switch: Callable[[], bool] = Depends(get_ingestao_switch),
):
    try:
        _svc(auth, storage, jobs, switch).delete_referencia(str(ref_id))
    except BibliotecaError as exc:
        _raise(exc)
    return Response(status_code=204)


# ── opt-out admin (platform admins only; LGPD Art. 7 IX + Meta deletion-on-request) ─────────────────────
# Every write below is a mutating request, so the platform AuditMiddleware records it in public.audit_logs
# with the acting admin (resolved by get_current_user_org); nothing personal beyond the handle is logged.


def _optout_out(row: dict) -> dict:
    return {k: row.get(k) for k in ("id", "handle", "motivo", "origem", "solicitado_em", "registrado_por", "created_at")}


@router.get("/admin/optouts")
async def list_optouts(auth=Depends(require_platform_admin)):
    return success_response([_optout_out(r) for r in biblioteca_optout.listar(get_admin_client())])


@router.post("/admin/optouts")
async def criar_optout(
    body: OptoutCreate,
    auth=Depends(require_platform_admin),
    storage: StorageBackend = Depends(get_biblioteca_storage),
):
    """Register the opt-out and synchronously purge the handle across ALL orgs. Idempotent: a repeat keeps
    the first row (``criado=false``) and re-runs the purge (a no-op once nothing is left)."""
    db = get_admin_client()
    user_id = str(getattr(auth[0], "id", "") or "") or None
    row, criado = biblioteca_optout.registrar(db, body.handle, body.motivo, body.origem, user_id)
    purgados = await purgar_handle(db, storage, body.handle)
    logger.info(
        "biblioteca opt-out: criado=%s origem=%s perfis=%d virais=%d blobs_falhos=%d",
        criado, body.origem, purgados["perfis"], purgados["virais"], purgados["blobs_falhos"],
    )
    return success_response({"optout": _optout_out(row), "criado": criado, "purgados": purgados})


@router.delete("/admin/optouts/{optout_id}", status_code=204)
async def remover_optout(optout_id: uuid.UUID, auth=Depends(require_platform_admin)):
    if not biblioteca_optout.remover(get_admin_client(), str(optout_id)):
        raise HTTPException(status_code=404, detail="Opt-out não encontrado")
    return Response(status_code=204)
